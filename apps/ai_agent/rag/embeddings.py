"""
apps/ai_agent/rag/embeddings.py
─────────────────────────────────────────────────────────────────────
Couche d'embeddings PLUGGABLE — c'est ici que le projet "possède"
sa couche modèle de retrieval (le LLM génératif reste, lui, un
composant interchangeable, voir apps/ai_agent/llm/providers.py).

Deux backends implémentent la même interface EmbeddingBackend :

 • TfidfBackend (défaut, toujours disponible)
   TF-IDF sur n-grammes de CARACTÈRES (3-5). Justification :
   - robuste à la morphologie française (inscrit/inscription/inscrire
     partagent leurs n-grammes) et aux fautes de frappe ;
   - aucun téléchargement de modèle → CI 100 % reproductible ;
   - sur un corpus < 10 000 chunks, la précision mesurée est
     compétitive (voir reports/rag_evaluation.md).

 • SentenceTransformerBackend (optionnel, recommandé en production)
   paraphrase-multilingual-MiniLM-L12-v2 (384 dims), exécuté
   LOCALEMENT — pas d'API externe pour les embeddings. Capture les
   reformulations sémantiques que TF-IDF manque
   ("étudiant recalé" ≈ "échec à la session principale").

Tous les vecteurs sont L2-normalisés : la similarité cosinus se
réduit à un produit scalaire dans le vector store.
─────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod

import numpy as np

logger = logging.getLogger(__name__)


class EmbeddingBackend(ABC):
    """Interface commune à tous les backends d'embeddings."""

    name: str = "abstract"

    @abstractmethod
    def fit(self, texts: list[str]) -> None:
        """Ajuste le backend sur le corpus (no-op pour les modèles pré-entraînés)."""

    @abstractmethod
    def encode(self, texts: list[str]) -> np.ndarray:
        """Encode une liste de textes → matrice (n, dim) L2-normalisée."""

    def encode_one(self, text: str) -> np.ndarray:
        return self.encode([text])[0]


def _l2_normalize(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


class TfidfBackend(EmbeddingBackend):
    """
    TF-IDF sur n-grammes de caractères (3-5) — backend par défaut.

    Sorties CREUSES (scipy CSR) : la dimension est la taille du
    vocabulaire de n-grammes (~6 500 chunks → ~10 000 dims à 5 000
    chunks). Densifier coûterait ~700 Mo à 20 000 chunks et provoque un
    OOM ; en creux, l'index tient en quelques dizaines de Mo car chaque
    chunk n'active qu'une fraction du vocabulaire. Le VectorStore fait
    la recherche cosinus directement en creux.

    SANS réduction de dimension par défaut : la projection LSA
    (TruncatedSVD) a été ÉVALUÉE puis retirée — sur ce corpus, elle
    lisse les similarités au point de détruire la séparation entre
    requêtes couvertes et hors-corpus (le rejet correct s'effondre,
    cf. ablation A5 de reports/rag_evaluation.md). Résultat négatif
    documenté ; l'option `svd_components` (qui produit alors des
    vecteurs denses) est conservée pour reproduire cette ablation.
    """

    name = "tfidf-char35"

    def __init__(self, svd_components: int | None = None):
        from sklearn.feature_extraction.text import TfidfVectorizer

        self._vectorizer = TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=(3, 5),
            sublinear_tf=True,
            min_df=1,
        )
        self._svd_components = svd_components
        self._svd = None
        self._fitted = False
        if svd_components:
            self.name = f"tfidf-char35-svd{svd_components}"

    def fit(self, texts: list[str]) -> None:
        matrix = self._vectorizer.fit_transform(texts)
        if self._svd_components:
            from sklearn.decomposition import TruncatedSVD

            n_components = min(
                self._svd_components,
                max(2, matrix.shape[1] - 1),
                max(2, matrix.shape[0] - 1),
            )
            self._svd = TruncatedSVD(n_components=n_components, random_state=42)
            self._svd.fit(matrix)
        self._fitted = True

    def encode(self, texts: list[str]):
        """Retourne une matrice CSR normalisée (ou dense si SVD actif)."""
        if not self._fitted:
            raise RuntimeError("TfidfBackend doit être fit() avant encode().")
        sparse = self._vectorizer.transform(texts)
        if self._svd is not None:
            dense = self._svd.transform(sparse)
            return _l2_normalize(np.asarray(dense, dtype=np.float32))
        from sklearn.preprocessing import normalize

        return normalize(sparse).astype(np.float32)

    def encode_one(self, text: str):
        """Vecteur d'une requête unique (CSR 1×dim, ou dense si SVD)."""
        vectors = self.encode([text])
        if hasattr(vectors, "toarray"):  # CSR : garder la forme creuse
            return vectors
        return vectors[0]


