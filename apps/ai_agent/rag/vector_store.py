"""
apps/ai_agent/rag/vector_store.py
─────────────────────────────────────────────────────────────────────
Vector store à recherche EXACTE, persisté sur disque.

Supporte DEUX représentations, avec la même interface :

 • DENSE (numpy)  — backends à faible dimension (spaCy 300d, hybride,
   sentence-transformers 384d). Produit matriciel classique.

 • SPARSE (scipy CSR) — backend TF-IDF char-ngrams, dont la dimension
   est la taille du vocabulaire (~6 500 à 34 chunks, ~10 000 à 5 000
   chunks). Densifier serait une faute : à 20 000 chunks, la matrice
   dense pèserait ~700 Mo (et provoque un OOM), alors que la matrice
   creuse tient en ~50 Mo car chaque chunk n'active qu'une fraction
   du vocabulaire. La recherche cosinus se fait directement en creux.
   Ce choix est ce qui permet au retriever de tenir à 20 000 chunks —
   voir l'étude de passage à l'échelle (reports/rag_evaluation.md).

Pourquoi pas FAISS / pgvector ?
 - En dessous de ~100 000 vecteurs, la recherche exacte reste plus
   rapide qu'un index ANN à construire, avec un rappel de 100 % et une
   dépendance binaire en moins. L'étude de scaling mesure ce seuil.
 - L'interface (add / search / save / load) est celle d'un store
   classique : brancher FAISS plus tard ne touche que cette classe.

Persistance : vectors.npz (dense) ou vectors_sparse.npz (CSR) +
chunks.jsonl (métadonnées lisibles) + meta.json (backend, date).
─────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import scipy.sparse as sp

from .chunking import Chunk


class VectorStore:
    """Index vectoriel en mémoire (dense ou creux) avec persistance."""

    def __init__(self):
        self._vectors = None  # np.ndarray (n, dim) ou sp.csr_matrix
        self._chunks: list[Chunk] = []
        self.meta: dict = {}

    # ─── Construction ────────────────────────────────────────────────

    @property
    def is_sparse(self) -> bool:
        return sp.issparse(self._vectors)

    def add(self, chunks: list[Chunk], vectors) -> None:
        if len(chunks) != vectors.shape[0]:
            raise ValueError(
                f"{len(chunks)} chunks mais {vectors.shape[0]} vecteurs."
            )
        if sp.issparse(vectors):
            vectors = vectors.tocsr().astype(np.float32)
            self._vectors = (
                vectors
                if self._vectors is None
                else sp.vstack([self._vectors, vectors]).tocsr()
            )
        else:
            vectors = np.asarray(vectors, dtype=np.float32)
            self._vectors = (
                vectors
                if self._vectors is None
                else np.vstack([self._vectors, vectors])
            )
        self._chunks.extend(chunks)

    def __len__(self) -> int:
        return len(self._chunks)

    @property
    def chunks(self) -> list[Chunk]:
        return list(self._chunks)

    def nbytes(self) -> int:
        """Empreinte mémoire de l'index (pour l'étude de scaling)."""
        if self._vectors is None:
            return 0
        if self.is_sparse:
            v = self._vectors
            return int(v.data.nbytes + v.indices.nbytes + v.indptr.nbytes)
        return int(self._vectors.nbytes)

    # ─── Recherche ───────────────────────────────────────────────────

    def search(
        self,
        query_vector,
        top_k: int = 4,
        min_score: float = 0.0,
    ) -> list[tuple[Chunk, float]]:
        """
        Similarité cosinus (produit scalaire sur vecteurs normalisés).
        Fonctionne à l'identique en dense et en creux.
        """
        if self._vectors is None or not len(self._chunks):
            return []

        if self.is_sparse:
            query = query_vector
            if not sp.issparse(query):
                query = sp.csr_matrix(np.asarray(query, dtype=np.float32))
            query = query.reshape(1, -1) if query.shape[0] != 1 else query
            scores = np.asarray((self._vectors @ query.T).todense()).ravel()
        else:
            query = np.asarray(query_vector, dtype=np.float32).reshape(-1)
            scores = self._vectors @ query

        top_k = min(top_k, len(self._chunks))
        top_idx = np.argpartition(-scores, top_k - 1)[:top_k]
        top_idx = top_idx[np.argsort(-scores[top_idx])]
        return [
            (self._chunks[i], float(scores[i]))
            for i in top_idx
            if scores[i] >= min_score
        ]

    # ─── Persistance ─────────────────────────────────────────────────

    def save(self, directory: str | Path, backend_name: str = "") -> None:
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        if self._vectors is None:
            raise RuntimeError("Store vide : rien à sauvegarder.")
        if self.is_sparse:
            sp.save_npz(directory / "vectors_sparse.npz", self._vectors)
        else:
            np.savez_compressed(directory / "vectors.npz", vectors=self._vectors)
        with open(directory / "chunks.jsonl", "w", encoding="utf-8") as fh:
            for chunk in self._chunks:
                fh.write(json.dumps(chunk.as_dict(), ensure_ascii=False) + "\n")
        self.meta = {
            "backend": backend_name,
            "n_chunks": len(self._chunks),
            "dim": int(self._vectors.shape[1]),
            "sparse": self.is_sparse,
            "index_bytes": self.nbytes(),
            "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        with open(directory / "meta.json", "w", encoding="utf-8") as fh:
            json.dump(self.meta, fh, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, directory: str | Path) -> "VectorStore":
        directory = Path(directory)
        store = cls()
        sparse_path = directory / "vectors_sparse.npz"
        if sparse_path.exists():
            store._vectors = sp.load_npz(sparse_path).tocsr().astype(np.float32)
        else:
            data = np.load(directory / "vectors.npz")
            store._vectors = np.asarray(data["vectors"], dtype=np.float32)
        with open(directory / "chunks.jsonl", encoding="utf-8") as fh:
            store._chunks = [
                Chunk.from_dict(json.loads(line)) for line in fh if line.strip()
            ]
        meta_path = directory / "meta.json"
        if meta_path.exists():
            store.meta = json.loads(meta_path.read_text(encoding="utf-8"))
        return store

    @staticmethod
    def exists(directory: str | Path) -> bool:
        directory = Path(directory)
        has_vectors = (directory / "vectors.npz").exists() or (
            directory / "vectors_sparse.npz"
        ).exists()
        return has_vectors and (directory / "chunks.jsonl").exists()
