"""
tests/test_pedagogie_stages_examens.py (V2 - corrigé)
"""
from datetime import date, timedelta
from django.test import TestCase
from django.core.exceptions import ValidationError


def make_base():
    """Crée les données de base communes."""
    from django.contrib.auth import get_user_model
    from apps.administration.models import Departement, Filiere, Classe, Etudiant, Enseignant, Salle
    User = get_user_model()
    n = User.objects.count()
    admin = User.objects.create_user(f'adm_{n}', password='Test123!', role='admin')

    dept, _ = Departement.objects.get_or_create(nom='informatique')
    filiere = Filiere.objects.create(
        nom=f'LI Test {n}', code=f'LI-TST-{n:04d}',
        departement=dept, niveau='L3', type_formation='licence',
    )
    classe = Classe.objects.create(
        nom=f'L3 A {n}', code=f'L3A-{n:04d}', filiere=filiere, niveau='L3',
    )
    m = Etudiant.objects.count()
    etudiant = Etudiant.objects.create(
        nom=f'TESTPEDAGO{m}', prenom='Etudiant',
        numero_etudiant=f'ETU2024P{m:05d}',
        email=f'pedago{m}@test.tn',
        filiere=filiere, annee_inscription=2024,
    )
    enseignant = Enseignant.objects.create(
        nom='ENSTEST', prenom='Prof',
        matricule=f'MAT-{n:04d}',
        departement=dept, grade='assistant',
    )
    salle = Salle.objects.create(nom=f'Salle{n}', type_salle='salle', capacite=30)
    return admin, dept, filiere, classe, etudiant, enseignant, salle


# ═══════════════════════════════════════════════════════════════
# PÉDAGOGIE
# ═══════════════════════════════════════════════════════════════

class MoyenneServiceTest(TestCase):

    def setUp(self):
        self.admin, self.dept, self.filiere, self.classe, self.etudiant, _, _ = make_base()
        from apps.pedagogie.models import Matiere, Note
        self.matiere = Matiere.objects.create(
            nom='Algorithmique', code=f'ALGO-{Matiere.objects.count():03d}',
            filiere=self.filiere, semestre=1, credits=3, coefficient=2.0,
            heures_cours=21, heures_td=14,
        )
        Note.objects.create(
            etudiant=self.etudiant, matiere=self.matiere,
            type_note='ds', note=12.0,
            annee_universitaire='2024-2025', semestre=1,
        )
        Note.objects.create(
            etudiant=self.etudiant, matiere=self.matiere,
            type_note='exam', note=14.0,
            annee_universitaire='2024-2025', semestre=1,
        )

    def test_note_matiere_ds_exam(self):
        from apps.pedagogie.services import MoyenneService
        note = MoyenneService._note_matiere(
            self.etudiant, self.matiere, semestre=1, annee='2024-2025'
        )
        self.assertAlmostEqual(note, 13.2, places=1)

    def test_calcul_moyenne_classe(self):
        from apps.pedagogie.services import MoyenneService
        from apps.pedagogie.models import MoyenneEtudiant
        result = MoyenneService.calculer_classe(
            self.classe, semestre=1, annee='2024-2025', calculated_by=self.admin,
        )
        self.assertGreaterEqual(result['nb_calcules'], 1)
        self.assertTrue(MoyenneEtudiant.objects.filter(
            etudiant=self.etudiant, classe=self.classe, semestre=1
        ).exists())

    def test_mentions(self):
        from apps.pedagogie.models import MoyenneEtudiant
        self.assertEqual(MoyenneEtudiant.calculer_mention(18.5), 'excellent')
        self.assertEqual(MoyenneEtudiant.calculer_mention(16.0), 'tres_bien')
        self.assertEqual(MoyenneEtudiant.calculer_mention(14.0), 'bien')
        self.assertEqual(MoyenneEtudiant.calculer_mention(12.0), 'assez_bien')
        self.assertEqual(MoyenneEtudiant.calculer_mention(10.0), 'passable')
        self.assertEqual(MoyenneEtudiant.calculer_mention(9.9), '')

    def test_saisir_note_valide(self):
        from apps.pedagogie.services import MoyenneService
        from apps.pedagogie.models import Matiere
        mat2 = Matiere.objects.create(
            nom='Réseaux', code=f'RES-{Matiere.objects.count():03d}',
            filiere=self.filiere, semestre=1, credits=2,
        )
        note = MoyenneService.saisir_note(
            self.etudiant, mat2, 'exam', 15.0, 1, '2024-2025'
        )
        self.assertEqual(note.note, 15.0)

    def test_saisir_note_invalide(self):
        from apps.pedagogie.services import MoyenneService
        with self.assertRaises(ValidationError):
            MoyenneService.saisir_note(
                self.etudiant, self.matiere, 'ds', 25.0, 1, '2024-2025'
            )


# ═══════════════════════════════════════════════════════════════
# STAGES
# ═══════════════════════════════════════════════════════════════

