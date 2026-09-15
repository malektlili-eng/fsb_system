"""
apps/ai_agent/orchestrator.py
─────────────────────────────────────────────────────────────────────
Agent IA V2 — Orchestrateur principal.

Architecture (voir docs/RAG.md pour les décisions de conception) :

  requête ──► RAG (embeddings locaux + index vectoriel)
         │      └─► chunks pertinents injectés comme SOURCES [S1..Sk]
         ├──► LLM (fournisseur interchangeable, Groq par défaut)
         │      └─► texte streamé  OU  demandes d'appels d'outils
         ├──► ToolExecutor (actions BD réelles, contrôle RBAC)
         └──► métriques (latence, tokens, retrieval, outil, succès)

Séparation des responsabilités MESURÉE (cf. BENCHMARKS.md) :
 • Connaissance stable (règlements, procédures, fiches entités)
   → RETRIEVAL sémantique : le modèle cite ses sources [S1]…
 • Données transactionnelles vivantes (notes, étudiants, plannings)
   → TOOL CALLING avec permissions par rôle : jamais indexées,
   jamais périmées, jamais servies sans contrôle RBAC.

Le fournisseur LLM est injecté (apps/ai_agent/llm/providers.py) :
l'orchestrateur est testé de bout en bout avec OfflineProvider,
sans réseau ni mock fragile du SDK Groq.
─────────────────────────────────────────────────────────────────────
"""
import json
import logging
import time
from typing import Generator

logger = logging.getLogger(__name__)


# ─── Outils disponibles (Tool Calling schema) ─────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "chercher_etudiant",
            "description": "Recherche un ou plusieurs étudiants par nom, prénom ou numéro étudiant",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Terme de recherche (nom, prénom, ou numéro)"},
                    "filiere_id": {"type": "integer", "description": "Filtrer par filière (optionnel)"},
                    "statut": {"type": "string", "enum": ["inscrit", "suspendu", "diplome", "abandonne"]}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "creer_etudiant",
            "description": "Crée un nouvel étudiant dans la base de données",
            "parameters": {
                "type": "object",
                "properties": {
                    "nom": {"type": "string"},
                    "prenom": {"type": "string"},
                    "email": {"type": "string", "format": "email"},
                    "filiere_id": {"type": "integer", "description": "ID de la filière"},
                    "annee_inscription": {"type": "integer"},
                    "cin": {"type": "string"}
                },
                "required": ["nom", "prenom", "filiere_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "obtenir_statistiques",
            "description": "Obtient des statistiques globales ou par filière",
            "parameters": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["etudiants", "notes", "absences", "stages", "global"]
                    },
                    "filiere_id": {"type": "integer", "description": "Filtrer par filière (optionnel)"}
                },
                "required": ["type"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "planifier_examen",
            "description": "Planifie ET ENREGISTRE un examen dans la base de données",
            "parameters": {
                "type": "object",
                "properties": {
                    "matiere_id": {"type": "integer"},
                    "session_id": {"type": "integer"},
                    "salle_id": {"type": "integer"},
                    "classe_id": {"type": "integer"},
                    "date": {"type": "string", "format": "date", "description": "Format YYYY-MM-DD"},
                    "heure_debut": {"type": "string", "description": "Format HH:MM"},
                    "heure_fin": {"type": "string", "description": "Format HH:MM"}
                },
                "required": ["matiere_id", "date", "heure_debut", "heure_fin"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "lister_filieres",
            "description": "Liste toutes les filières disponibles avec leurs informations",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "notes_etudiant",
            "description": "Récupère les notes d'un étudiant spécifique",
            "parameters": {
                "type": "object",
                "properties": {
                    "etudiant_id": {"type": "integer"},
                    "semestre": {"type": "integer", "enum": [1, 2]}
                },
                "required": ["etudiant_id"]
            }
        }
    }
]


# ─── Prompt système ───────────────────────────────────────────────────

