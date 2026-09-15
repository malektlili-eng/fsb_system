"""
Commande : python manage.py run_benchmarks [--live] [--output-dir reports]

Exécute les 20 requêtes du benchmark (voir BENCHMARKS.md) à travers
l'orchestrateur complet et écrit reports/benchmark_results_<mode>.json.

  Mode OFFLINE (défaut) : OfflineProvider, aucun réseau, reproductible.
    Mesure : retrieval, outils/BD, comportements attendus, ablation
    de contexte V1 vs V2.

  Mode LIVE (--live) : GroqProvider, nécessite GROQ_API_KEY.
    Ajoute : TTFT, latence LLM totale, longueur des réponses réelles.

La commande utilise un utilisateur de benchmark dédié (rôle admin)
créé à la volée, et une base de données de travail : lancez-la de
préférence sur une base de démonstration (init_data).
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Exécute le benchmark de l'agent (20 requêtes) et écrit le journal JSON."

    def add_arguments(self, parser):
        parser.add_argument(
            "--live",
            action="store_true",
            help="Utilise le vrai LLM (Groq) au lieu du fournisseur offline.",
        )
        parser.add_argument("--output-dir", default="reports")

    def handle(self, *args, **options):
        from django.contrib.auth import get_user_model

        from apps.ai_agent.benchmarks.harness import (
            BenchmarkHarness,
            write_benchmark_report,
        )

        User = get_user_model()
        bench_user, _ = User.objects.get_or_create(
            username="benchmark_bot",
            defaults={"role": "admin", "first_name": "Bench", "last_name": "Bot"},
        )

        provider = None
        if options["live"]:
            from django.conf import settings

            if not settings.GROQ_API_KEY:
                self.stderr.write(
                    self.style.ERROR(
                        "GROQ_API_KEY manquante : le mode --live est impossible."
                    )
                )
                return
            from apps.ai_agent.llm.providers import GroqProvider

            provider = GroqProvider()

        harness = BenchmarkHarness(bench_user, provider=provider)
        self.stdout.write(f"Benchmark en mode {harness.mode}…")
        payload = harness.run_all()
        path = write_benchmark_report(payload, options["output_dir"])

        summary = payload["summary"]
        self.stdout.write(
            self.style.SUCCESS(
                f"{summary['passed']}/{summary['n_queries']} requêtes conformes "
                f"({summary['pass_rate'] * 100:.0f} %) — journal : {path}"
            )
        )
        self.stdout.write(
            "Contexte V1 (déversement complet) : "
            f"{summary['context_ablation']['v1_full_dump_tokens']} tokens ; "
            "V2 (sélectif, moyenne) : "
            f"{summary['context_ablation']['v2_selective_mean_tokens']} tokens "
            f"(réduction {summary['context_ablation']['reduction_pct']} %)."
        )
