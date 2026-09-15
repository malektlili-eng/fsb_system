"""
apps/ai_agent/rag/retriever.py
─────────────────────────────────────────────────────────────────────
Retriever : point d'entrée du pipeline RAG côté requête.

Pipeline : requête → embedding → top-k cosinus (vector store)
         → boost lexical léger → seuil de pertinence → contexte.

Deux garde-fous mesurés dans l'évaluation (reports/rag_evaluation.md) :

 • SEUIL DE PERTINENCE (min_score) : si aucun chunk ne dépasse le
   seuil, on n'injecte RIEN — un contexte hors-sujet dégrade la
   réponse plus qu'un contexte absent (l'agent bascule alors sur
   ses outils ou répond qu'il ne sait pas).

 • SCORE HYBRIDE : score = cosinus + α · recouvrement_lexical.
   Le recouvrement lexical (Jaccard sur mots > 3 lettres) rattrape
   les requêtes très courtes ("rattrapage ?") où le signal dense
   est faible. α = 0.25, choisi par l'ablation A3 du rapport d'éval.
─────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path

from .chunking import Chunk
from .embeddings import EmbeddingBackend, get_backend
from .knowledge import build_knowledge_chunks
from .vector_store import VectorStore

logger = logging.getLogger(__name__)

DEFAULT_TOP_K = 4
DEFAULT_MIN_SCORE = 0.20
LEXICAL_ALPHA = 0.25

_WORD_RE = re.compile(r"[a-zà-ÿ]{4,}", re.IGNORECASE)


@dataclass
class RetrievalResult:
    """Résultat d'une requête de retrieval, avec sa télémétrie."""

    query: str
    chunks: list[tuple[Chunk, float]]
    latency_ms: float
    backend: str

    @property
    def top_score(self) -> float:
        return self.chunks[0][1] if self.chunks else 0.0

    def context_block(self) -> str:
        """Formate les chunks retenus en bloc SOURCES pour le prompt."""
        if not self.chunks:
            return ""
        lines = []
        for i, (chunk, score) in enumerate(self.chunks, start=1):
            lines.append(f"[S{i}] ({chunk.section}) {chunk.content}")
            logger.debug("RAG S%d score=%.3f %s", i, score, chunk.chunk_id)
        return "\n".join(lines)

    def as_event(self) -> dict:
        """Payload SSE envoyé au client pour afficher les sources."""
        return {
            "type": "rag",
            "data": [
                {
                    "rank": i + 1,
                    "section": chunk.section,
                    "source": chunk.source_doc,
                    "score": round(score, 3),
                }
                for i, (chunk, score) in enumerate(self.chunks)
            ],
            "latency_ms": round(self.latency_ms, 1),
        }


def _lexical_overlap(query: str, text: str) -> float:
    """Jaccard sur les mots significatifs (> 3 lettres)."""
    q_words = set(_WORD_RE.findall(query.lower()))
    if not q_words:
        return 0.0
    t_words = set(_WORD_RE.findall(text.lower()))
    if not t_words:
        return 0.0
    return len(q_words & t_words) / len(q_words | t_words)


class Retriever:
    """
    Retriever prêt à l'emploi au-dessus d'un VectorStore.

    Usage :
        retriever = Retriever.from_index(settings.RAG_INDEX_DIR)
        result = retriever.retrieve("Comment justifier une absence ?")
    """

    def __init__(self, store: VectorStore, backend: EmbeddingBackend):
        self.store = store
        self.backend = backend

    # ─── Constructeurs ───────────────────────────────────────────────

    @classmethod
    def build(
        cls,
        backend: EmbeddingBackend | None = None,
        include_db_entities: bool = True,
        chunks: list[Chunk] | None = None,
    ) -> "Retriever":
        """Construit l'index en mémoire à partir du corpus."""
        backend = backend or get_backend()
        if chunks is None:
            chunks = build_knowledge_chunks(include_db_entities=include_db_entities)
        if not chunks:
            raise RuntimeError("Corpus vide : impossible de construire l'index RAG.")
        texts = [c.text for c in chunks]
        backend.fit(texts)
        vectors = backend.encode(texts)
        store = VectorStore()
        store.add(chunks, vectors)
        logger.info(
            "Index RAG construit : %d chunks, backend=%s", len(store), backend.name
        )
        return cls(store, backend)

    @classmethod
    def from_index(
        cls, index_dir: str | Path, backend: EmbeddingBackend | None = None
    ) -> "Retriever":
        """
        Charge un index persisté. Le backend TF-IDF étant ajusté sur le
        corpus, on le ré-ajuste sur les textes rechargés (déterministe,
        < 1 s) ; un backend pré-entraîné (sentence-transformers) est
        chargé tel quel.
        """
        store = VectorStore.load(index_dir)
        backend = backend or get_backend()
        backend.fit([c.text for c in store.chunks])
        return cls(store, backend)

    def save(self, index_dir: str | Path) -> None:
        self.store.save(index_dir, backend_name=self.backend.name)

    # ─── Requête ─────────────────────────────────────────────────────

    def retrieve(
        self,
        query: str,
        top_k: int = DEFAULT_TOP_K,
        min_score: float = DEFAULT_MIN_SCORE,
        lexical_alpha: float = LEXICAL_ALPHA,
    ) -> RetrievalResult:
        start = time.perf_counter()
        query_vec = self.backend.encode_one(query)
        # On sur-échantillonne (top_k * 3) avant re-scoring hybride.
        candidates = self.store.search(query_vec, top_k=top_k * 3, min_score=0.0)

        rescored: list[tuple[Chunk, float]] = []
        for chunk, cos_score in candidates:
            hybrid = cos_score + lexical_alpha * _lexical_overlap(query, chunk.text)
            rescored.append((chunk, hybrid))
        rescored.sort(key=lambda pair: -pair[1])
        kept = [(c, s) for c, s in rescored[:top_k] if s >= min_score]

        latency_ms = (time.perf_counter() - start) * 1000
        return RetrievalResult(
            query=query,
            chunks=kept,
            latency_ms=latency_ms,
            backend=self.backend.name,
        )


# ─── Singleton applicatif (chargé paresseusement) ────────────────────

_default_retriever: Retriever | None = None


def get_retriever(force_rebuild: bool = False) -> Retriever:
    """
    Retourne le retriever applicatif partagé.

    Ordre de résolution :
      1. Index persisté dans settings.RAG_INDEX_DIR (s'il existe)
      2. Construction à la volée depuis le corpus (puis persistance)
    """
    global _default_retriever
    if _default_retriever is not None and not force_rebuild:
        return _default_retriever

    from django.conf import settings

    index_dir = Path(
        getattr(settings, "RAG_INDEX_DIR", settings.BASE_DIR / "var" / "rag_index")
    )
    if VectorStore.exists(index_dir) and not force_rebuild:
        _default_retriever = Retriever.from_index(index_dir)
    else:
        _default_retriever = Retriever.build()
        try:
            _default_retriever.save(index_dir)
        except OSError as exc:
            logger.warning("Index RAG non persisté (%s) — mode mémoire.", exc)
    return _default_retriever


def reset_retriever() -> None:
    """Réinitialise le singleton (utilisé par les tests)."""
    global _default_retriever
    _default_retriever = None
