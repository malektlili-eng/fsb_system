"""
tests/test_evaluation_benchmarks.py
─────────────────────────────────────────────────────────────────────
Tests du runner d'évaluation et du harnais de benchmark : ces
artefacts font partie du contrat du projet (BENCHMARKS.md,
reports/rag_evaluation.md doivent rester générables).
─────────────────────────────────────────────────────────────────────
"""
import json
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai_agent.benchmarks.harness import (
    BenchmarkHarness,
    write_benchmark_report,
)
from apps.ai_agent.benchmarks.queries import BENCHMARK_QUERIES
from apps.ai_agent.evaluation.runner import evaluate_retriever
from apps.ai_agent.llm.providers import OfflineProvider
from apps.ai_agent.rag.embeddings import TfidfBackend
from apps.ai_agent.rag.knowledge import load_corpus_chunks
from apps.ai_agent.rag.retriever import Retriever

User = get_user_model()


def _retriever():
    if not hasattr(_retriever, "_cache"):
        _retriever._cache = Retriever.build(
            backend=TfidfBackend(), chunks=load_corpus_chunks()
        )
    return _retriever._cache


class EvaluateRetrieverTest(TestCase):
    def test_rapport_contient_les_champs_attendus(self):
        report = evaluate_retriever(_retriever())
        self.assertEqual(report["n_queries"], 30)
        agg = report["aggregated"]
        for key in ("hit@4", "recall@4", "precision@4", "mrr", "ndcg@4"):
            self.assertIn(key, agg)
            self.assertGreaterEqual(agg[key], 0.0)
            self.assertLessEqual(agg[key], 1.0)
        self.assertIsNotNone(report["correct_rejection_rate"])
        self.assertIn("p50", report["latency_ms"])

    def test_qualite_minimale_du_retrieval(self):
        """Garde-fou anti-régression : le retrieval ne doit pas
        s'effondrer silencieusement (seuils volontairement prudents)."""
        report = evaluate_retriever(_retriever())
        agg = report["aggregated"]
        self.assertGreaterEqual(agg["recall@4"], 0.60)
        self.assertGreaterEqual(agg["mrr"], 0.60)
        self.assertGreaterEqual(report["correct_rejection_rate"], 0.60)


class BenchmarkQueriesTest(TestCase):
    def test_20_requetes_reparties(self):
        self.assertEqual(len(BENCHMARK_QUERIES), 20)
        categories = {}
        for query in BENCHMARK_QUERIES:
            categories[query["category"]] = (
                categories.get(query["category"], 0) + 1
            )
        self.assertEqual(categories["connaissance"], 8)
        self.assertEqual(categories["action"], 6)
        self.assertEqual(categories["statistiques"], 3)
        self.assertEqual(categories["limite"], 3)

    def test_ids_uniques(self):
        ids = [query["id"] for query in BENCHMARK_QUERIES]
        self.assertEqual(len(ids), len(set(ids)))


class BenchmarkHarnessTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            username="bench_admin", password="x", role="admin",
            first_name="Bench", last_name="Admin",
        )
        from apps.administration.models import Departement, Etudiant, Filiere

        dept = Departement.objects.create(nom="informatique")
        filiere = Filiere.objects.create(
            nom="Licence Bench", code="LI-BENCH", departement=dept,
            niveau="L3", type_formation="licence",
        )
        Etudiant.objects.create(
            nom="BENALI", prenom="Test", numero_etudiant="ETU-BENCH-01",
            filiere=filiere, annee_inscription=2025,
        )

    def test_run_query_verifie_les_comportements(self):
        harness = BenchmarkHarness(
            self.admin, provider=OfflineProvider(), retriever=_retriever()
        )
        knowledge = next(q for q in BENCHMARK_QUERIES if q["id"] == "K1")
        row = harness.run_query(knowledge)
        self.assertTrue(row["checks"]["rag_déclenché"])
        self.assertTrue(row["passed"])
        self.assertGreaterEqual(row["rag"]["sources_injected"], 1)

        action = next(q for q in BENCHMARK_QUERIES if q["id"] == "A1")
        row = harness.run_query(action)
        self.assertTrue(row["checks"]["bon_outil"])
        self.assertTrue(row["checks"]["outil_succès"])

    def test_run_all_et_rapport_json(self):
        harness = BenchmarkHarness(
            self.admin, provider=OfflineProvider(), retriever=_retriever()
        )
        payload = harness.run_all()
        summary = payload["summary"]
        self.assertEqual(summary["n_queries"], 20)
        self.assertEqual(summary["mode"], "offline")
        # L'ablation de contexte V1 vs V2 doit montrer une réduction
        self.assertGreater(
            summary["context_ablation"]["v1_full_dump_tokens"],
            summary["context_ablation"]["v2_selective_mean_tokens"],
        )
        self.assertGreater(summary["context_ablation"]["reduction_pct"], 50)

        with tempfile.TemporaryDirectory() as tmp_dir:
            path = write_benchmark_report(payload, tmp_dir)
            self.assertTrue(Path(path).exists())
            reloaded = json.loads(Path(path).read_text(encoding="utf-8"))
            self.assertEqual(reloaded["summary"]["n_queries"], 20)

    def test_taux_de_conformite_offline(self):
        """En mode offline les comportements attendus doivent tous passer
        (retrieval déterministe + routage d'outils déterministe)."""
        harness = BenchmarkHarness(
            self.admin, provider=OfflineProvider(), retriever=_retriever()
        )
        payload = harness.run_all()
        failed = [r["id"] for r in payload["results"] if not r["passed"]]
        self.assertEqual(
            failed, [], f"Requêtes non conformes en offline : {failed}"
        )
