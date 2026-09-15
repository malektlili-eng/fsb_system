"""
apps/ai_agent/benchmarks/harness.py
─────────────────────────────────────────────────────────────────────
Harnais de benchmark de l'agent (alimente BENCHMARKS.md).

Deux modes, avec une PROVENANCE claire de chaque chiffre :

 • OFFLINE (défaut, aucun réseau, reproductible) :
   le fournisseur LLM est OfflineProvider ; on mesure ce qui est
   déterministe : latence de retrieval, latence des outils/BD,
   respect des comportements attendus (RAG déclenché ou non, bon
   outil appelé, succès), taille du contexte injecté, et la
   comparaison "avant/après" V1 vs V2 en tokens de prompt.

 • LIVE (--live, nécessite GROQ_API_KEY) :
   même harnais avec GroqProvider ; ajoute TTFT (time-to-first-token),
   latence totale LLM et longueur de réponse. Chaque exécution live
   est journalisée avec le modèle et l'horodatage.

Comparaison "avant vs après IA" (mesurée, pas déclarée) :
   V1 déversait TOUT le contexte en prompt (stats + toutes les
   fiches + tout le règlement). V2 n'injecte que les chunks au-dessus
   du seuil. Le harnais reconstruit les deux prompts pour chaque
   requête et compte les tokens (approximation mots×1.3) → colonne
   "réduction de contexte".
─────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import json
import statistics
import time
from pathlib import Path

from apps.ai_agent.llm.providers import OfflineProvider
from apps.ai_agent.orchestrator import FSBOrchestrator
from apps.ai_agent.rag.knowledge import load_corpus_chunks
from apps.ai_agent.rag.retriever import Retriever, get_retriever

from .queries import BENCHMARK_QUERIES


def _approx_tokens(text: str) -> int:
    """Approximation tokens ≈ mots × 1.3 (français, tokenizer BPE)."""
    return int(len(text.split()) * 1.3)


def _percentiles(values: list[float]) -> dict:
    if not values:
        return {"p50": None, "p95": None, "mean": None}
    ordered = sorted(values)
    return {
        "p50": round(ordered[len(ordered) // 2], 1),
        "p95": round(ordered[max(0, int(len(ordered) * 0.95) - 1)], 1),
        "mean": round(statistics.mean(values), 1),
    }


def _v1_full_context_tokens() -> int:
    """
    Reconstruit le contexte "V1" (tout le corpus déversé dans le
    prompt) et retourne sa taille en tokens approximés.
    """
    full_dump = "\n".join(chunk.text for chunk in load_corpus_chunks())
    return _approx_tokens(full_dump)


class BenchmarkHarness:
    """Exécute les 20 requêtes du benchmark et collecte les mesures."""

    def __init__(self, user, provider=None, retriever: Retriever | None = None):
        self.user = user
        self.provider = provider or OfflineProvider()
        self.retriever = retriever or get_retriever()
        self.mode = "live" if provider and provider.name == "groq" else "offline"

    def run_query(self, spec: dict) -> dict:
        """Exécute une requête à travers l'orchestrateur complet."""
        from apps.ai_agent.models import ConversationChat

        conversation = ConversationChat.objects.create(
            user=self.user, titre=f"bench-{spec['id']}"
        )
        orchestrator = FSBOrchestrator(
            self.user, provider=self.provider, retriever=self.retriever
        )

        events: list[dict] = []
        started = time.perf_counter()
        first_token_ms = None
        for line in orchestrator.process_stream(spec["query"], conversation.pk):
            event = json.loads(line)
            if event["type"] == "token" and first_token_ms is None:
                first_token_ms = (time.perf_counter() - started) * 1000
            events.append(event)
        total_ms = (time.perf_counter() - started) * 1000

        rag_events = [e for e in events if e["type"] == "rag"]
        tool_done = [e for e in events if e["type"] == "tool_done"]
        tokens = sum(1 for e in events if e["type"] == "token")
        errors = [e for e in events if e["type"] == "error"]

        rag_sources = rag_events[0]["data"] if rag_events else []
        retrieval_ms = rag_events[0]["latency_ms"] if rag_events else 0.0

        # Vérification des comportements attendus
        checks: dict[str, bool] = {}
        if spec.get("expect_rag"):
            checks["rag_déclenché"] = bool(rag_sources)
        if spec.get("expect_no_rag"):
            checks["rag_correctement_absent"] = not rag_sources
        if spec.get("expect_tool"):
            checks["bon_outil"] = any(
                e["data"] == spec["expect_tool"] for e in tool_done
            )
            if spec.get("expect_success"):
                checks["outil_succès"] = any(
                    e["data"] == spec["expect_tool"] and e.get("success")
                    for e in tool_done
                )
        checks["sans_erreur"] = not errors

        # Ablation de contexte : V2 (sélectif) vs V1 (tout déverser)
        retrieval = self.retriever.retrieve(spec["query"])
        v2_context_tokens = _approx_tokens(retrieval.context_block())

        return {
            "id": spec["id"],
            "category": spec["category"],
            "query": spec["query"],
            "mode": self.mode,
            "passed": all(checks.values()),
            "checks": checks,
            "latency": {
                "retrieval_ms": round(retrieval_ms, 1),
                "first_token_ms": (
                    round(first_token_ms, 1) if first_token_ms else None
                ),
                "total_ms": round(total_ms, 1),
            },
            "rag": {
                "sources_injected": len(rag_sources),
                "top_score": rag_sources[0]["score"] if rag_sources else None,
                "context_tokens_v2": v2_context_tokens,
            },
            "tools": [e["data"] for e in tool_done],
            "response_tokens": tokens,
        }

    def run_all(self) -> dict:
        rows = [self.run_query(spec) for spec in BENCHMARK_QUERIES]

        v1_tokens = _v1_full_context_tokens()
        v2_mean_tokens = statistics.mean(
            row["rag"]["context_tokens_v2"] for row in rows
        )

        summary = {
            "mode": self.mode,
            "provider": self.provider.name,
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "n_queries": len(rows),
            "passed": sum(1 for row in rows if row["passed"]),
            "pass_rate": round(
                sum(1 for row in rows if row["passed"]) / len(rows), 3
            ),
            "latency_retrieval_ms": _percentiles(
                [row["latency"]["retrieval_ms"] for row in rows]
            ),
            "latency_total_ms": _percentiles(
                [row["latency"]["total_ms"] for row in rows]
            ),
            "latency_first_token_ms": _percentiles(
                [
                    row["latency"]["first_token_ms"]
                    for row in rows
                    if row["latency"]["first_token_ms"] is not None
                ]
            ),
            "context_ablation": {
                "v1_full_dump_tokens": v1_tokens,
                "v2_selective_mean_tokens": round(v2_mean_tokens, 1),
                "reduction_pct": round(
                    (1 - v2_mean_tokens / v1_tokens) * 100, 1
                ),
            },
        }
        return {"summary": summary, "results": rows}


def write_benchmark_report(payload: dict, output_dir: str | Path = "reports") -> Path:
    """Écrit le journal JSON du benchmark."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    mode = payload["summary"]["mode"]
    path = output_dir / f"benchmark_results_{mode}.json"
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return path
