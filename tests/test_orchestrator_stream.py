"""
tests/test_orchestrator_stream.py
─────────────────────────────────────────────────────────────────────
Tests de bout en bout du pipeline de l'orchestrateur (RAG + tool
calling + streaming + métriques), via OfflineProvider : aucun appel
réseau, aucun mock fragile du SDK Groq.
─────────────────────────────────────────────────────────────────────
"""
import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.ai_agent.llm.providers import (
    GroqProvider,
    OfflineProvider,
    TokenEvent,
    ToolCallEvent,
    get_provider,
    groq_is_usable,
)
from apps.ai_agent.models import AgentMetric, ConversationChat, MessageChat
from apps.ai_agent.orchestrator import FSBOrchestrator
from apps.ai_agent.rag.embeddings import TfidfBackend
from apps.ai_agent.rag.knowledge import load_corpus_chunks
from apps.ai_agent.rag.retriever import Retriever

from tests.support import requires_groq_sdk

User = get_user_model()


def _make_admin(username="orch_admin"):
    return User.objects.create_user(
        username=username, password="TestPass123!", role="admin",
        first_name="Orch", last_name="Admin",
    )


def _shared_retriever():
    if not hasattr(_shared_retriever, "_cache"):
        _shared_retriever._cache = Retriever.build(
            backend=TfidfBackend(), chunks=load_corpus_chunks()
        )
    return _shared_retriever._cache


class OfflineProviderTest(TestCase):
    """Le fournisseur offline respecte le contrat de l'interface."""

    def test_stream_texte_sans_outil(self):
        provider = OfflineProvider()
        events = list(
            provider.stream_chat(
                [{"role": "user", "content": "Bonjour l'agent"}], tools=None
            )
        )
        self.assertTrue(all(isinstance(e, TokenEvent) for e in events))
        text = "".join(e.text for e in events)
        self.assertIn("Bonjour l'agent", text)

    def test_declenche_outil_statistiques(self):
        from apps.ai_agent.orchestrator import TOOLS

        provider = OfflineProvider()
        events = list(
            provider.stream_chat(
                [{"role": "user", "content": "Combien d'étudiants inscrits ?"}],
                tools=TOOLS,
            )
        )
        tool_calls = [e for e in events if isinstance(e, ToolCallEvent)]
        self.assertEqual(len(tool_calls), 1)
        self.assertEqual(tool_calls[0].name, "obtenir_statistiques")

    def test_complete_retourne_du_texte(self):
        provider = OfflineProvider()
        summary = provider.complete([{"role": "user", "content": "Résume"}])
        self.assertIsInstance(summary, str)
        self.assertTrue(summary)

    def test_fabrique_offline(self):
        self.assertIsInstance(get_provider("offline"), OfflineProvider)

    @requires_groq_sdk
    @override_settings(GROQ_API_KEY="cle-factice-de-test")
    def test_fabrique_groq_quand_le_fournisseur_est_utilisable(self):
        """Avec le SDK présent et une clé configurée, on obtient Groq."""
        provider = get_provider("groq")
        self.assertIsInstance(provider, GroqProvider)
        self.assertEqual(provider.name, "groq")

    @override_settings(GROQ_API_KEY="", LLM_FALLBACK_OFFLINE=True)
    def test_bascule_offline_quand_la_cle_manque(self):
        """
        Dégradation gracieuse : sans clé, on sert le fournisseur
        déterministe au lieu de planter. C'est ce qui rend un
        déploiement de démonstration utilisable sans secret — le
        retrieval, le tool calling et le streaming restent observables.
        """
        provider = get_provider("groq")
        self.assertIsInstance(provider, OfflineProvider)

    @override_settings(GROQ_API_KEY="", LLM_FALLBACK_OFFLINE=False)
    def test_echoue_bruyamment_si_le_repli_est_desactive(self):
        """
        En production réelle on refuse le repli silencieux : mieux vaut
        une erreur explicite qu'un agent qui répond du déterministe
        sans que personne ne s'en aperçoive.
        """
        with self.assertRaises(RuntimeError) as ctx:
            get_provider("groq")
        self.assertIn("GROQ_API_KEY", str(ctx.exception))

    @override_settings(GROQ_API_KEY="")
    def test_groq_is_usable_explique_la_raison(self):
        """La raison est exploitable pour les logs et l'interface."""
        usable, reason = groq_is_usable()
        self.assertFalse(usable)
        self.assertTrue(reason)


