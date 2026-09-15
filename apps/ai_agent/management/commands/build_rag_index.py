"""
Commande : python manage.py build_rag_index [--no-db-entities]
Construit (ou reconstruit) l'index vectoriel RAG et le persiste dans
settings.RAG_INDEX_DIR. À relancer après modification du corpus
(rag/corpus/*.md) ou des entités indexées.
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Construit et persiste l'index vectoriel du RAG."

    def add_arguments(self, parser):
        parser.add_argument(
            "--no-db-entities",
            action="store_true",
            help="N'indexe que les documents (pas les fiches entités BD).",
        )

    def handle(self, *args, **options):
        from django.conf import settings

        from apps.ai_agent.rag.retriever import Retriever, reset_retriever

        retriever = Retriever.build(
            include_db_entities=not options["no_db_entities"]
        )
        retriever.save(settings.RAG_INDEX_DIR)
        reset_retriever()
        self.stdout.write(
            self.style.SUCCESS(
                f"Index RAG : {len(retriever.store)} chunks "
                f"(backend {retriever.backend.name}) → {settings.RAG_INDEX_DIR}"
            )
        )