SYSTEM_PROMPT_TEMPLATE = """Tu es l'assistant intelligent de la FSB (Faculté des Sciences de Bizerte).
Tu aides les agents administratifs à gérer les données universitaires.

UTILISATEUR CONNECTÉ : {user_name} (rôle : {user_role})
DATE AUJOURD'HUI : {today}

RÈGLES IMPORTANTES :
1. Tu réponds TOUJOURS en français
2. Tu utilises les outils disponibles pour effectuer des actions RÉELLES en base de données
3. Avant toute action de création/modification, tu CONFIRMES les données avec l'utilisateur
4. Tu ne révèles jamais de données sensibles (CIN, adresses) sans raison légitime
5. Si l'utilisateur n'a pas les droits suffisants, tu l'en informes poliment
6. Tu cites toujours les numéros/IDs exacts des entités que tu mentionnes
7. En cas de doute sur l'identité d'une personne, tu utilises d'abord chercher_etudiant
8. Quand des SOURCES [S1..Sk] sont fournies, tu fondes ta réponse dessus et tu
   cites l'identifiant de la source utilisée, ex. « (source : S2) ».
   Si les sources ne couvrent pas la question, tu le dis explicitement.

DONNÉES DE CONTEXTE RAPIDE :
{quick_context}
{sources_block}"""


# ─── Orchestrateur principal ──────────────────────────────────────────