class SpacyVectorBackend(EmbeddingBackend):
    """
    Backend sémantique dense à partir de vecteurs de mots FRANÇAIS
    pré-entraînés (spaCy `fr_core_news_md`, 300 dims, 20 000 vecteurs).

    Pourquoi ce backend ?
    C'est le backend qui exécute réellement l'ablation A4 (sémantique vs
    lexical). Contrairement à TF-IDF, il place « recalé » et « échec »
    dans des régions voisines de l'espace, ce qui est exactement le
    mécanisme qui manque sur les requêtes reformulées.

    Mise en commun (pooling) : moyenne des vecteurs de mots PONDÉRÉE PAR
    L'IDF du corpus. La moyenne simple laisse les mots-outils (« de »,
    « la », « comment ») dominer la représentation ; pondérer par l'IDF
    redonne le poids aux mots porteurs de sens. L'IDF est appris sur le
    corpus au fit() ; les mots inconnus prennent l'IDF médian.

    Installation :
        pip install spacy
        pip install https://github.com/explosion/spacy-models/releases/\
download/fr_core_news_md-3.8.0/fr_core_news_md-3.8.0-py3-none-any.whl
    """

    name = "spacy-fr-core-news-md-idf"

    def __init__(self, model_name: str = "fr_core_news_md"):
        try:
            import spacy
        except ImportError as exc:  # pragma: no cover - dépend de l'env
            raise ImportError(
                "spaCy n'est pas installé (pip install spacy)."
            ) from exc
        try:
            self._nlp = spacy.load(
                model_name, disable=["parser", "ner", "tagger", "lemmatizer"]
            )
        except OSError as exc:  # pragma: no cover - dépend de l'env
            raise ImportError(
                f"Modèle spaCy '{model_name}' absent. Voir la docstring "
                "pour la commande d'installation."
            ) from exc
        if not self._nlp.vocab.vectors.shape[0]:  # pragma: no cover
            raise ImportError(
                f"Le modèle '{model_name}' ne contient pas de vecteurs "
                "(utiliser une variante _md ou _lg, pas _sm)."
            )
        self._dim = self._nlp.vocab.vectors.shape[1]
        self._idf: dict[str, float] = {}
        self._median_idf = 1.0

    def fit(self, texts: list[str]) -> None:
        """Apprend les poids IDF des tokens sur le corpus."""
        import math
        from collections import Counter

        doc_freq: Counter = Counter()
        for doc in self._nlp.pipe(texts, batch_size=64):
            seen = {t.lower_ for t in doc if t.is_alpha}
            doc_freq.update(seen)
        n_docs = max(len(texts), 1)
        self._idf = {
            token: math.log((1 + n_docs) / (1 + freq)) + 1.0
            for token, freq in doc_freq.items()
        }
        if self._idf:
            self._median_idf = float(np.median(list(self._idf.values())))

    def _encode_doc(self, doc) -> np.ndarray:
        vectors, weights = [], []
        for token in doc:
            if not token.is_alpha or not token.has_vector:
                continue
            vectors.append(token.vector)
            weights.append(self._idf.get(token.lower_, self._median_idf))
        if not vectors:
            return np.zeros(self._dim, dtype=np.float32)
        matrix = np.asarray(vectors, dtype=np.float32)
        weight_vec = np.asarray(weights, dtype=np.float32).reshape(-1, 1)
        return (matrix * weight_vec).sum(axis=0) / weight_vec.sum()

    def encode(self, texts: list[str]) -> np.ndarray:
        vectors = [
            self._encode_doc(doc)
            for doc in self._nlp.pipe(texts, batch_size=64)
        ]
        return _l2_normalize(np.asarray(vectors, dtype=np.float32))


