"""
tests/test_administration.py (V2 - corrigé)
"""
import datetime
from django.test import TestCase, Client
from django.urls import reverse
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model

User = get_user_model()


# ─── Factories ────────────────────────────────────────────────

class UserFactory:
    @staticmethod
    def create(role='scolarite', username=None, **kwargs):
        username = username or f"user_{role}_{User.objects.count()}"
        return User.objects.create_user(
            username=username, password='TestPass123!',
            first_name='Test', last_name='User', role=role, **kwargs
        )
    @staticmethod
    def create_super_admin():
        return UserFactory.create(role='super_admin', username=f'superadmin_{User.objects.count()}')
    @staticmethod
    def create_admin():
        return UserFactory.create(role='admin', username=f'admin_{User.objects.count()}')
    @staticmethod
    def create_scolarite():
        return UserFactory.create(role='scolarite', username=f'scol_{User.objects.count()}')


def make_dept():
    from apps.administration.models import Departement
    return Departement.objects.get_or_create(nom='informatique')[0]


def make_filiere(suffix=''):
    from apps.administration.models import Filiere
    dept = make_dept()
    code = f"LI-TST{suffix}-{Filiere.objects.count():03d}"
    return Filiere.objects.create(
        nom=f'Licence Info {suffix}', code=code,
        departement=dept, niveau='L3', type_formation='licence',
    )


def make_etudiant(filiere=None, suffix=''):
    from apps.administration.models import Etudiant
    if filiere is None:
        filiere = make_filiere(suffix)
    n = Etudiant.objects.count()
    return Etudiant.objects.create(
        nom=f'TESTNOM{n}', prenom=f'Prenom{n}',
        numero_etudiant=f'ETU2024{n:05d}',
        email=f'etudiant{n}@test.tn',
        filiere=filiere, annee_inscription=2024, statut='inscrit',
    )


# ═══════════════════════════════════════════════════════════════
# TESTS DES MODÈLES
# ═══════════════════════════════════════════════════════════════

class EtudiantModelTest(TestCase):

    def setUp(self):
        self.filiere = make_filiere('M')

    def test_creation_etudiant_valide(self):
        from apps.administration.models import Etudiant
        e = Etudiant.objects.create(
            nom='BEN ALI', prenom='Mohamed',
            numero_etudiant='ETU202400001',
            email='mohamedbenali@test.tn',
            filiere=self.filiere, annee_inscription=2024,
        )
        self.assertEqual(e.statut, 'inscrit')

    def test_numero_etudiant_unique(self):
        from apps.administration.models import Etudiant
        from django.db import IntegrityError
        Etudiant.objects.create(
            nom='DURAND', prenom='Alice',
            numero_etudiant='ETU202400001X',
            email='alice.durand@test.tn', annee_inscription=2024,
        )
        with self.assertRaises(IntegrityError):
            Etudiant.objects.create(
                nom='MARTIN', prenom='Bob',
                numero_etudiant='ETU202400001X',
                email='bob.martin@test.tn', annee_inscription=2024,
            )

    def test_get_full_name(self):
        from apps.administration.models import Etudiant
        e = Etudiant(nom='BEN SALAH', prenom='Fatma')
        self.assertEqual(e.get_full_name(), 'Fatma BEN SALAH')

    def test_statut_default_inscrit(self):
        from apps.administration.models import Etudiant
        e = Etudiant.objects.create(
            nom='TEST', prenom='Statut',
            numero_etudiant='ETU_STAT_01',
            email='statut@test.tn',
            filiere=self.filiere, annee_inscription=2024,
        )
        self.assertEqual(e.statut, 'inscrit')


class FiliereModelTest(TestCase):

    def test_nb_etudiants_compte_inscrits(self):
        from apps.administration.models import Etudiant
        filiere = make_filiere('NB')
        for i in range(3):
            Etudiant.objects.create(
                nom=f'ET{i}', prenom=f'P{i}',
                numero_etudiant=f'ETU_NB_{i:03d}',
                email=f'nb{i}@test.tn',
                filiere=filiere, annee_inscription=2024, statut='inscrit',
            )
        Etudiant.objects.create(
            nom='DIP', prenom='Dip',
            numero_etudiant='ETU_NB_DIP',
            email='dip@test.tn',
            filiere=filiere, annee_inscription=2023, statut='diplome',
        )
        self.assertEqual(filiere.nb_etudiants(), 3)


