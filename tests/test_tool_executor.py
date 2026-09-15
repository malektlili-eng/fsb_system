"""
tests/test_tool_executor.py
─────────────────────────────────────────────────────────────────────
Tests directs du ToolExecutor : les outils exécutent de VRAIES actions
en base sous contrôle RBAC. C'est le cœur de valeur de
`orchestrator.py` — il doit être testé pour lui-même, pas seulement à
travers le pipeline de streaming.
─────────────────────────────────────────────────────────────────────
"""
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai_agent.orchestrator import ToolExecutor

User = get_user_model()


class ToolExecutorBaseTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        from apps.administration.models import Departement, Etudiant, Filiere

        cls.admin = User.objects.create_user(
            username="tool_admin", password="x", role="admin",
            first_name="Tool", last_name="Admin",
        )
        cls.scolarite = User.objects.create_user(
            username="tool_scol", password="x", role="scolarite",
            first_name="Tool", last_name="Scol",
        )
        cls.dept = Departement.objects.create(nom="informatique")
        cls.filiere = Filiere.objects.create(
            nom="Licence Informatique", code="LI-TOOL", departement=cls.dept,
            niveau="L3", type_formation="licence",
        )
        cls.etudiant = Etudiant.objects.create(
            nom="ZAOUI", prenom="Mehdi", numero_etudiant="ETU-TOOL-001",
            email="mehdi.zaoui@fsb.tn", filiere=cls.filiere,
            annee_inscription=2025,
        )


class ChercherEtudiantTest(ToolExecutorBaseTest):
    def test_recherche_par_nom(self):
        executor = ToolExecutor(self.admin)
        result = executor.execute("chercher_etudiant", {"query": "ZAOUI"})
        self.assertTrue(result["success"])
        self.assertGreaterEqual(result["count"], 1)

    def test_recherche_par_numero(self):
        executor = ToolExecutor(self.admin)
        result = executor.execute(
            "chercher_etudiant", {"query": "ETU-TOOL-001"}
        )
        self.assertTrue(result["success"])
        self.assertGreaterEqual(result["count"], 1)

    def test_recherche_sans_resultat_reste_un_succes(self):
        """Zéro résultat n'est pas une erreur : la requête a abouti."""
        executor = ToolExecutor(self.admin)
        result = executor.execute(
            "chercher_etudiant", {"query": "INEXISTANT_XYZ"}
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["count"], 0)

    def test_filtre_par_filiere(self):
        executor = ToolExecutor(self.admin)
        result = executor.execute(
            "chercher_etudiant",
            {"query": "ZAOUI", "filiere_id": self.filiere.pk},
        )
        self.assertTrue(result["success"])


class CreerEtudiantTest(ToolExecutorBaseTest):
    def test_creation_reussie_et_numero_auto(self):
        from apps.administration.models import Etudiant

        executor = ToolExecutor(self.scolarite)
        result = executor.execute(
            "creer_etudiant",
            {
                "nom": "BENSALAH",
                "prenom": "Ines",
                "filiere_id": self.filiere.pk,
                "email": "ines.bensalah@fsb.tn",
            },
        )
        self.assertTrue(result["success"], result)
        self.assertTrue(
            Etudiant.objects.filter(nom="BENSALAH", prenom="Ines").exists()
        )

    def test_filiere_inexistante_echoue_proprement(self):
        executor = ToolExecutor(self.scolarite)
        result = executor.execute(
            "creer_etudiant",
            {
                "nom": "X",
                "prenom": "Y",
                "filiere_id": 999999,
                "email": "x.y@fsb.tn",
            },
        )
        self.assertFalse(result["success"])
        self.assertIn("error", result)


class StatistiquesTest(ToolExecutorBaseTest):
    def test_statistiques_globales(self):
        executor = ToolExecutor(self.admin)
        result = executor.execute("obtenir_statistiques", {"type": "global"})
        self.assertTrue(result["success"])
        stats = result["stats"]
        self.assertIn("total_etudiants", stats)
        self.assertIn("total_filieres", stats)
        self.assertGreaterEqual(stats["total_filieres"], 1)

    def test_statistiques_etudiants_filtrees_par_filiere(self):
        executor = ToolExecutor(self.admin)
        result = executor.execute(
            "obtenir_statistiques",
            {"type": "etudiants", "filiere_id": self.filiere.pk},
        )
        self.assertTrue(result["success"])
        self.assertIn("inscrits", result["stats"])

    def test_statistiques_absences(self):
        executor = ToolExecutor(self.admin)
        result = executor.execute("obtenir_statistiques", {"type": "absences"})
        self.assertTrue(result["success"])
        self.assertIn("justifiees", result["stats"])

    def test_type_inconnu_echoue_proprement(self):
        executor = ToolExecutor(self.admin)
        result = executor.execute(
            "obtenir_statistiques", {"type": "inconnu_xyz"}
        )
        self.assertFalse(result["success"])
        self.assertIn("error", result)


class ListerFilieresTest(ToolExecutorBaseTest):
    def test_liste_contient_la_filiere(self):
        executor = ToolExecutor(self.admin)
        result = executor.execute("lister_filieres", {})
        self.assertTrue(result["success"])
        self.assertIn("LI-TOOL", str(result))


class NotesEtudiantTest(ToolExecutorBaseTest):
    def test_notes_etudiant_existant(self):
        executor = ToolExecutor(self.admin)
        result = executor.execute(
            "notes_etudiant", {"etudiant_id": self.etudiant.pk}
        )
        self.assertTrue(result["success"])
        self.assertIsInstance(result["notes"], list)

    def test_etudiant_sans_notes_retourne_liste_vide(self):
        """Aucune note n'est un résultat valide, pas une erreur."""
        executor = ToolExecutor(self.admin)
        result = executor.execute("notes_etudiant", {"etudiant_id": 999999})
        self.assertTrue(result["success"])
        self.assertEqual(result["notes"], [])

    def test_filtre_par_semestre(self):
        executor = ToolExecutor(self.admin)
        result = executor.execute(
            "notes_etudiant", {"etudiant_id": self.etudiant.pk, "semestre": 1}
        )
        self.assertTrue(result["success"])


class PlanifierExamenTest(ToolExecutorBaseTest):
    def test_matiere_inexistante_echoue_proprement(self):
        executor = ToolExecutor(self.admin)
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        result = executor.execute(
            "planifier_examen",
            {
                "matiere_id": 999999,
                "date": tomorrow,
                "heure_debut": "08:00",
                "heure_fin": "10:00",
            },
        )
        self.assertFalse(result["success"])
        self.assertIn("error", result)


class PermissionsTest(ToolExecutorBaseTest):
    def test_scolarite_ne_peut_pas_planifier_un_examen(self):
        executor = ToolExecutor(self.scolarite)
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        result = executor.execute(
            "planifier_examen",
            {
                "matiere_id": 1,
                "date": tomorrow,
                "heure_debut": "08:00",
                "heure_fin": "10:00",
            },
        )
        self.assertFalse(result["success"])
        self.assertIn("error", result)

    def test_outil_inconnu_refuse(self):
        executor = ToolExecutor(self.admin)
        result = executor.execute("outil_qui_nexiste_pas", {})
        self.assertFalse(result["success"])

    def test_arguments_invalides_ne_cassent_pas(self):
        """Un mauvais type d'argument ne doit pas propager d'exception."""
        executor = ToolExecutor(self.admin)
        result = executor.execute("chercher_etudiant", {})
        self.assertIn("success", result)
