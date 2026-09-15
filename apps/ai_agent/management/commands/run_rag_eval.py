"""
Commande : python manage.py run_rag_eval [--output-dir reports]
Évalue le retrieval sur le gold set (30 requêtes annotées), exécute
les ablations A1-A4 et écrit :
  reports/rag_evaluation.md    (rapport lisible)
  reports/rag_evaluation.json  (journal complet)
Aucun appel réseau : < 1 minute, reproductible en CI.
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Évalue le retrieval RAG sur le gold set et écrit les rapports."

    def add_arguments(self, parser):
        parser.add_argument("--output-dir", default="reports")
        parser.add_argument(
            "--no-scaling",
            action="store_true",
            help="Ignore l'étude de passage à l'échelle (plus rapide).",
        )

    def handle(self, *args, **options):
        from apps.ai_agent.evaluation.runner import write_reports

        md_path, json_path = write_reports(
            options["output_dir"], include_scaling=not options["no_scaling"]
        )
        self.stdout.write(self.style.SUCCESS(f"Rapport : {md_path}"))
        self.stdout.write(self.style.SUCCESS(f"Journal : {json_path}"))
