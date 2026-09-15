"""
apps/ai_agent/rag/chunking.py
─────────────────────────────────────────────────────────────────────
Stratégie de découpage (chunking) du corpus documentaire.

Choix de conception (voir docs/RAG.md pour la justification complète) :

 1. Découpage par FENÊTRE GLISSANTE alignée sur les PHRASES :
    on ne coupe jamais au milieu d'une phrase, ce qui préserve
    la cohérence sémantique de chaque chunk.

 2. Taille cible ~450 caractères (~110 tokens) avec chevauchement
    d'une phrase entre chunks consécutifs : un fait à cheval sur
    deux chunks reste retrouvable.

 3. Conscience de la STRUCTURE Markdown : chaque chunk est préfixé
    par le titre du document et de la section dont il provient
    ("Règlement des études > Article 12 — Rattrapage"). Ce préfixe
    est embarqué avec le texte, ce qui améliore nettement le rappel
    sur les requêtes qui nomment la procédure plutôt que son contenu.

 4. Les enregistrements BD (filières, salles…) sont sérialisés en
    "fiches" d'un chunk chacune via serialize_record() : format
    déterministe clé→valeur, adapté aux entités courtes.
─────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

# Taille cible d'un chunk, en caractères (~110 tokens français).
DEFAULT_CHUNK_SIZE = 450
# Nombre de phrases de chevauchement entre deux chunks consécutifs.
DEFAULT_OVERLAP_SENTENCES = 1
# Taille minimale : en dessous, le fragment est fusionné au précédent.
MIN_CHUNK_SIZE = 80

_SENTENCE_SPLIT_RE = re.compile(
    r"(?<=[.!?;:])\s+(?=[A-ZÀÂÉÈÊËÎÏÔÙÛÜÇ0-9«\-—•])"
)
_MD_HEADER_RE = re.compile(r"^(#{1,4})\s+(.*)$")


@dataclass
class Chunk:
    """Un fragment indexable du corpus, avec sa provenance."""

    chunk_id: str
    text: str            # texte embarqué (préfixe section + contenu)
    content: str         # contenu brut, sans préfixe
    source_doc: str      # identifiant du document d'origine
    section: str         # chemin de section ("Doc > Section")
    position: int        # rang du chunk dans le document
    metadata: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "text": self.text,
            "content": self.content,
            "source_doc": self.source_doc,
            "section": self.section,
            "position": self.position,
            "metadata": self.metadata,
        }

    @staticmethod
    def from_dict(d: dict) -> "Chunk":
        return Chunk(**d)


def split_sentences(text: str) -> list[str]:
    """Découpe un paragraphe en phrases (heuristique adaptée au français)."""
    text = text.strip()
    if not text:
        return []
    parts = _SENTENCE_SPLIT_RE.split(text)
    return [p.strip() for p in parts if p.strip()]


def _make_chunk_id(source_doc: str, position: int, content: str) -> str:
    digest = hashlib.sha1(content.encode("utf-8")).hexdigest()[:10]
    return f"{source_doc}::{position:03d}::{digest}"


def _pack_sentences(
    sentences: list[str],
    chunk_size: int,
    overlap_sentences: int,
) -> list[list[str]]:
    """Regroupe des phrases en fenêtres de ~chunk_size caractères."""
    windows: list[list[str]] = []
    current: list[str] = []
    current_len = 0

    for sentence in sentences:
        s_len = len(sentence) + 1
        # Une phrase seule plus longue que chunk_size devient son propre chunk.
        if current and current_len + s_len > chunk_size:
            windows.append(current)
            # Chevauchement : on repart des N dernières phrases.
            tail = current[-overlap_sentences:] if overlap_sentences else []
            current = list(tail)
            current_len = sum(len(s) + 1 for s in current)
        current.append(sentence)
        current_len += s_len

    if current:
        # Fusionner un reliquat trop court avec la fenêtre précédente.
        if windows and sum(len(s) for s in current) < MIN_CHUNK_SIZE:
            merged = windows[-1] + [
                s for s in current if s not in windows[-1]
            ]
            windows[-1] = merged
        else:
            windows.append(current)
    return windows


def chunk_markdown(
    text: str,
    source_doc: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap_sentences: int = DEFAULT_OVERLAP_SENTENCES,
) -> list[Chunk]:
    """
    Découpe un document Markdown en chunks alignés sur les phrases,
    en conservant le chemin de section de chaque fragment.
    """
    doc_title = source_doc
    section_path: list[str] = []
    chunks: list[Chunk] = []
    position = 0
    paragraph_buffer: list[str] = []

    def flush_paragraphs():
        nonlocal position
        if not paragraph_buffer:
            return
        block = " ".join(paragraph_buffer)
        paragraph_buffer.clear()
        sentences = split_sentences(block)
        if not sentences:
            return
        section = " > ".join([doc_title] + section_path) or doc_title
        for window in _pack_sentences(sentences, chunk_size, overlap_sentences):
            content = " ".join(window).strip()
            if not content:
                continue
            embedded = f"[{section}] {content}"
            chunks.append(
                Chunk(
                    chunk_id=_make_chunk_id(source_doc, position, content),
                    text=embedded,
                    content=content,
                    source_doc=source_doc,
                    section=section,
                    position=position,
                )
            )
            position += 1

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        header = _MD_HEADER_RE.match(line)
        if header:
            flush_paragraphs()
            level = len(header.group(1))
            title = header.group(2).strip()
            if level == 1:
                doc_title = title
                section_path = []
            else:
                section_path = section_path[: level - 2] + [title]
            continue
        if not line.strip():
            flush_paragraphs()
            continue
        # Les puces deviennent des phrases autonomes.
        cleaned = re.sub(r"^[-*•]\s+", "", line).strip()
        paragraph_buffer.append(cleaned)

    flush_paragraphs()
    return chunks


def serialize_record(
    kind: str,
    identifier: str,
    fields: dict,
    source_doc: str | None = None,
) -> Chunk:
    """
    Sérialise un enregistrement de base de données en "fiche" d'un chunk.

    Exemple de sortie :
        [Fiche filière LFI] Filière : Licence Informatique. Code : LFI.
        Niveau : L3. Département : Informatique.
    """
    label = f"Fiche {kind} {identifier}".strip()
    parts = [
        f"{key} : {value}."
        for key, value in fields.items()
        if value not in (None, "", [])
    ]
    content = " ".join(parts)
    source = source_doc or f"db_{kind}"
    return Chunk(
        chunk_id=_make_chunk_id(source, 0, f"{label}|{content}"),
        text=f"[{label}] {content}",
        content=content,
        source_doc=source,
        section=label,
        position=0,
        metadata={"kind": kind, "identifier": identifier},
    )
