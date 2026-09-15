"""
tests/test_rag_retrieval.py
─────────────────────────────────────────────────────────────────────
Tests du vector store, du retriever et des métriques d'évaluation.
─────────────────────────────────────────────────────────────────────
"""
import tempfile

from django.test import SimpleTestCase, TestCase

from apps.ai_agent.evaluation.gold_set import GOLD_QUERIES, is_relevant
from apps.ai_agent.evaluation.metrics import (
    aggregate,
    hit_at_k,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)
from apps.ai_agent.rag.embeddings import TfidfBackend
from apps.ai_agent.rag.knowledge import load_corpus_chunks
from apps.ai_agent.rag.retriever import Retriever
from apps.ai_agent.rag.vector_store import VectorStore


class VectorStoreTest(SimpleTestCase):
    def _make_retriever(self):
        chunks = load_corpus_chunks()
        return Retriever.build(backend=TfidfBackend(), chunks=chunks)

    def test_add_incoherent_leve_erreur(self):
        import numpy as np

        store = VectorStore()
        chunks = load_corpus_chunks()[:2]
        with self.assertRaises(ValueError):
            store.add(chunks, np.zeros((3, 4), dtype="float32"))

    def test_persistance_round_trip(self):
        """save() puis load() restituent le même index (mêmes résultats)."""
        retriever = self._make_retriever()
        query = "Comment justifier une absence ?"
        before = retriever.retrieve(query)

        with tempfile.TemporaryDirectory() as tmp_dir:
            retriever.save(tmp_dir)
            self.assertTrue(VectorStore.exists(tmp_dir))
            reloaded = Retriever.from_index(tmp_dir, backend=TfidfBackend())
            after = reloaded.retrieve(query)

        self.assertEqual(len(retriever.store), len(reloaded.store))
        self.assertEqual(
            [c.chunk_id for c, _ in before.chunks],
            [c.chunk_id for c, _ in after.chunks],
        )

    def test_persistance_creuse_conserve_la_representation(self):
        """L'index TF-IDF est creux et le reste après un aller-retour."""
        from pathlib import Path

        retriever = self._make_retriever()
        self.assertTrue(retriever.store.is_sparse)

        with tempfile.TemporaryDirectory() as tmp_dir:
            retriever.save(tmp_dir)
            # Le fichier creux est écrit, pas le dense.
            self.assertTrue((Path(tmp_dir) / "vectors_sparse.npz").exists())
            self.assertFalse((Path(tmp_dir) / "vectors.npz").exists())
            reloaded = VectorStore.load(tmp_dir)
            self.assertTrue(reloaded.is_sparse)
            self.assertEqual(reloaded.meta["sparse"], True)
            self.assertGreater(reloaded.meta["index_bytes"], 0)

    def test_persistance_dense_round_trip(self):
        """Un backend dense (SVD) écrit et relit vectors.npz."""
        from pathlib import Path

        chunks = load_corpus_chunks()
        retriever = Retriever.build(
            backend=TfidfBackend(svd_components=16), chunks=chunks
        )
        self.assertFalse(retriever.store.is_sparse)
        with tempfile.TemporaryDirectory() as tmp_dir:
            retriever.save(tmp_dir)
            self.assertTrue((Path(tmp_dir) / "vectors.npz").exists())
            reloaded = VectorStore.load(tmp_dir)
            self.assertFalse(reloaded.is_sparse)
            self.assertEqual(len(reloaded), len(retriever.store))

    def test_nbytes_creux_plus_petit_que_dense(self):
        """L'empreinte creuse est très inférieure à l'équivalent dense."""
        retriever = self._make_retriever()
        sparse_bytes = retriever.store.nbytes()
        shape = retriever.store._vectors.shape
        dense_bytes = shape[0] * shape[1] * 4
        self.assertLess(sparse_bytes, dense_bytes)

    def test_store_vide_retourne_liste_vide(self):
        import numpy as np

        store = VectorStore()
        self.assertEqual(store.search(np.zeros(4), top_k=3), [])