class HybridDenseSparseBackend(EmbeddingBackend):
    """
    Concaténation pondérée d'un backend dense sémantique (spaCy) et du
    backend lexical (TF-IDF char-ngrams), chaque partie L2-normalisée
    puis pondérée par `dense_weight` / (1 - dense_weight).

    Motivation (issue de l'ablation A4) : le dense rattrape les
    reformulations, le lexical garde la précision sur les termes exacts
    (numéros, codes, intitulés d'articles). La concaténation permet à la
    similarité cosinus de combiner les deux signaux en une seule
    recherche, sans second passage de reranking.
    """

    name = "hybrid-spacy+tfidf"

    def __init__(self, dense_weight: float = 0.5):
        self.dense_weight = dense_weight
        self._dense = SpacyVectorBackend()
        self._sparse = TfidfBackend()
        self.name = f"hybrid-spacy+tfidf-w{dense_weight}"

    def fit(self, texts: list[str]) -> None:
        self._dense.fit(texts)
        self._sparse.fit(texts)

    def encode(self, texts: list[str]) -> np.ndarray:
        dense = self._dense.encode(texts) * self.dense_weight
        sparse = self._sparse.encode(texts)
        # TfidfBackend renvoie du CSR : on densifie ICI uniquement, car
        # la concaténation hybride produit de toute façon un vecteur
        # dense. Ce backend vise la qualité, pas le passage à l'échelle
        # (voir l'étude de scaling : le défaut TF-IDF reste creux).
        if hasattr(sparse, "toarray"):
            sparse = sparse.toarray()
        sparse = np.asarray(sparse, dtype=np.float32) * (1.0 - self.dense_weight)
        return _l2_normalize(np.hstack([dense, sparse]).astype(np.float32))


class SentenceTransformerBackend(EmbeddingBackend):
    """
    Backend sémantique via sentence-transformers, exécuté localement.

    Nécessite : pip install sentence-transformers
    Modèle par défaut : paraphrase-multilingual-MiniLM-L12-v2
    (multilingue, bon rapport qualité/latence pour le français).

    Note : ce backend requiert le téléchargement des poids depuis
    HuggingFace au premier usage. Lorsque le réseau n'est pas
    disponible, `SpacyVectorBackend` fournit une alternative sémantique
    pré-entraînée dont les poids sont installables via pip.
    """

    name = "st-multilingual-minilm-l12-v2"

    def __init__(self, model_name: str = "paraphrase-multilingual-MiniLM-L12-v2"):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - dépend de l'env
            raise ImportError(
                "sentence-transformers n'est pas installé. "
                "Installez-le (pip install sentence-transformers) ou "
                "utilisez TfidfBackend."
            ) from exc
        try:
            self._model = SentenceTransformer(model_name)
        except Exception as exc:  # pragma: no cover - dépend du réseau
            raise ImportError(
                f"Poids '{model_name}' indisponibles (réseau ?) : {exc}"
            ) from exc
        self.name = f"st-{model_name}"

    def fit(self, texts: list[str]) -> None:
        # Modèle pré-entraîné : rien à ajuster sur le corpus.
        return None

    def encode(self, texts: list[str]) -> np.ndarray:
        vectors = self._model.encode(
            texts, normalize_embeddings=True, show_progress_bar=False
        )
        return np.asarray(vectors, dtype=np.float32)


def get_backend(name: str | None = None) -> EmbeddingBackend:
    """
    Fabrique de backend, pilotée par settings.RAG_EMBEDDING_BACKEND.

    Valeurs : "tfidf" (défaut) | "spacy" | "hybrid" | "sentence-transformers".
    Retombe sur TF-IDF si un backend sémantique est demandé mais
    indisponible (comportement journalisé, jamais silencieux).
    """
    if name is None:
        try:
            from django.conf import settings

            name = getattr(settings, "RAG_EMBEDDING_BACKEND", "tfidf")
        except Exception:
            name = "tfidf"

    semantic_backends = {
        "spacy": SpacyVectorBackend,
        "hybrid": HybridDenseSparseBackend,
        "sentence-transformers": SentenceTransformerBackend,
    }
    if name in semantic_backends:
        try:
            return semantic_backends[name]()
        except ImportError as exc:
            logger.warning(
                "Backend '%s' indisponible (%s) — repli sur TfidfBackend.",
                name,
                exc,
            )
            return TfidfBackend()
    return TfidfBackend()
