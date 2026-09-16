"""
tests/test_views_and_commands.py
─────────────────────────────────────────────────────────────────────
Tests des vues secondaires de l'agent (métriques, historique) et des
commandes de gestion (build_rag_index, run_rag_eval, run_benchmarks),
plus le parsing du flux Groq (accumulation des tool calls partiels)
via un client mocké.
─────────────────────────────────────────────────────────────────────
"""
import json
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from tests.support import requires_groq_sdk

User = get_user_model()


class AgentSecondaryViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_user(
            username="views_admin", password="TestPass123!", role="admin",
        )
        self.scolarite = User.objects.create_user(
            username="views_scol", password="TestPass123!", role="scolarite",
        )
        self.client.login(username="views_admin", password="TestPass123!")

    def test_page_historique(self):
        from apps.ai_agent.models import ConversationChat

        ConversationChat.objects.create(user=self.admin, titre="Conv A")
        response = self.client.get(reverse("ai_agent:history"))
        self.assertEqual(response.status_code, 200)

    def test_clear_all_conversations(self):
        from apps.ai_agent.models import ConversationChat

        ConversationChat.objects.create(user=self.admin, titre="À vider")
        response = self.client.post(reverse("ai_agent:clear"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            ConversationChat.objects.filter(user=self.admin).count(), 0
        )

    def test_dashboard_metriques_admin(self):
        from apps.ai_agent.models import AgentMetric

        AgentMetric.objects.create(
            user=self.admin, question="Q", response_time_ms=1200,
            tokens_used=42, tool_called="chercher_etudiant",
            action_success=True,
        )
        response = self.client.get(reverse("ai_agent:metrics"))
        self.assertEqual(response.status_code, 200)

    def test_dashboard_metriques_refuse_scolarite(self):
        self.client.logout()
        self.client.login(username="views_scol", password="TestPass123!")
        response = self.client.get(reverse("ai_agent:metrics"))
        self.assertEqual(response.status_code, 403)

    def test_send_message_sans_cle_api_retourne_503_si_repli_desactive(self):
        """
        503 UNIQUEMENT quand le repli est explicitement désactivé.

        Ce test affirmait auparavant qu'une clé absente devait toujours
        produire un 503 — il verrouillait le bug qu'il était censé
        prévenir : la vue refusait de répondre alors que le repli
        déterministe était disponible. Le contrat correct distingue les
        deux cas.
        """
        with self.settings(GROQ_API_KEY="", LLM_FALLBACK_OFFLINE=False):
            response = self.client.post(
                reverse("ai_agent:send"),
                json.dumps({"message": "Bonjour", "conversation_id": None}),
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 503)

    def test_send_message_sans_cle_api_repond_si_repli_actif(self):
        with self.settings(GROQ_API_KEY="", LLM_FALLBACK_OFFLINE=True):
            response = self.client.post(
                reverse("ai_agent:send"),
                json.dumps({"message": "Bonjour", "conversation_id": None}),
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 200)

    def test_send_message_json_invalide_retourne_400(self):
        response = self.client.post(
            reverse("ai_agent:send"), "pas-du-json",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)


class ManagementCommandsTest(TestCase):
    def test_build_rag_index_persiste(self):
        from apps.ai_agent.rag.vector_store import VectorStore

        with tempfile.TemporaryDirectory() as tmp_dir:
            index_dir = Path(tmp_dir) / "idx"
            with self.settings(RAG_INDEX_DIR=index_dir):
                out = StringIO()
                call_command("build_rag_index", "--no-db-entities", stdout=out)
                self.assertIn("Index RAG", out.getvalue())
                # Le backend par défaut est creux : l'index est écrit en
                # vectors_sparse.npz. On vérifie le contrat du store plutôt
                # qu'un nom de fichier lié à la représentation.
                self.assertTrue(VectorStore.exists(index_dir))
                self.assertTrue((index_dir / "chunks.jsonl").exists())
                store = VectorStore.load(index_dir)
                self.assertTrue(store.is_sparse)
                self.assertGreater(len(store), 0)

    def test_run_rag_eval_ecrit_les_rapports(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            out = StringIO()
            call_command("run_rag_eval", "--output-dir", tmp_dir, stdout=out)
            self.assertTrue((Path(tmp_dir) / "rag_evaluation.md").exists())
            payload = json.loads(
                (Path(tmp_dir) / "rag_evaluation.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(payload["main"]["n_queries"], 30)
            ablation_names = {row["ablation"] for row in payload["ablations"]}
            self.assertIn("A1_chunk_size", ablation_names)
            self.assertIn("A5_svd_lsa", ablation_names)

    def test_run_benchmarks_offline(self):
        from apps.administration.models import Departement, Etudiant, Filiere

        dept = Departement.objects.create(nom="informatique")
        filiere = Filiere.objects.create(
            nom="Licence Cmd", code="LI-CMD", departement=dept,
            niveau="L3", type_formation="licence",
        )
        Etudiant.objects.create(
            nom="BENALI", prenom="Cmd", numero_etudiant="ETU-CMD-01",
            filiere=filiere, annee_inscription=2025,
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            out = StringIO()
            with self.settings(LLM_PROVIDER="offline"):
                call_command(
                    "run_benchmarks", "--output-dir", tmp_dir, stdout=out
                )
            report = Path(tmp_dir) / "benchmark_results_offline.json"
            self.assertTrue(report.exists())
            self.assertIn("requêtes conformes", out.getvalue())

    def test_run_benchmarks_live_sans_cle_echoue_proprement(self):
        err = StringIO()
        with self.settings(GROQ_API_KEY=""):
            call_command("run_benchmarks", "--live", stderr=err)
        self.assertIn("GROQ_API_KEY", err.getvalue())


class CoverageSplitCommandTest(TestCase):
    """
    La commande `coverage_split` produit la répartition honnête de la
    couverture par sous-système (réponse à la critique « 74 % global
    survend la couche CRUD »). Elle doit rester fonctionnelle et
    échouer proprement quand les données de couverture sont absentes.
    """

    def test_sans_fichier_de_donnees_message_clair(self):
        err = StringIO()
        with tempfile.TemporaryDirectory() as tmp_dir:
            call_command(
                "coverage_split",
                "--data-file", str(Path(tmp_dir) / "absent.coverage"),
                "--output-dir", tmp_dir,
                stderr=err,
            )
        self.assertIn("introuvable", err.getvalue())

    def test_genere_le_rapport_depuis_des_donnees_reelles(self):
        """
        On mesure réellement un petit module du projet avec coverage,
        puis on vérifie que la commande sait en tirer un rapport.
        """
        try:
            from coverage import Coverage
        except ImportError:  # pragma: no cover
            self.skipTest("coverage non installé")

        with tempfile.TemporaryDirectory() as tmp_dir:
            data_file = str(Path(tmp_dir) / "cov.data")
            cov = Coverage(data_file=data_file, source=["apps.ai_agent.rag"])
            cov.start()
            # Exécute du code réel du sous-système IA/RAG.
            from apps.ai_agent.rag.chunking import split_sentences

            split_sentences("Première phrase. Deuxième phrase.")
            cov.stop()
            cov.save()

            out = StringIO()
            call_command(
                "coverage_split",
                "--data-file", data_file,
                "--output-dir", tmp_dir,
                stdout=out,
            )
            report = Path(tmp_dir) / "coverage_split.md"
            self.assertTrue(report.exists())
            content = report.read_text(encoding="utf-8")
            self.assertIn("répartition par sous-système", content)
            self.assertIn("Agent IA & RAG", content)
            # Le tableau de synthèse et le détail par fichier sont présents.
            self.assertIn("| Sous-système |", content)
            self.assertIn("## Détail par fichier", content)

    def test_le_tableau_se_reconcilie_exactement(self):
        """
        Propriété critique : la somme des sous-systèmes DOIT égaler la
        ligne de total.

        Une version antérieure affichait 71 % en bas du tableau pendant
        que le README annonçait 78 %, sans que l'écart soit expliqué
        nulle part — les sous-systèmes nommés ne couvraient pas tout le
        code applicatif. Un relecteur qui ouvre les deux fichiers voit
        l'incohérence en quelques secondes. Ce test empêche la
        régression.
        """
        try:
            from coverage import Coverage
        except ImportError:  # pragma: no cover
            self.skipTest("coverage non installé")

        with tempfile.TemporaryDirectory() as tmp_dir:
            data_file = str(Path(tmp_dir) / "cov.data")
            cov = Coverage(data_file=data_file, source=["apps"])
            cov.start()
            from apps.ai_agent.rag.chunking import split_sentences

            split_sentences("Une phrase. Une autre.")
            cov.stop()
            cov.save()

            call_command(
                "coverage_split",
                "--data-file", data_file,
                "--output-dir", tmp_dir,
                stdout=StringIO(),
            )
            content = (Path(tmp_dir) / "coverage_split.md").read_text(
                encoding="utf-8"
            )

        # Extraire les lignes chiffrées du SEUL tableau de synthèse
        # (le rapport contient aussi un détail par fichier, de même
        # forme : le parser doit s'arrêter au premier titre suivant).
        summary = content.split("## Ce que ce total mesure")[0]

        def _num(cell: str) -> int | None:
            cleaned = cell.replace("*", "").replace("_", "").strip()
            return int(cleaned) if cleaned.isdigit() else None

        rows, total = [], None
        for line in summary.splitlines():
            if not line.startswith("|") or "Instructions" in line:
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) != 4:
                continue
            stmts, covered = _num(cells[1]), _num(cells[2])
            if stmts is None or covered is None:
                continue
            if "Total" in cells[0]:
                total = (stmts, covered)
            else:
                rows.append((stmts, covered))

        self.assertIsNotNone(total, "ligne de total absente du tableau")
        self.assertTrue(rows, "aucun sous-système dans le tableau")
        self.assertEqual(
            sum(r[0] for r in rows), total[0],
            "les instructions des sous-systèmes ne somment pas au total",
        )
        self.assertEqual(
            sum(r[1] for r in rows), total[1],
            "les instructions couvertes ne somment pas au total",
        )

    def test_porte_ia_rag_casse_le_build_si_non_franchie(self):
        """
        `--fail-under-ai` rend vérifiable la phrase « l'effort de test
        est concentré sur la couche IA/RAG » : ce n'est plus une
        affirmation du README mais une porte qui échoue.
        """
        try:
            from coverage import Coverage
        except ImportError:  # pragma: no cover
            self.skipTest("coverage non installé")

        with tempfile.TemporaryDirectory() as tmp_dir:
            data_file = str(Path(tmp_dir) / "cov.data")
            cov = Coverage(data_file=data_file, source=["apps.ai_agent.rag"])
            cov.start()
            from apps.ai_agent.rag.chunking import split_sentences

            split_sentences("Phrase.")
            cov.stop()
            cov.save()

            with self.assertRaises(SystemExit):
                call_command(
                    "coverage_split",
                    "--data-file", data_file,
                    "--output-dir", tmp_dir,
                    "--fail-under-ai", "99.9",
                    stdout=StringIO(),
                )


class GroqStreamParsingTest(TestCase):
    """
    Le parsing du flux Groq (deltas de texte + tool calls fragmentés
    sur plusieurs chunks) est la partie la plus fragile du fournisseur :
    on l'exerce avec un client mocké qui rejoue un flux réaliste.
    """

    def _fake_chunk(self, content=None, tool_calls=None):
        chunk = MagicMock()
        delta = MagicMock()
        delta.content = content
        delta.tool_calls = tool_calls
        chunk.choices = [MagicMock(delta=delta)]
        return chunk

    def _fake_tool_delta(self, index, call_id=None, name=None, arguments=None):
        tc = MagicMock()
        tc.index = index
        tc.id = call_id
        tc.function = MagicMock()
        tc.function.name = name
        tc.function.arguments = arguments
        return tc

    @requires_groq_sdk
    @patch("groq.Groq")
    def test_accumulation_tool_call_fragmente(self, MockGroq):
        from apps.ai_agent.llm.providers import (
            GroqProvider,
            TokenEvent,
            ToolCallEvent,
        )

        stream = [
            self._fake_chunk(content="Je vérifie"),
            self._fake_chunk(
                tool_calls=[
                    self._fake_tool_delta(
                        0, call_id="call_abc", name="chercher_etudiant",
                        arguments='{"que',
                    )
                ]
            ),
            self._fake_chunk(
                tool_calls=[
                    self._fake_tool_delta(0, arguments='ry": "BENALI"}')
                ]
            ),
        ]
        MockGroq.return_value.chat.completions.create.return_value = iter(
            stream
        )

        provider = GroqProvider(api_key="fake", model="fake-model")
        events = list(
            provider.stream_chat(
                [{"role": "user", "content": "Cherche BENALI"}],
                tools=[{"type": "function", "function": {"name": "x"}}],
            )
        )

        tokens = [e for e in events if isinstance(e, TokenEvent)]
        calls = [e for e in events if isinstance(e, ToolCallEvent)]
        self.assertEqual(tokens[0].text, "Je vérifie")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].call_id, "call_abc")
        self.assertEqual(calls[0].name, "chercher_etudiant")
        self.assertEqual(
            json.loads(calls[0].arguments), {"query": "BENALI"}
        )

    @requires_groq_sdk
    @patch("groq.Groq")
    def test_complete_utilise_le_modele_de_resume(self, MockGroq):
        from apps.ai_agent.llm.providers import GroqProvider

        completion = MagicMock()
        completion.choices = [
            MagicMock(message=MagicMock(content="Résumé fictif"))
        ]
        MockGroq.return_value.chat.completions.create.return_value = completion

        provider = GroqProvider(api_key="fake", model="fake-model")
        result = provider.complete([{"role": "user", "content": "Résume"}])
        self.assertEqual(result, "Résumé fictif")
        called_with = MockGroq.return_value.chat.completions.create.call_args
        self.assertEqual(called_with.kwargs["model"], provider.summary_model)


class ChatViewWithoutApiKeyTest(TestCase):
    """
    Régression : la vue de chat court-circuitait la requête dès que
    GROQ_API_KEY était vide, en renvoyant « Clé API Groq non
    configurée » — AVANT que l'orchestrateur, et donc le repli
    déterministe, ne soient atteints.

    Le repli existait pourtant dans `get_provider()`. Le bug a survécu
    parce que les tests appelaient l'orchestrateur directement et ne
    passaient jamais par la vue. Il ne s'est manifesté que sur
    l'instance déployée, sans clé — exactement le scénario que le repli
    est censé couvrir.

    Ces tests parcourent la vue HTTP de bout en bout.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="chat_demo", password="pwd", role="super_admin"
        )
        self.client = Client()
        self.client.login(username="chat_demo", password="pwd")

    @override_settings(GROQ_API_KEY="", LLM_FALLBACK_OFFLINE=True)
    def test_sans_cle_la_vue_repond_au_lieu_de_refuser(self):
        response = self.client.post(
            "/ai/chat/send/",
            data=json.dumps({"message": "Comment se passe la session de rattrapage ?"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        body = b"".join(response.streaming_content).decode()
        self.assertNotIn("non configurée", body)
        # Le RAG s'est bien déclenché : c'est la preuve que le pipeline
        # a tourné, pas seulement qu'une erreur a été évitée.
        self.assertIn('"type": "rag"', body)

    @override_settings(GROQ_API_KEY="", LLM_FALLBACK_OFFLINE=False)
    def test_sans_cle_et_sans_repli_la_vue_echoue_explicitement(self):
        """Repli désactivé = erreur claire, jamais de silence."""
        response = self.client.post(
            "/ai/chat/send/",
            data=json.dumps({"message": "Bonjour"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 503)
        self.assertIn("indisponible", response.json()["error"])

    @override_settings(GROQ_API_KEY="", LLM_FALLBACK_OFFLINE=True)
    def test_la_banniere_annonce_le_mode_deterministe(self):
        """
        L'interface ne doit pas crier à la panne : le mode déterministe
        est le comportement prévu d'une démo sans secret.
        """
        response = self.client.get("/ai/chat/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["offline_mode"])
        self.assertNotContains(response, "GROQ_API_KEY manquante")


class InitDataPasswordRealignTest(TestCase):
    """
    Régression : `init_data` ne créait les comptes que s'ils n'existaient
    pas, sans jamais mettre leur mot de passe à jour.

    Conséquence observée en production : changer `DEMO_ADMIN_PASSWORD`
    puis redéployer n'avait aucun effet sur une base déjà semée, et
    personne ne pouvait se connecter à la démonstration — ni avec
    l'ancien mot de passe, ni avec le nouveau. Une commande annoncée
    « idempotente » l'était au sens faible : elle ne dupliquait rien,
    mais elle ne convergeait pas non plus vers l'état demandé.
    """

    def test_le_mot_de_passe_est_realigne_sur_une_base_deja_semee(self):
        call_command("init_data", "--admin-password=premier", "--quiet",
                     stdout=StringIO())
        admin = User.objects.get(username="admin")
        self.assertTrue(admin.check_password("premier"))

        call_command("init_data", "--admin-password=second", "--quiet",
                     stdout=StringIO())
        admin.refresh_from_db()
        self.assertTrue(
            admin.check_password("second"),
            "init_data doit converger vers le mot de passe demandé.",
        )
        self.assertFalse(admin.check_password("premier"))

    def test_reste_idempotente_sur_les_donnees(self):
        """Le réalignement ne doit pas dupliquer d'entités."""
        from apps.administration.models import Etudiant

        call_command("init_data", "--quiet", stdout=StringIO())
        premier = Etudiant.objects.count()
        call_command("init_data", "--quiet", stdout=StringIO())
        self.assertEqual(Etudiant.objects.count(), premier)