class RetrieverTest(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.retriever = Retriever.build(
            backend=TfidfBackend(), chunks=load_corpus_chunks()
        )

    def test_requete_couverte_retourne_la_bonne_section(self):
        result = self.retriever.retrieve("Comment justifier une absence ?")
        self.assertGreater(len(result.chunks), 0)
        top_chunk = result.chunks[0][0]
        self.assertTrue(
            "Absence" in top_chunk.section or "Article 4" in top_chunk.section,
            f"Section inattendue : {top_chunk.section}",
        )

    def test_requete_hors_corpus_rejetee_par_le_seuil(self):
        result = self.retriever.retrieve("Comment configurer un serveur Minecraft ?")
        self.assertEqual(
            result.chunks, [],
            "Une requête hors-corpus ne doit injecter aucune source.",
        )

    def test_context_block_numerote_les_sources(self):
        result = self.retriever.retrieve("Quelle est la durée du stage de licence ?")
        block = result.context_block()
        self.assertIn("[S1]", block)

    def test_as_event_expose_scores_et_latence(self):
        result = self.retriever.retrieve("session de rattrapage")
        event = result.as_event()
        self.assertEqual(event["type"], "rag")
        self.assertGreaterEqual(event["latency_ms"], 0)
        if event["data"]:
            self.assertIn("score", event["data"][0])
            self.assertIn("section", event["data"][0])

    def test_scores_tries_decroissants(self):
        result = self.retriever.retrieve("pondération contrôle continu examen")
        scores = [score for _, score in result.chunks]
        self.assertEqual(scores, sorted(scores, reverse=True))


class RetrieverSingletonTest(TestCase):
    """get_retriever construit, persiste puis réutilise l'index."""

    def test_get_retriever_et_reset(self):
        from django.test import override_settings
        import tempfile

        from apps.ai_agent.rag import retriever as retriever_module

        with tempfile.TemporaryDirectory() as tmp_dir:
            with override_settings(RAG_INDEX_DIR=tmp_dir):
                retriever_module.reset_retriever()
                first = retriever_module.get_retriever()
                self.assertGreater(len(first.store), 0)
                # Deuxième appel : même instance (singleton)
                second = retriever_module.get_retriever()
                self.assertIs(first, second)
                # L'index a été persisté
                self.assertTrue(VectorStore.exists(tmp_dir))
                retriever_module.reset_retriever()


class MetricsTest(SimpleTestCase):
    """Vérification des métriques IR sur des cas calculés à la main."""

    def test_hit_recall_precision(self):
        flags = [False, True, True, False]
        self.assertEqual(hit_at_k(flags, 4), 1.0)
        self.assertEqual(hit_at_k(flags, 1), 0.0)
        self.assertEqual(recall_at_k(flags, 4, total_relevant=4), 0.5)
        self.assertEqual(precision_at_k(flags, 4), 0.5)

    def test_reciprocal_rank(self):
        self.assertEqual(reciprocal_rank([False, True, False]), 0.5)
        self.assertEqual(reciprocal_rank([True]), 1.0)
        self.assertEqual(reciprocal_rank([False, False]), 0.0)

    def test_ndcg_calcul_manuel(self):
        import math

        # Pertinent en rang 2 sur 1 pertinent total :
        # DCG = 1/log2(3) ; IDCG = 1/log2(2) = 1
        flags = [False, True, False, False]
        expected = (1 / math.log2(3)) / 1.0
        self.assertAlmostEqual(ndcg_at_k(flags, 4, 1), expected, places=6)

    def test_ndcg_parfait_egale_un(self):
        self.assertEqual(ndcg_at_k([True, True], 4, 2), 1.0)

    def test_aggregate_moyenne(self):
        rows = [{"m": 1.0}, {"m": 0.0}]
        self.assertEqual(aggregate(rows), {"m": 0.5})


class GoldSetIntegrityTest(SimpleTestCase):
    """Le gold set doit rester cohérent avec le corpus."""

    def test_30_requetes_dont_3_hors_corpus(self):
        self.assertEqual(len(GOLD_QUERIES), 30)
        hors = [q for q in GOLD_QUERIES if q["category"] == "hors-corpus"]
        self.assertEqual(len(hors), 3)

    def test_chaque_jugement_matche_au_moins_un_chunk(self):
        """Chaque requête annotée a ≥ 1 chunk pertinent dans le corpus
        (sinon le gold set référence une section disparue)."""
        chunks = load_corpus_chunks()
        for item in GOLD_QUERIES:
            if item["category"] == "hors-corpus":
                continue
            matches = [c for c in chunks if is_relevant(c, item["relevant"])]
            self.assertGreater(
                len(matches), 0,
                f"Aucun chunk pertinent pour : {item['query']}",
            )


class DomainPortabilityTest(SimpleTestCase):
    """
    Le moteur RAG est domaine-agnostique : pointer le corpus vers un
    autre domaine (ici support e-commerce) suffit à le faire fonctionner,
    SANS changement de code. Ce test verrouille cette propriété, qui
    répond à la critique « domaine interne → impact limité » : la valeur
    d'ingénierie (chunking + embeddings + index + seuil) est réutilisable.
    """

    ECOMMERCE_CORPUS = {
        "retours.md": (
            "# Politique de retour\n"
            "## Délai de retour\n"
            "Vous disposez de 30 jours après réception pour retourner un "
            "article non porté. Le remboursement est effectué sous 14 jours "
            "ouvrables sur le moyen de paiement initial.\n"
            "## Frais de port\n"
            "Les frais de retour sont gratuits au-dessus de 50 euros.\n"
        ),
        "livraison.md": (
            "# Livraison\n"
            "## Délais\n"
            "La livraison standard prend 3 à 5 jours ouvrables. "
            "La livraison express est en 24 heures.\n"
            "## Suivi\n"
            "Un numéro de suivi est envoyé par email dès l'expédition.\n"
        ),
    }

    def _build_ecommerce_retriever(self, tmp_dir):
        from pathlib import Path

        for name, content in self.ECOMMERCE_CORPUS.items():
            Path(tmp_dir, name).write_text(content, encoding="utf-8")
        chunks = load_corpus_chunks(corpus_dir=tmp_dir)
        return Retriever.build(backend=TfidfBackend(), chunks=chunks), chunks

    def test_moteur_fonctionne_sur_domaine_ecommerce(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            retriever, chunks = self._build_ecommerce_retriever(tmp_dir)
            self.assertGreater(len(chunks), 0)

            result = retriever.retrieve(
                "Combien de temps pour me faire rembourser ?"
            )
            self.assertGreater(len(result.chunks), 0)
            self.assertIn("remboursement", result.chunks[0][0].content.lower())

    def test_rejet_hors_domaine_toujours_actif(self):
        """Le seuil de pertinence fonctionne quel que soit le domaine :
        une requête sans rapport avec le corpus n'injecte aucune source."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            retriever, _ = self._build_ecommerce_retriever(tmp_dir)
            result = retriever.retrieve(
                "photosynthèse chlorophylle plante verte"
            )
            self.assertEqual(
                result.chunks, [],
                "Une requête hors-domaine doit être rejetée par le seuil.",
            )