class FSBOrchestrator:
    """
    Orchestrateur principal de l'agent IA V2.
    Gère le RAG, le tool calling, le streaming et les métriques.
    """

    def __init__(self, user, provider=None, retriever=None):
        self.user = user
        if provider is None:
            from apps.ai_agent.llm.providers import get_provider

            provider = get_provider()
        self.provider = provider
        self._retriever = retriever  # résolu paresseusement si None
        self.executor = ToolExecutor(user)

    # ─── RAG ─────────────────────────────────────────────────────────

    def _retrieve(self, message: str):
        """
        Retrieval sémantique — ne doit JAMAIS faire échouer le chat :
        toute erreur est journalisée et le pipeline continue sans
        contexte documentaire.
        """
        try:
            retriever = self._retriever
            if retriever is None:
                from apps.ai_agent.rag.retriever import get_retriever

                retriever = get_retriever()
                self._retriever = retriever
            return retriever.retrieve(message)
        except Exception as exc:
            logger.warning("RAG indisponible pour cette requête : %s", exc)
            return None

    # ─── Pipeline principal ──────────────────────────────────────────

    def process_stream(self, message: str, conv_id: int) -> Generator[str, None, None]:
        """
        Traite un message et yield les événements de la réponse (SSE).

        Yields (une ligne JSON par événement) :
            {"type": "rag",        "data": [sources], "latency_ms": ...}
            {"type": "token",      "data": "texte partiel"}
            {"type": "tool_start", "data": "Exécution : ..."}
            {"type": "tool_done",  "data": "nom_outil", "success": bool}
            {"type": "done",       "tokens": n, "elapsed_ms": ms}
            {"type": "error",      "data": "message"}
        """
        from apps.ai_agent.llm.providers import ToolCallEvent

        start_time = time.time()
        tokens_count = 0

        try:
            # 1. Historique avec mémoire intelligente
            history = self._get_history(conv_id)

            # 2. Retrieval sémantique (RAG) sur le corpus institutionnel
            retrieval = self._retrieve(message)
            sources_block = ""
            if retrieval and retrieval.chunks:
                sources_block = (
                    "\nSOURCES DOCUMENTAIRES (extraits du corpus FSB) :\n"
                    + retrieval.context_block()
                )
                yield json.dumps(retrieval.as_event(), ensure_ascii=False) + "\n"

            # 3. Contexte rapide (léger, ~200 tokens) + prompt système
            quick_ctx = self._build_quick_context()
            system = SYSTEM_PROMPT_TEMPLATE.format(
                user_name=self.user.get_full_name(),
                user_role=(
                    self.user.get_role_display()
                    if hasattr(self.user, "get_role_display")
                    else self.user.role
                ),
                today=__import__("datetime").date.today().isoformat(),
                quick_context=quick_ctx,
                sources_block=sources_block,
            )

            messages_to_send = history + [{"role": "user", "content": message}]
            first_pass = [{"role": "system", "content": system}] + messages_to_send

            # 4. Premier appel LLM avec tool calling (streaming normalisé)
            full_text = []
            tool_calls = []
            for line in self._stream_tokens(
                first_pass, full_text, tools=TOOLS, max_tokens=1500
            ):
                if isinstance(line, ToolCallEvent):
                    tool_calls.append(line)
                else:
                    tokens_count += 1
                    yield line

            # 5. Exécuter les outils si demandés, puis second appel
            tool_results = []
            if tool_calls:
                for event_or_result in self._run_tools(tool_calls, tool_results):
                    yield event_or_result

                second_pass = self._build_second_pass(first_pass, tool_results)
                for line in self._stream_tokens(
                    second_pass, full_text, tools=None, max_tokens=1200
                ):
                    tokens_count += 1
                    yield line

            # 6. Fin du stream : persistance + métriques
            elapsed_ms = int((time.time() - start_time) * 1000)
            final_text = "".join(full_text)
            self._save_message(conv_id, "assistant", final_text)
            self._log_metric(
                question=message[:500],
                response_length=len(final_text),
                response_time_ms=elapsed_ms,
                tokens_used=tokens_count,
                tool_called=tool_calls[0].name if tool_calls else "",
                action_success=(
                    all(tr["success"] for tr in tool_results) if tool_calls else None
                ),
                rag_chunks=len(retrieval.chunks) if retrieval else 0,
                rag_top_score=retrieval.top_score if retrieval else None,
                retrieval_ms=int(retrieval.latency_ms) if retrieval else 0,
            )

            yield json.dumps(
                {"type": "done", "tokens": tokens_count, "elapsed_ms": elapsed_ms}
            ) + "\n"

        except Exception as e:
            logger.error(f"Erreur orchestrateur : {e}", exc_info=True)
            yield json.dumps({"type": "error", "data": str(e)}) + "\n"

    def _stream_tokens(self, messages, full_text, tools, max_tokens):
        """
        Streame un appel LLM : yield une ligne JSON par token de texte,
        et yield l'objet ToolCallEvent tel quel pour les appels d'outils.
        Accumule le texte dans `full_text` (effet de bord assumé).
        """
        from apps.ai_agent.llm.providers import TokenEvent, ToolCallEvent

        for event in self.provider.stream_chat(
            messages, tools=tools, max_tokens=max_tokens, temperature=0.1
        ):
            if isinstance(event, TokenEvent):
                full_text.append(event.text)
                yield json.dumps({"type": "token", "data": event.text}) + "\n"
            elif isinstance(event, ToolCallEvent):
                yield event

    def _run_tools(self, tool_calls, tool_results):
        """
        Exécute chaque outil demandé (avec contrôle RBAC dans
        ToolExecutor), yield les événements tool_start / tool_done, et
        accumule les résultats dans `tool_results`.
        """
        for call in tool_calls:
            try:
                args = json.loads(call.arguments) if call.arguments else {}
            except json.JSONDecodeError:
                args = {}

            yield json.dumps(
                {"type": "tool_start", "data": f"Exécution : {call.name}..."}
            ) + "\n"

            result = self.executor.execute(call.name, args)
            success = bool(result.get("success", False))
            tool_results.append(
                {"call": call, "result": result, "success": success}
            )
            yield json.dumps(
                {"type": "tool_done", "data": call.name, "success": success}
            ) + "\n"

    @staticmethod
    def _build_second_pass(first_pass, tool_results):
        """Construit les messages du second appel (assistant + résultats)."""
        assistant_turn = {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": tr["call"].call_id,
                    "type": "function",
                    "function": {
                        "name": tr["call"].name,
                        "arguments": tr["call"].arguments,
                    },
                }
                for tr in tool_results
            ],
        }
        tool_turns = [
            {
                "role": "tool",
                "tool_call_id": tr["call"].call_id,
                "content": json.dumps(tr["result"], ensure_ascii=False),
            }
            for tr in tool_results
        ]
        return first_pass + [assistant_turn] + tool_turns

    # ─── Mémoire conversationnelle ───────────────────────────────────

    def _get_history(self, conv_id: int, max_messages: int = 20) -> list:
        """Récupère l'historique avec résumé automatique si trop long."""
        from apps.ai_agent.models import MessageChat

        messages_qs = MessageChat.objects.filter(
            conversation_id=conv_id
        ).order_by("timestamp")

        total = messages_qs.count()

        if total <= max_messages:
            return [{"role": m.role, "content": m.contenu} for m in messages_qs]

        # Résumer les anciens messages via le fournisseur LLM
        old = messages_qs[: total - 8]
        recent = messages_qs[total - 8:]

        old_text = "\n".join([f"{m.role}: {m.contenu[:200]}" for m in old])
        try:
            summary = self.provider.complete(
                [
                    {
                        "role": "user",
                        "content": (
                            "Résume cette conversation en 3 phrases max, "
                            f"en français :\n{old_text}"
                        ),
                    }
                ],
                max_tokens=200,
            )
        except Exception:
            summary = "(Historique résumé non disponible)"

        return [
            {"role": "system", "content": f"Résumé des échanges précédents : {summary}"},
            *[{"role": m.role, "content": m.contenu} for m in recent],
        ]

    # ─── Contexte, persistance, métriques ────────────────────────────

    def _build_quick_context(self) -> str:
        """Contexte minimal : stats globales et filières (< 300 tokens)."""
        try:
            from apps.administration.models import Etudiant, Enseignant, Filiere
            from apps.stages.models import DemandeStage

            filieres = [f"{f.code} ({f.nom})" for f in Filiere.objects.all()[:15]]
            ctx = {
                "stats": {
                    "etudiants_inscrits": Etudiant.objects.filter(
                        statut="inscrit"
                    ).count(),
                    "enseignants_actifs": Enseignant.objects.filter(
                        actif=True
                    ).count(),
                    "stages_en_attente": DemandeStage.objects.filter(
                        statut="en_attente"
                    ).count(),
                },
                "filieres": filieres,
            }
            return json.dumps(ctx, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Erreur build_quick_context : {e}")
            return "{}"

    def _save_message(self, conv_id: int, role: str, content: str):
        """Sauvegarde un message en base."""
        try:
            from apps.ai_agent.models import MessageChat

            MessageChat.objects.create(
                conversation_id=conv_id,
                role=role,
                contenu=content,
            )
        except Exception as e:
            logger.error(f"Erreur save_message : {e}")

    def _log_metric(self, **kwargs):
        """Log les métriques de performance de l'agent."""
        try:
            from apps.ai_agent.models import AgentMetric

            AgentMetric.objects.create(user=self.user, **kwargs)
        except Exception as e:
            logger.warning(f"Erreur metric log : {e}")


# ─── Exécuteur d'outils ───────────────────────────────────────────────

class ToolExecutor:
    """Exécute les outils appelés par le LLM avec vérification des permissions."""

    TOOL_PERMISSIONS = {
        "chercher_etudiant":   ['super_admin', 'admin', 'scolarite', 'chef_dept', 'doyen'],
        "creer_etudiant":      ['super_admin', 'admin', 'scolarite'],
        "obtenir_statistiques": ['super_admin', 'admin', 'scolarite', 'chef_dept', 'doyen'],
        "planifier_examen":    ['super_admin', 'admin'],
        "lister_filieres":     ['super_admin', 'admin', 'scolarite', 'chef_dept', 'doyen'],
        "notes_etudiant":      ['super_admin', 'admin', 'scolarite', 'chef_dept'],
    }

    def __init__(self, user):
        self.user = user

    def execute(self, tool_name: str, args: dict) -> dict:
        """Exécute un outil avec vérification des permissions."""
        allowed_roles = self.TOOL_PERMISSIONS.get(tool_name, [])
        if self.user.role not in allowed_roles:
            return {
                "success": False,
                "error": f"Permission refusée. L'outil '{tool_name}' nécessite "
                         f"un des rôles : {', '.join(allowed_roles)}"
            }

        handler = getattr(self, f"_tool_{tool_name}", None)
        if not handler:
            return {"success": False, "error": f"Outil inconnu : {tool_name}"}

        try:
            return handler(**args)
        except Exception as e:
            logger.error(f"Erreur tool {tool_name} : {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    def _tool_chercher_etudiant(self, query: str, filiere_id: int = None,
                                 statut: str = None) -> dict:
        from apps.administration.models import Etudiant
        from django.db.models import Q

        qs = Etudiant.objects.select_related('filiere').filter(
            Q(nom__icontains=query) |
            Q(prenom__icontains=query) |
            Q(numero_etudiant__icontains=query) |
            Q(email__icontains=query)
        )
        if filiere_id:
            qs = qs.filter(filiere_id=filiere_id)
        if statut:
            qs = qs.filter(statut=statut)

        results = [
            {
                "id": e.pk,
                "nom_complet": e.get_full_name(),
                "numero": e.numero_etudiant,
                "filiere": e.filiere.nom if e.filiere else None,
                "statut": e.statut,
                "email": e.email,
            }
            for e in qs[:10]
        ]
        return {
            "success": True,
            "count": len(results),
            "etudiants": results
        }

    def _tool_creer_etudiant(self, nom: str, prenom: str, filiere_id: int,
                              email: str = '', annee_inscription: int = None,
                              cin: str = '') -> dict:
        from apps.administration.services import EtudiantService
        import datetime

        data = {
            'nom': nom,
            'prenom': prenom,
            'email': email,
            'filiere': filiere_id,
            'annee_inscription': annee_inscription or datetime.date.today().year,
            'cin': cin,
        }
        etudiant = EtudiantService.creer(data, created_by=self.user)
        return {
            "success": True,
            "message": "Étudiant créé avec succès",
            "etudiant": {
                "id": etudiant.pk,
                "nom_complet": etudiant.get_full_name(),
                "numero_etudiant": etudiant.numero_etudiant,
                "email": etudiant.email,
                "filiere": etudiant.filiere.nom if etudiant.filiere else None,
            }
        }

    def _tool_obtenir_statistiques(self, type: str, filiere_id: int = None) -> dict:
        from apps.administration.models import Etudiant, Enseignant, Filiere
        from apps.pedagogie.models import Note, Absence
        from apps.stages.models import DemandeStage

        base_filter = {}
        if filiere_id:
            base_filter['filiere_id'] = filiere_id

        if type == 'global':
            return {
                "success": True,
                "stats": {
                    "total_etudiants": Etudiant.objects.filter(statut='inscrit').count(),
                    "total_enseignants": Enseignant.objects.filter(actif=True).count(),
                    "total_filieres": Filiere.objects.count(),
                    "stages_en_attente": DemandeStage.objects.filter(statut='en_attente').count(),
                    "total_notes_saisies": Note.objects.count(),
                }
            }

        if type == 'etudiants':
            qs = Etudiant.objects.filter(**base_filter)
            return {
                "success": True,
                "stats": {
                    "inscrits": qs.filter(statut='inscrit').count(),
                    "diplomes": qs.filter(statut='diplome').count(),
                    "suspendus": qs.filter(statut='suspendu').count(),
                }
            }

        if type == 'absences':
            qs = Absence.objects.filter(**{
                k.replace('filiere', 'etudiant__filiere'): v
                for k, v in base_filter.items()
            })
            return {
                "success": True,
                "stats": {
                    "total": qs.count(),
                    "justifiees": qs.filter(justifiee=True).count(),
                    "non_justifiees": qs.filter(justifiee=False).count(),
                }
            }

        return {"success": False, "error": f"Type de statistique inconnu : {type}"}

    def _tool_planifier_examen(self, matiere_id: int, date: str,
                                heure_debut: str, heure_fin: str,
                                session_id: int = None, salle_id: int = None,
                                classe_id: int = None) -> dict:
        from apps.examens.models import PlanningExamen
        from django.db import transaction

        with transaction.atomic():
            planning = PlanningExamen(
                matiere_id=matiere_id,
                date=date,
                heure_debut=heure_debut,
                heure_fin=heure_fin,
            )
            if session_id:
                planning.session_id = session_id
            if salle_id:
                planning.salle_id = salle_id
            if classe_id:
                planning.classe_id = classe_id

            # Vérifier les conflits
            if salle_id and planning.is_conflit_salle():
                return {
                    "success": False,
                    "error": "Conflit de salle détecté sur ce créneau"
                }
            if classe_id and planning.is_conflit_classe():
                return {
                    "success": False,
                    "error": "La classe a déjà un examen sur ce créneau"
                }

            planning.save()

        return {
            "success": True,
            "message": f"Examen planifié le {date} de {heure_debut} à {heure_fin}",
            "planning_id": planning.pk,
        }

    def _tool_lister_filieres(self) -> dict:
        from apps.administration.models import Filiere
        return {
            "success": True,
            "filieres": [
                {
                    "id": f.pk,
                    "code": f.code,
                    "nom": f.nom,
                    "niveau": f.niveau,
                    "departement": f.departement.get_nom_display() if f.departement else None,
                }
                for f in Filiere.objects.select_related('departement').order_by('nom')
            ]
        }

    def _tool_notes_etudiant(self, etudiant_id: int, semestre: int = None) -> dict:
        from apps.pedagogie.models import Note
        qs = Note.objects.filter(etudiant_id=etudiant_id).select_related('matiere')
        if semestre:
            qs = qs.filter(semestre=semestre)
        return {
            "success": True,
            "notes": [
                {
                    "matiere": n.matiere.nom if n.matiere else "?",
                    "type": n.get_type_note_display(),
                    "note": n.note,
                    "semestre": n.semestre,
                }
                for n in qs
            ]
        }
