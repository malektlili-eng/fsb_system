"""
apps/ai_agent/llm/providers.py
─────────────────────────────────────────────────────────────────────
Abstraction du fournisseur LLM.

Réponse directe à la critique "le LLM est entièrement délégué à
Groq" : ce projet POSSÈDE sa couche retrieval (embeddings locaux,
index, ranking, évaluation — voir apps/ai_agent/rag/) et traite la
GÉNÉRATION comme un composant interchangeable derrière cette
interface. Conséquences concrètes :

 • GroqProvider     : production (modèle Groq configurable).
 • OfflineProvider  : générateur déterministe SANS réseau, utilisé
   par les tests et le mode offline des benchmarks. Il simule le
   protocole de streaming ET le tool calling (déclenchement piloté
   par le contenu de la requête), ce qui permet de tester le
   pipeline complet de l'orchestrateur de façon reproductible.

Changer de fournisseur (OpenAI, vLLM auto-hébergé, Ollama…) =
implémenter LLMProvider, sans toucher à l'orchestrateur.
─────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Generator, Iterable


# ─── Événements de streaming normalisés ───────────────────────────────


@dataclass
class TokenEvent:
    """Un fragment de texte streamé."""

    text: str


@dataclass
class ToolCallEvent:
    """Une demande d'appel d'outil émise par le modèle."""

    call_id: str
    name: str
    arguments: str  # JSON brut (string), comme dans l'API OpenAI/Groq


@dataclass
class ChatTurn:
    """Réponse complète d'un tour (utilisée hors streaming)."""

    text: str = ""
    tool_calls: list[ToolCallEvent] = field(default_factory=list)


StreamEvent = TokenEvent | ToolCallEvent


# ─── Interface ─────────────────────────────────────────────────────────


class LLMProvider(ABC):
    """Interface minimale requise par l'orchestrateur."""

    name: str = "abstract"

    @abstractmethod
    def stream_chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        max_tokens: int = 1500,
        temperature: float = 0.1,
    ) -> Generator[StreamEvent, None, None]:
        """Streame la réponse sous forme d'événements normalisés."""

    @abstractmethod
    def complete(
        self,
        messages: list[dict],
        max_tokens: int = 300,
        temperature: float = 0.1,
    ) -> str:
        """Complétion simple non streamée (résumés d'historique…)."""


# ─── Groq (production) ────────────────────────────────────────────────


class GroqProvider(LLMProvider):
    """Fournisseur de production : Groq (modèle via settings.GROQ_MODEL)."""

    name = "groq"

    def __init__(self, api_key: str | None = None, model: str | None = None,
                 summary_model: str = "llama-3.1-8b-instant"):
        from django.conf import settings
        from groq import Groq

        self._client = Groq(api_key=api_key or settings.GROQ_API_KEY)
        self.model = model or settings.GROQ_MODEL
        self.summary_model = summary_model

    def stream_chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        max_tokens: int = 1500,
        temperature: float = 0.1,
    ) -> Generator[StreamEvent, None, None]:
        kwargs = dict(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            stream=True,
        )
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        response = self._client.chat.completions.create(**kwargs)

        partial_calls: dict[int, dict] = {}
        for chunk in response:
            delta = chunk.choices[0].delta
            if delta.content:
                yield TokenEvent(text=delta.content)
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    slot = partial_calls.setdefault(
                        tc.index,
                        {"id": tc.id or f"call_{tc.index}", "name": "", "arguments": ""},
                    )
                    if tc.id:
                        slot["id"] = tc.id
                    if tc.function:
                        if tc.function.name:
                            slot["name"] = tc.function.name
                        if tc.function.arguments:
                            slot["arguments"] += tc.function.arguments
        for _, slot in sorted(partial_calls.items()):
            yield ToolCallEvent(
                call_id=slot["id"], name=slot["name"], arguments=slot["arguments"]
            )

    def complete(
        self,
        messages: list[dict],
        max_tokens: int = 300,
        temperature: float = 0.1,
    ) -> str:
        response = self._client.chat.completions.create(
            model=self.summary_model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return response.choices[0].message.content or ""


# ─── Offline (tests & benchmarks reproductibles) ──────────────────────


class OfflineProvider(LLMProvider):
    """
    Générateur déterministe sans réseau.

    Règles de simulation du tool calling (sur le DERNIER message
    utilisateur) :
      - "combien" / "statistiq"  → obtenir_statistiques(global)
      - "cherche" / "trouve"     → chercher_etudiant(query=<dernier mot>)
      - "filière"/"filiere" + "liste" → lister_filieres()
    Sinon : réponse textuelle streamée mot à mot, qui reprend les
    identifiants de sources [S1]… présents dans le prompt système,
    ce qui permet de vérifier le câblage RAG → réponse dans les tests.
    """

    name = "offline"

    def __init__(self, canned_text: str | None = None):
        self.canned_text = canned_text
        self.calls: list[list[dict]] = []  # journal pour les assertions

    # -- helpers ------------------------------------------------------

    @staticmethod
    def _last_user_content(messages: Iterable[dict]) -> str:
        for message in reversed(list(messages)):
            if message.get("role") == "user":
                return str(message.get("content", ""))
        return ""

    @staticmethod
    def _system_content(messages: Iterable[dict]) -> str:
        for message in messages:
            if message.get("role") == "system":
                return str(message.get("content", ""))
        return ""

    def _decide_tool(self, user_text: str, tools: list[dict] | None):
        if not tools:
            return None
        lowered = user_text.lower()
        available = {t["function"]["name"] for t in tools}
        if ("combien" in lowered or "statistiq" in lowered) and (
            "obtenir_statistiques" in available
        ):
            return ("obtenir_statistiques", json.dumps({"type": "global"}))
        if ("cherche" in lowered or "trouve" in lowered) and (
            "chercher_etudiant" in available
        ):
            last_word = user_text.strip().split()[-1].strip("?!. ")
            return ("chercher_etudiant", json.dumps({"query": last_word}))
        if "filière" in lowered or "filiere" in lowered:
            if "liste" in lowered and "lister_filieres" in available:
                return ("lister_filieres", json.dumps({}))
        return None

    # -- interface ----------------------------------------------------

    def stream_chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        max_tokens: int = 1500,
        temperature: float = 0.1,
    ) -> Generator[StreamEvent, None, None]:
        self.calls.append(list(messages))
        has_tool_results = any(m.get("role") == "tool" for m in messages)
        user_text = self._last_user_content(messages)

        if not has_tool_results:
            decided = self._decide_tool(user_text, tools)
            if decided:
                name, arguments = decided
                yield ToolCallEvent(call_id="call_0", name=name, arguments=arguments)
                return

        if self.canned_text is not None:
            text = self.canned_text
        elif has_tool_results:
            text = "Voici le résultat obtenu depuis la base de données."
        else:
            system = self._system_content(messages)
            cited = " [S1]" if "[S1]" in system else ""
            text = f"Réponse hors-ligne à : {user_text}{cited}"

        for word in text.split(" "):
            yield TokenEvent(text=word + " ")

    def complete(
        self,
        messages: list[dict],
        max_tokens: int = 300,
        temperature: float = 0.1,
    ) -> str:
        return "Résumé hors-ligne de la conversation précédente."