class StageServiceTest(TestCase):

    def setUp(self):
        self.admin, _, self.filiere, _, self.etudiant, self.enseignant, _ = make_base()
        from apps.stages.models import DemandeStage
        self.demande = DemandeStage.objects.create(
            etudiant=self.etudiant,
            type_stage='pfe',
            entreprise='Société Test',
            sujet='Application web',
            date_debut=date.today(),
            date_fin=date.today() + timedelta(days=90),
            statut='en_attente',
        )

    def test_valider_demande(self):
        from apps.pedagogie.services import StageService
        d = StageService.valider(self.demande, self.enseignant.pk, 'OK', self.admin)
        self.assertEqual(d.statut, 'valide')

    def test_refuser_sans_commentaire(self):
        from apps.pedagogie.services import StageService
        with self.assertRaises(ValidationError):
            StageService.refuser(self.demande, '', self.admin)

    def test_transition_invalide(self):
        from apps.pedagogie.services import StageService
        with self.assertRaises(ValidationError):
            StageService.changer_statut(self.demande, 'termine', self.admin)

    def test_workflow_complet(self):
        from apps.pedagogie.services import StageService
        StageService.valider(self.demande, None, 'OK', self.admin)
        StageService.changer_statut(self.demande, 'en_cours', self.admin)
        StageService.terminer(self.demande, 14.5, self.admin)
        self.demande.refresh_from_db()
        self.assertEqual(self.demande.statut, 'termine')
        self.assertEqual(self.demande.note_stage, 14.5)


# ═══════════════════════════════════════════════════════════════
# DIPLÔME
# ═══════════════════════════════════════════════════════════════

class DiplomeServiceTest(TestCase):

    def setUp(self):
        self.admin, self.dept, self.filiere, _, self.etudiant, _, _ = make_base()

    def test_etudiant_non_terminal_non_eligible(self):
        from apps.pedagogie.services import DiplomeService
        from apps.administration.models import Filiere, Etudiant
        n = Filiere.objects.count()
        filiere_l1 = Filiere.objects.create(
            nom=f'L1 Test {n}', code=f'L1-DIP-{n:04d}',
            departement=self.dept, niveau='L1',
        )
        m = Etudiant.objects.count()
        etudiant_l1 = Etudiant.objects.create(
            nom='NON_ELIG', prenom='Test',
            numero_etudiant=f'ETU_NELIG_{m:04d}',
            email=f'nelig{m}@test.tn',
            filiere=filiere_l1, annee_inscription=2024,
        )
        check = DiplomeService.verifier_eligibilite(etudiant_l1)
        self.assertFalse(check['eligible'])
        self.assertTrue(len(check['raisons']) > 0)

    def test_etudiant_sans_moyennes_non_eligible(self):
        from apps.pedagogie.services import DiplomeService
        check = DiplomeService.verifier_eligibilite(self.etudiant)
        self.assertFalse(check['eligible'])
        self.assertTrue(any('moyenne' in r.lower() or 'stage' in r.lower()
                           for r in check['raisons']))


# ═══════════════════════════════════════════════════════════════
# EXAMENS
# ═══════════════════════════════════════════════════════════════

class PlanningExamenServiceTest(TestCase):

    def setUp(self):
        self.admin, _, self.filiere, self.classe, _, _, self.salle = make_base()
        from apps.examens.models import SessionExamen
        from apps.pedagogie.models import Matiere
        self.session = SessionExamen.objects.create(
            nom='Session S1 Test',
            type_session='principale',
            annee_universitaire='2024-2025',
            semestre=1,
            date_debut=date(2025, 1, 10),
            date_fin=date(2025, 1, 25),
        )
        n = Matiere.objects.count()
        self.mat1 = Matiere.objects.create(
            nom='Algo', code=f'ALGO-EX-{n:03d}',
            filiere=self.filiere, semestre=1,
        )
        self.mat2 = Matiere.objects.create(
            nom='BD', code=f'BD-EX-{n+1:03d}',
            filiere=self.filiere, semestre=1,
        )

    def test_planifier_sans_conflit(self):
        from apps.pedagogie.services import PlanningExamenService
        from apps.examens.models import PlanningExamen
        p = PlanningExamenService.ajouter(
            session=self.session, matiere=self.mat1,
            date=date(2025, 1, 15), heure_debut='08:00', heure_fin='10:00',
            salle=self.salle, added_by=self.admin,
        )
        self.assertIsNotNone(p.pk)
        self.assertTrue(PlanningExamen.objects.filter(pk=p.pk).exists())

    def test_conflit_salle(self):
        from apps.pedagogie.services import PlanningExamenService
        PlanningExamenService.ajouter(
            session=self.session, matiere=self.mat1,
            date=date(2025, 1, 15), heure_debut='08:00', heure_fin='10:00',
            salle=self.salle, added_by=self.admin,
        )
        with self.assertRaises(ValidationError):
            PlanningExamenService.ajouter(
                session=self.session, matiere=self.mat2,
                date=date(2025, 1, 15), heure_debut='09:00', heure_fin='11:00',
                salle=self.salle, added_by=self.admin,
            )

    def test_meme_salle_creneau_different_ok(self):
        from apps.pedagogie.services import PlanningExamenService
        PlanningExamenService.ajouter(
            session=self.session, matiere=self.mat1,
            date=date(2025, 1, 15), heure_debut='08:00', heure_fin='10:00',
            salle=self.salle, added_by=self.admin,
        )
        p2 = PlanningExamenService.ajouter(
            session=self.session, matiere=self.mat2,
            date=date(2025, 1, 15), heure_debut='10:30', heure_fin='12:30',
            salle=self.salle, added_by=self.admin,
        )
        self.assertIsNotNone(p2.pk)