class OrchestratorStreamTest(TestCase):
    """Pipeline complet process_stream avec RAG et outils réels (BD)."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = _make_admin()
        from apps.administration.models import Departement, Etudiant, Filiere

        dept = Departement.objects.create(nom="informatique")
        cls.filiere = Filiere.objects.create(
            nom="Licence Info Stream", code="LI-STREAM", departement=dept,
            niveau="L3", type_formation="licence",
        )
        Etudiant.objects.create(
            nom="STREAMTEST", prenom="Etu", numero_etudiant="ETU-STREAM-01",
            filiere=cls.filiere, annee_inscription=2025,
        )

    def setUp(self):
        self.conv = ConversationChat.objects.create(
            user=self.admin, titre="stream-test"
        )

    def _run(self, message, provider=None):
        orchestrator = FSBOrchestrator(
            self.admin,
            provider=provider or OfflineProvider(),
            retriever=_shared_retriever(),
        )
        lines = list(orchestrator.process_stream(message, self.conv.pk))
        return [json.loads(line) for line in lines]

    def test_question_connaissance_injecte_des_sources(self):
        events = self._run("Comment justifier une absence ?")
        types = [e["type"] for e in events]
        self.assertIn("rag", types)
        self.assertIn("token", types)
        self.assertEqual(types[-1], "done")
        rag_event = next(e for e in events if e["type"] == "rag")
        self.assertGreaterEqual(len(rag_event["data"]), 1)
        # La réponse cite une source [S1] (câblage prompt → réponse)
        text = "".join(e["data"] for e in events if e["type"] == "token")
        self.assertIn("[S1]", text)

    def test_question_hors_corpus_ne_produit_pas_devenement_rag(self):
        events = self._run("Comment configurer un serveur Minecraft ?")
        self.assertNotIn("rag", [e["type"] for e in events])

    def test_action_outil_execute_et_repond(self):
        events = self._run("Cherche l'étudiant STREAMTEST")
        types = [e["type"] for e in events]
        self.assertIn("tool_start", types)
        tool_done = next(e for e in events if e["type"] == "tool_done")
        self.assertEqual(tool_done["data"], "chercher_etudiant")
        self.assertTrue(tool_done["success"])
        self.assertEqual(types[-1], "done")

    def test_reponse_sauvegardee_en_bd(self):
        self._run("Combien d'étudiants inscrits ?")
        saved = MessageChat.objects.filter(
            conversation=self.conv, role="assistant"
        )
        self.assertEqual(saved.count(), 1)
        self.assertTrue(saved.first().contenu)

    def test_metrique_enregistree_avec_telemetrie_rag(self):
        self._run("Quelle est la durée du stage de licence ?")
        metric = AgentMetric.objects.filter(user=self.admin).latest("timestamp")
        self.assertGreaterEqual(metric.rag_chunks, 1)
        self.assertIsNotNone(metric.rag_top_score)
        self.assertGreaterEqual(metric.retrieval_ms, 0)
        self.assertEqual(metric.tool_called, "")

    def test_metrique_outil_et_succes(self):
        self._run("Combien d'étudiants inscrits ?")
        metric = AgentMetric.objects.filter(user=self.admin).latest("timestamp")
        self.assertEqual(metric.tool_called, "obtenir_statistiques")
        self.assertTrue(metric.action_success)

    def test_permission_refusee_marque_echec(self):
        """Un rôle scolarite qui déclenche un outil admin → success=False."""
        scolarite = User.objects.create_user(
            username="orch_scol", password="x", role="scolarite"
        )
        conv = ConversationChat.objects.create(user=scolarite, titre="perm")
        # OfflineProvider mappe "planifi…" sur rien ; on force via canned
        # tool call en construisant un provider ad hoc.
        provider = OfflineProvider()

        original_decide = provider._decide_tool

        def force_planifier(user_text, tools):
            if "planifie" in user_text.lower():
                return (
                    "planifier_examen",
                    json.dumps(
                        {
                            "matiere_id": 1,
                            "date": "2026-09-01",
                            "heure_debut": "08:00",
                            "heure_fin": "10:00",
                        }
                    ),
                )
            return original_decide(user_text, tools)

        provider._decide_tool = force_planifier
        orchestrator = FSBOrchestrator(
            scolarite, provider=provider, retriever=_shared_retriever()
        )
        events = [
            json.loads(line)
            for line in orchestrator.process_stream(
                "Planifie un examen demain", conv.pk
            )
        ]
        tool_done = next(e for e in events if e["type"] == "tool_done")
        self.assertFalse(tool_done["success"])
        metric = AgentMetric.objects.filter(user=scolarite).latest("timestamp")
        self.assertFalse(metric.action_success)

    def test_rag_en_panne_ne_bloque_pas_le_chat(self):
        """Si le retriever lève, le pipeline continue sans sources."""

        class BrokenRetriever:
            def retrieve(self, *args, **kwargs):
                raise RuntimeError("index corrompu")

        orchestrator = FSBOrchestrator(
            self.admin, provider=OfflineProvider(), retriever=BrokenRetriever()
        )
        events = [
            json.loads(line)
            for line in orchestrator.process_stream("Bonjour", self.conv.pk)
        ]
        types = [e["type"] for e in events]
        self.assertNotIn("rag", types)
        self.assertNotIn("error", types)
        self.assertEqual(types[-1], "done")

    def test_erreur_fournisseur_emet_event_error(self):
        class ExplodingProvider(OfflineProvider):
            def stream_chat(self, *args, **kwargs):
                raise RuntimeError("panne LLM")
                yield  # pragma: no cover

        orchestrator = FSBOrchestrator(
            self.admin, provider=ExplodingProvider(), retriever=_shared_retriever()
        )
        events = [
            json.loads(line)
            for line in orchestrator.process_stream("Bonjour", self.conv.pk)
        ]
        self.assertEqual(events[-1]["type"], "error")
        self.assertIn("panne LLM", events[-1]["data"])


class HistorySummaryTest(TestCase):
    """Résumé automatique de l'historique long via provider.complete()."""

    def setUp(self):
        self.admin = _make_admin("orch_hist")
        self.conv = ConversationChat.objects.create(
            user=self.admin, titre="hist"
        )
        for i in range(25):
            MessageChat.objects.create(
                conversation=self.conv,
                role="user" if i % 2 == 0 else "assistant",
                contenu=f"Message numéro {i}",
            )

    def test_historique_long_est_resume(self):
        orchestrator = FSBOrchestrator(
            self.admin, provider=OfflineProvider(), retriever=_shared_retriever()
        )
        history = orchestrator._get_history(self.conv.pk, max_messages=20)
        # 1 résumé système + 8 messages récents
        self.assertEqual(len(history), 9)
        self.assertEqual(history[0]["role"], "system")
        self.assertIn("Résumé", history[0]["content"])
        self.assertEqual(history[-1]["content"], "Message numéro 24")