# ─── Fabrique ─────────────────────────────────────────────────────────


def groq_is_usable() -> tuple[bool, str]:
    """
    Le fournisseur Groq est-il réellement utilisable ici ?

    Vérifie les deux conditions indépendantes : le SDK est importable, et
    une clé API est configurée. Retourne ``(ok, raison)`` — la raison sert
    aux logs et à la bannière de l'interface.
    """
    try:
        import groq  # noqa: F401
    except ImportError:
        return False, "le SDK groq n'est pas installé"

    try:
        from django.conf import settings

        if not getattr(settings, "GROQ_API_KEY", ""):
            return False, "GROQ_API_KEY n'est pas renseignée"
    except Exception:  # pragma: no cover - Django non configuré
        return False, "configuration Django indisponible"

    return True, ""


def get_provider(name: str | None = None) -> LLMProvider:
    """
    Résout le fournisseur selon settings.LLM_PROVIDER
    ("groq" par défaut, "offline" pour tests/CI).

    Dégradation gracieuse : si "groq" est demandé mais inutilisable (SDK
    absent ou clé manquante) et que LLM_FALLBACK_OFFLINE est actif, on
    bascule sur OfflineProvider au lieu de lever une exception. C'est ce
    qui permet à un déploiement de démonstration de rester fonctionnel
    sans secret : le retrieval, le tool calling et le streaming SSE —
    c'est-à-dire tout ce que ce dépôt implémente réellement — restent
    observables ; seule la fluidité de la génération est dégradée.
    Un déploiement de production met LLM_FALLBACK_OFFLINE=False pour
    échouer bruyamment plutôt que servir silencieusement du déterministe.
    """
    import logging

    logger = logging.getLogger(__name__)

    # Le réglage de repli se lit TOUJOURS depuis les settings, que le
    # fournisseur ait été nommé explicitement ou non : c'est une
    # politique de déploiement, pas un paramètre d'appel.
    fallback_enabled = True
    try:
        from django.conf import settings

        fallback_enabled = getattr(settings, "LLM_FALLBACK_OFFLINE", True)
        if name is None:
            name = getattr(settings, "LLM_PROVIDER", "groq")
    except Exception:  # pragma: no cover - Django non configuré
        if name is None:
            name = "offline"

    if name == "offline":
        return OfflineProvider()

    usable, reason = groq_is_usable()
    if not usable:
        if not fallback_enabled:
            raise RuntimeError(
                f"Fournisseur LLM 'groq' indisponible : {reason}. "
                "Renseignez GROQ_API_KEY ou passez LLM_PROVIDER=offline."
            )
        logger.warning(
            "Fournisseur 'groq' indisponible (%s) — bascule sur "
            "OfflineProvider déterministe. RAG, tool calling et streaming "
            "restent actifs.",
            reason,
        )
        return OfflineProvider()

    return GroqProvider()
