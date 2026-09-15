"""
tests/test_scaling_and_ceiling.py
─────────────────────────────────────────────────────────────────────
Tests de l'étude de passage à l'échelle et du plafond de précision.

Ces deux artefacts répondent à des critiques de revue précises
(« le retriever tient-il à 10 000 chunks ? », « Precision@4 = 0.259
est mauvais ») : ils doivent donc rester corrects et régénérables.

Les tailles utilisées ici sont volontairement petites (le vrai rapport
va jusqu'à 20 000 chunks) pour que la suite reste rapide.
─────────────────────────────────────────────────────────────────────
"""
from django.test import SimpleTestCase

from apps.ai_agent.evaluation.runner import precision_ceiling
from apps.ai_agent.evaluation.scaling import (
    format_scaling_markdown,
    generate_distractors,
    generate_realistic_distractors,
    run_scaling_study,
)
from apps.ai_agent.rag.embeddings import TfidfBackend
from apps.ai_agent.rag.knowledge import load_corpus_chunks
from apps.ai_agent.rag.retriever import Retriever


class DistractorGenerationTest(SimpleTestCase):
    def test_distracteurs_markoviens_plausibles(self):
        real = load_corpus_chunks()
        distractors = generate_distractors(real, 20, seed=1)
        self.assertEqual(len(distractors), 20)
        for chunk in distractors:
            self.assertTrue(chunk.metadata.get("synthetic"))
            self.assertGreater(len(chunk.content.split()), 20)

    def test_distracteurs_realistes_autre_vocabulaire(self):
        distractors = generate_realistic_distractors(20, seed=1)
        self.assertEqual(len(distractors), 20)
        joined = " ".join(c.content for c in distractors).lower()
        # Vocabulaire d'un autre domaine : aucun terme du règlement.
        for forbidden in ("rattrapage", "défaillant", "jury"):
            self.assertNotIn(forbidden, joined)

    def test_deterministe_par_seed(self):
        a = generate_realistic_distractors(5, seed=3)
        b = generate_realistic_distractors(5, seed=3)
        self.assertEqual([c.content for c in a], [c.content for c in b])

    def test_ids_uniques(self):
        real = load_corpus_chunks()
        distractors = generate_distractors(real, 50, seed=2)
        ids = [c.chunk_id for c in distractors]
        self.assertEqual(len(ids), len(set(ids)))


class ScalingStudyTest(SimpleTestCase):
    def test_etude_produit_les_deux_regimes(self):
        study = run_scaling_study(sizes=(34, 150))
        self.assertIn("realistic", study["regimes"])
        self.assertIn("adversarial", study["regimes"])
        for rows in study["regimes"].values():
            self.assertEqual(len(rows), 2)
            for row in rows:
                self.assertIn("latency_ms", row)
                self.assertIn("quality", row)
                self.assertGreaterEqual(row["index_mb"], 0)
                self.assertTrue(row["sparse"])

    def test_corpus_reel_conserve_a_toutes_les_tailles(self):
        """Les chunks pertinents ne doivent jamais être altérés."""
        study = run_scaling_study(sizes=(34, 150))
        rows = study["regimes"]["realistic"]
        self.assertEqual(rows[0]["n_chunks"], study["n_real_chunks"])
        self.assertEqual(rows[1]["n_chunks"], 150)
        self.assertEqual(rows[1]["n_distractors"], 150 - study["n_real_chunks"])

    def test_qualite_tient_en_regime_realiste(self):
        """
        Propriété centrale : ajouter des documents d'AUTRES sujets ne doit
        pas dégrader le retrieval (c'est ce qui justifie la recherche
        exacte sans index ANN).
        """
        study = run_scaling_study(sizes=(34, 200))
        rows = study["regimes"]["realistic"]
        base_recall = rows[0]["quality"]["recall@4"]
        scaled_recall = rows[-1]["quality"]["recall@4"]
        self.assertGreaterEqual(scaled_recall, base_recall - 0.05)

    def test_markdown_rendu(self):
        study = run_scaling_study(sizes=(34, 150))
        lines = format_scaling_markdown(study)
        text = "\n".join(lines)
        self.assertIn("Passage à l'échelle", text)
        self.assertIn("Régime réaliste", text)
        self.assertIn("Régime adversarial", text)


class PrecisionCeilingTest(SimpleTestCase):
    def test_plafond_calcule_et_coherent(self):
        chunks = load_corpus_chunks()
        ceiling = precision_ceiling(chunks, top_k=4)
        self.assertEqual(ceiling["n_queries"], 27)
        self.assertGreater(ceiling["max_precision"], 0.0)
        self.assertLessEqual(ceiling["max_precision"], 1.0)
        # La majorité des requêtes n'a qu'un seul chunk pertinent :
        # c'est ce qui borne mécaniquement Precision@4.
        self.assertGreater(ceiling["queries_with_single_relevant"], 10)

    def test_precision_mesuree_sous_le_plafond(self):
        """La précision observée ne peut pas dépasser le plafond théorique."""
        from apps.ai_agent.evaluation.runner import evaluate_retriever

        chunks = load_corpus_chunks()
        retriever = Retriever.build(backend=TfidfBackend(), chunks=chunks)
        report = evaluate_retriever(retriever)
        ceiling = precision_ceiling(chunks, top_k=4)
        self.assertLessEqual(
            report["aggregated"]["precision@4"],
            ceiling["max_precision"] + 1e-9,
        )