# ═══════════════════════════════════════════════════════════════
# TESTS DES SERVICES
# ═══════════════════════════════════════════════════════════════

class EtudiantServiceTest(TestCase):

    def setUp(self):
        self.admin = UserFactory.create_admin()
        self.filiere = make_filiere('SVC')

    def test_generer_numero_format(self):
        from apps.administration.services import EtudiantService
        numero = EtudiantService.generer_numero(annee=2024)
        self.assertTrue(numero.startswith('ETU2024'))
        self.assertEqual(len(numero), 12)

    def test_generer_numero_unique(self):
        from apps.administration.services import EtudiantService
        n1 = EtudiantService.generer_numero(annee=2024)
        make_etudiant(filiere=self.filiere)
        n2 = EtudiantService.generer_numero(annee=2024)
        self.assertNotEqual(n1, n2)

    def test_creer_etudiant_valide(self):
        from apps.administration.services import EtudiantService
        etudiant = EtudiantService.creer({
            'nom': 'TRABELSI', 'prenom': 'Sarra',
            'email': 'sarra.trabelsi.svc@test.tn',
            'filiere': self.filiere.pk, 'annee_inscription': 2024,
        }, created_by=self.admin)
        self.assertEqual(etudiant.nom, 'TRABELSI')
        self.assertTrue(etudiant.numero_etudiant.startswith('ETU'))

    def test_creer_email_duplique_leve_erreur(self):
        from apps.administration.services import EtudiantService
        make_etudiant(filiere=self.filiere)
        # Utiliser le même email qu'un étudiant existant
        from apps.administration.models import Etudiant
        existing_email = Etudiant.objects.first().email
        with self.assertRaises(ValidationError):
            EtudiantService.creer({
                'nom': 'AUTRE', 'prenom': 'Test',
                'email': existing_email,
                'filiere': self.filiere.pk, 'annee_inscription': 2024,
            }, created_by=self.admin)

    def test_creer_sans_email_genere_email_auto(self):
        from apps.administration.services import EtudiantService
        etudiant = EtudiantService.creer({
            'nom': 'MANSOUR', 'prenom': 'Ali',
            'filiere': self.filiere.pk, 'annee_inscription': 2024,
        }, created_by=self.admin)
        self.assertIn('@etu.fsb.tn', etudiant.email)

    def test_creer_annee_auto_si_absente(self):
        """Sans annee_inscription, l'année courante est utilisée."""
        import datetime
        from apps.administration.services import EtudiantService
        etudiant = EtudiantService.creer({
            'nom': 'ANNEE', 'prenom': 'Auto',
            'filiere': self.filiere.pk,
        }, created_by=self.admin)
        self.assertEqual(etudiant.annee_inscription, datetime.date.today().year)


# ═══════════════════════════════════════════════════════════════
# TESTS CONTRÔLE D'ACCÈS
# ═══════════════════════════════════════════════════════════════

class AccesVuesTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.super_admin = UserFactory.create_super_admin()
        self.admin = UserFactory.create_admin()
        self.scolarite = UserFactory.create_scolarite()
        self.etudiant_obj = make_etudiant()

    def test_dashboard_accessible_connecte(self):
        self.client.login(username=self.scolarite.username, password='TestPass123!')
        r = self.client.get(reverse('administration:dashboard'))
        self.assertEqual(r.status_code, 200)

    def test_dashboard_redirige_anonyme(self):
        r = self.client.get(reverse('administration:dashboard'))
        self.assertEqual(r.status_code, 302)

    def test_liste_etudiants_accessible_connecte(self):
        self.client.login(username=self.scolarite.username, password='TestPass123!')
        r = self.client.get(reverse('administration:liste_etudiants'))
        self.assertEqual(r.status_code, 200)

    def test_supprimer_etudiant_interdit_scolarite(self):
        self.client.login(username=self.scolarite.username, password='TestPass123!')
        r = self.client.post(
            reverse('administration:supprimer_etudiant', args=[self.etudiant_obj.pk])
        )
        self.assertEqual(r.status_code, 403)

    def test_supprimer_etudiant_autorise_admin(self):
        self.client.login(username=self.admin.username, password='TestPass123!')
        r = self.client.post(
            reverse('administration:supprimer_etudiant', args=[self.etudiant_obj.pk])
        )
        self.assertEqual(r.status_code, 302)

    def test_gestion_agents_reservee_super_admin(self):
        self.client.login(username=self.admin.username, password='TestPass123!')
        r = self.client.get(reverse('accounts:gestion_agents'))
        self.assertEqual(r.status_code, 403)

        self.client.logout()
        self.client.login(username=self.super_admin.username, password='TestPass123!')
        r = self.client.get(reverse('accounts:gestion_agents'))
        self.assertEqual(r.status_code, 200)

    def test_ajouter_etudiant_valide(self):
        from apps.administration.models import Etudiant
        filiere = make_filiere('AJT')
        self.client.login(username=self.admin.username, password='TestPass123!')
        r = self.client.post(reverse('administration:ajouter_etudiant'), {
            'nom': 'FORM TEST',
            'prenom': 'Valide',
            'email': 'formvalide@test.tn',
            'filiere': filiere.pk,
            'annee_inscription': 2024,
        })
        self.assertEqual(r.status_code, 302)
        self.assertTrue(Etudiant.objects.filter(email='formvalide@test.tn').exists())

    def test_ajouter_etudiant_invalide_reste_sur_formulaire(self):
        self.client.login(username=self.admin.username, password='TestPass123!')
        r = self.client.post(reverse('administration:ajouter_etudiant'), {
            'nom': '', 'prenom': ''
        })
        self.assertEqual(r.status_code, 200)
        # Vérifier que le contexte contient le formulaire avec des erreurs
        self.assertIn('form', r.context)
        self.assertIn('nom', r.context['form'].errors)


# ═══════════════════════════════════════════════════════════════
# TESTS FORMULAIRES
# ═══════════════════════════════════════════════════════════════

class EtudiantFormTest(TestCase):

    def setUp(self):
        self.filiere = make_filiere('FRM')

    def _data(self, **kw):
        d = {'nom': 'BENSALEM', 'prenom': 'Nour',
             'email': 'nour.bensalem@test.tn',
             'filiere': self.filiere.pk, 'annee_inscription': 2024}
        d.update(kw)
        return d

    def test_form_valide(self):
        from apps.administration.forms import EtudiantForm
        form = EtudiantForm(self._data())
        self.assertTrue(form.is_valid(), form.errors)

    def test_nom_normalise_majuscules(self):
        from apps.administration.forms import EtudiantForm
        form = EtudiantForm(self._data(nom='bensalem', email='nour2@test.tn'))
        form.is_valid()
        self.assertEqual(form.cleaned_data['nom'], 'BENSALEM')

    def test_prenom_title_case(self):
        from apps.administration.forms import EtudiantForm
        form = EtudiantForm(self._data(prenom='nour eddine', email='ne@test.tn'))
        form.is_valid()
        self.assertEqual(form.cleaned_data['prenom'], 'Nour Eddine')

    def test_email_duplique_invalide(self):
        from apps.administration.forms import EtudiantForm
        make_etudiant(filiere=self.filiere)
        from apps.administration.models import Etudiant
        existing = Etudiant.objects.first().email
        form = EtudiantForm(self._data(email=existing))
        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)

    def test_nom_vide_invalide(self):
        from apps.administration.forms import EtudiantForm
        form = EtudiantForm(self._data(nom=''))
        self.assertFalse(form.is_valid())
        self.assertIn('nom', form.errors)
