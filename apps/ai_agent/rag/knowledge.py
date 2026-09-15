"""
apps/ai_agent/rag/knowledge.py
─────────────────────────────────────────────────────────────────────
Construction du corpus de connaissances indexé par le RAG.

Deux sources de vérité complémentaires :

 1. DOCUMENTS INSTITUTIONNELS (rag/corpus/*.md)
    Règlement des études, procédures, FAQ… Connaissance stable,
    découpée par chunk_markdown() (fenêtre glissante sur phrases).

 2. FICHES ENTITÉS (base de données)
    Filières, départements, salles : entités peu volatiles dont la
    description textuelle permet de répondre à "quelles filières de
    niveau L3 ?" par similarité sémantique. Une fiche = un chunk via
    serialize_record().

Ce qui n'est PAS indexé — et pourquoi (choix documenté) :
    Les données transactionnelles vivantes (notes, absences,
    étudiants individuels) restent servies par le TOOL CALLING avec
    contrôle RBAC : les indexer créerait un index périmé dès la
    première saisie et contournerait les permissions par rôle.
    Voir docs/RAG.md § "RAG vs Tool Calling".
─────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import logging
from pathlib import Path

from .chunking import Chunk, chunk_markdown, serialize_record

logger = logging.getLogger(__name__)

# Corpus par défaut (FSB). Surchargé par settings.RAG_CORPUS_DIR :
# pointer cette variable vers un autre dossier de .md suffit à faire
# tourner le MÊME moteur RAG sur un tout autre domaine (RH, juridique,
# support client…), sans modifier une ligne de code. Voir docs/RAG.md.
_DEFAULT_CORPUS_DIR = Path(__file__).resolve().parent / "corpus"


def _resolve_corpus_dir(corpus_dir: str | Path | None) -> Path:
    """Ordre de résolution : argument explicite > settings > défaut FSB."""
    if corpus_dir is not None:
        return Path(corpus_dir)
    try:
        from django.conf import settings

        configured = getattr(settings, "RAG_CORPUS_DIR", None)
        if configured:
            return Path(configured)
    except Exception:
        pass
    return _DEFAULT_CORPUS_DIR


# Rétro-compatibilité : certains modules importent CORPUS_DIR.
CORPUS_DIR = _DEFAULT_CORPUS_DIR


def load_corpus_chunks(
    corpus_dir: str | Path | None = None,
    chunk_size: int | None = None,
    overlap_sentences: int | None = None,
) -> list[Chunk]:
    """Charge et découpe tous les documents Markdown du corpus."""
    corpus_dir = _resolve_corpus_dir(corpus_dir)
    kwargs = {}
    if chunk_size is not None:
        kwargs["chunk_size"] = chunk_size
    if overlap_sentences is not None:
        kwargs["overlap_sentences"] = overlap_sentences

    chunks: list[Chunk] = []
    for md_file in sorted(corpus_dir.glob("*.md")):
        text = md_file.read_text(encoding="utf-8")
        doc_chunks = chunk_markdown(text, source_doc=md_file.stem, **kwargs)
        chunks.extend(doc_chunks)
        logger.info("Corpus : %s → %d chunks", md_file.name, len(doc_chunks))
    return chunks


def load_entity_chunks() -> list[Chunk]:
    """
    Sérialise les entités BD stables (filières, départements, salles)
    en fiches d'un chunk. Tolérant : si la BD est vide ou inaccessible,
    retourne simplement une liste vide.
    """
    chunks: list[Chunk] = []
    try:
        from apps.administration.models import Departement, Filiere, Salle

        for filiere in Filiere.objects.select_related("departement"):
            chunks.append(
                serialize_record(
                    kind="filière",
                    identifier=filiere.code,
                    fields={
                        "Filière": filiere.nom,
                        "Code": filiere.code,
                        "Niveau": filiere.niveau,
                        "Type de formation": filiere.type_formation,
                        "Département": (
                            filiere.departement.get_nom_display()
                            if filiere.departement
                            else None
                        ),
                    },
                )
            )
        for dept in Departement.objects.all():
            chunks.append(
                serialize_record(
                    kind="département",
                    identifier=str(dept.pk),
                    fields={
                        "Département": dept.get_nom_display(),
                        "Nombre de filières": dept.filieres.count(),
                    },
                )
            )
        for salle in Salle.objects.all():
            chunks.append(
                serialize_record(
                    kind="salle",
                    identifier=salle.nom,
                    fields={
                        "Salle": salle.nom,
                        "Capacité": getattr(salle, "capacite", None),
                        "Type": getattr(salle, "type_salle", None),
                    },
                )
            )
    except Exception as exc:
        logger.warning("Fiches entités BD non chargées : %s", exc)
    return chunks


def build_knowledge_chunks(
    include_db_entities: bool = True,
    corpus_dir: str | Path | None = None,
    chunk_size: int | None = None,
    overlap_sentences: int | None = None,
) -> list[Chunk]:
    """Assemble le corpus complet (documents + fiches entités)."""
    chunks = load_corpus_chunks(
        corpus_dir=corpus_dir,
        chunk_size=chunk_size,
        overlap_sentences=overlap_sentences,
    )
    if include_db_entities:
        chunks.extend(load_entity_chunks())
    return chunks
