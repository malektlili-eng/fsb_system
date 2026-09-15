"""
tests/test_ai_agent.py
─────────────────────────────────────────────────────────────────────
Tests pour l'agent IA V2.

On mocke les appels à Groq pour :
- Tester le routage sans dépendance externe
- Tester chaque outil indépendamment
- Avoir des tests reproductibles et rapides
─────────────────────────────────────────────────────────────────────
"""
from unittest.mock import patch, MagicMock
from django.test import TestCase, Client
from django.urls import reverse

from tests.support import requires_groq_sdk


class UserFactory:
    @staticmethod
    def create_admin():
        from django.contrib.auth import get_user_model
        User = get_user_model()
        return User.objects.create_user(
            username='test_admin_ai',
            password='TestPass123!',
            role='admin',
        )


class FiliereFactory:
    @staticmethod
    def create():
        from apps.administration.models import Departement, Filiere
        dept, _ = Departement.objects.get_or_create(nom='informatique')
        return Filiere.objects.create(
            nom='Licence Informatique Test',
            code='LI-TEST-AI',
            departement=dept,
            niveau='L3',
            type_formation='licence',
        )


# ═══════════════════════════════════════════════════════════════════
# TESTS DU TOOL EXECUTOR
# ═══════════════════════════════════════════════════════════════════

class ToolExecutorTest(TestCase):
    """Tests des outils de l'agent sans appel LLM."""

    def setUp(self):
        self.admin = UserFactory.create_admin()
        self.filiere = FiliereFactory.create()

    def _get_executor(self):
        from apps.ai_agent.orchestrator import ToolExecutor
        return ToolExecutor(self.admin)

    def test_lister_filieres_retourne_donnees(self):
        """L'outil lister_filieres retourne les filières en BD."""
        executor = self._get_executor()
        result = executor.execute('lister_filieres', {})
        self.assertTrue(result['success'])
        self.assertIn('filieres', result)
        self.assertTrue(len(result['filieres']) >= 1)

    def test_obtenir_statistiques_global(self):
        """L'outil obtenir_statistiques retourne les stats globales."""
        executor = self._get_executor()
        result = executor.execute('obtenir_statistiques', {'type': 'global'})
        self.assertTrue(result['success'])
        self.assertIn('stats', result)
        self.assertIn('total_etudiants', result['stats'])

    def test_chercher_etudiant_trouve(self):
        """Recherche un étudiant existant."""
        from apps.administration.models import Etudiant
        e = Etudiant.objects.create(
            nom='TESTCHERCHE', prenom='Etudiant',
            numero_etudiant='ETU2024TEST01',
            filiere=self.filiere,
            annee_inscription=2024,
        )
        executor = self._get_executor()
        result = executor.execute('chercher_etudiant', {'query': 'TESTCHERCHE'})
        self.assertTrue(result['success'])
        self.assertEqual(result['count'], 1)
        self.assertEqual(result['etudiants'][0]['id'], e.pk)

    def test_chercher_etudiant_vide_si_inconnu(self):
        """Recherche sans résultat retourne une liste vide."""
        executor = self._get_executor()
        result = executor.execute('chercher_etudiant', {'query': 'NOM_INEXISTANT_XYZ'})
        self.assertTrue(result['success'])
        self.assertEqual(result['count'], 0)

    def test_creer_etudiant_via_outil(self):
        """L'outil creer_etudiant crée réellement en BD."""
        from apps.administration.models import Etudiant
        executor = self._get_executor()
        result = executor.execute('creer_etudiant', {
            'nom': 'TOOL_TEST',
            'prenom': 'Outil',
            'filiere_id': self.filiere.pk,
        })
        self.assertTrue(result['success'], result.get('error'))
        self.assertIn('etudiant', result)
        self.assertTrue(Etudiant.objects.filter(nom='TOOL_TEST').exists())

    def test_permission_refusee_scolarite_ne_peut_pas_creer(self):
        """Un agent scolarite ne peut PAS utiliser un outil réservé à l'admin."""
        from django.contrib.auth import get_user_model
        from apps.ai_agent.orchestrator import ToolExecutor

        User = get_user_model()
        scolarite = User.objects.create_user(
            username='test_scol_ai', password='Test123!', role='scolarite'
        )
        executor = ToolExecutor(scolarite)

        # planifier_examen est réservé à super_admin et admin
        result = executor.execute('planifier_examen', {
            'matiere_id': 1, 'date': '2025-01-15',
            'heure_debut': '08:00', 'heure_fin': '10:00'
        })
        self.assertFalse(result['success'])
        self.assertIn('Permission refusée', result['error'])


# ═══════════════════════════════════════════════════════════════════
# TESTS DES VUES AVEC MOCK
# ═══════════════════════════════════════════════════════════════════

class ChatViewTest(TestCase):
    """Tests de la vue de chat avec mock de l'orchestrateur."""

    def setUp(self):
        self.client = Client()
        self.admin = UserFactory.create_admin()
        self.client.login(username='test_admin_ai', password='TestPass123!')

    def test_interface_chat_accessible(self):
        """La page chat est accessible."""
        response = self.client.get(reverse('ai_agent:chat'))
        self.assertEqual(response.status_code, 200)

    def test_interface_chat_redirige_anonyme(self):
        """Un utilisateur non connecté est redirigé."""
        self.client.logout()
        response = self.client.get(reverse('ai_agent:chat'))
        self.assertRedirects(response, f"/accounts/login/?next={reverse('ai_agent:chat')}")

    @patch('apps.ai_agent.views.FSBOrchestrator')
    def test_send_message_retourne_stream(self, MockOrchestrator):
        """L'endpoint de message retourne un stream SSE."""
        import json

        # Configurer le mock pour retourner un stream simulé
        mock_instance = MagicMock()
        mock_instance.process_stream.return_value = iter([
            json.dumps({"type": "token", "data": "Bonjour"}) + "\n",
            json.dumps({"type": "token", "data": " !"}) + "\n",
            json.dumps({"type": "done", "tokens": 2, "elapsed_ms": 500}) + "\n",
        ])
        MockOrchestrator.return_value = mock_instance

        response = self.client.post(
            reverse('ai_agent:send'),
            json.dumps({'message': 'Bonjour', 'conversation_id': None}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/event-stream')

    def test_send_message_vide_retourne_400(self):
        """Un message vide retourne une erreur 400."""
        import json
        response = self.client.post(
            reverse('ai_agent:send'),
            json.dumps({'message': '', 'conversation_id': None}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    def test_delete_conversation(self):
        """La suppression d'une conversation fonctionne."""
        from apps.ai_agent.models import ConversationChat
        conv = ConversationChat.objects.create(
            user=self.admin, titre='Test à supprimer'
        )
        response = self.client.post(
            reverse('ai_agent:delete_conversation', args=[conv.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ConversationChat.objects.filter(pk=conv.pk).exists())


# ═══════════════════════════════════════════════════════════════════
# TESTS DE LA MÉMOIRE CONVERSATIONNELLE
# ═══════════════════════════════════════════════════════════════════

class ConversationMemoryTest(TestCase):
    """Tests de la récupération de l'historique."""

    def setUp(self):
        self.admin = UserFactory.create_admin()
        from apps.ai_agent.models import ConversationChat, MessageChat
        self.conv = ConversationChat.objects.create(
            user=self.admin, titre='Test mémoire'
        )
        # Créer 8 messages
        for i in range(8):
            MessageChat.objects.create(
                conversation=self.conv,
                role='user' if i % 2 == 0 else 'assistant',
                contenu=f'Message {i}',
            )

    @requires_groq_sdk
    @patch('groq.Groq')
    def test_historique_court_retourne_tous_messages(self, MockGroq):
        """Avec 8 messages (< 20), tous sont retournés."""
        from apps.ai_agent.orchestrator import FSBOrchestrator
        orchestrator = FSBOrchestrator(self.admin)
        history = orchestrator._get_history(self.conv.pk, max_messages=20)
        self.assertEqual(len(history), 8)

    def test_modele_agent_metric(self):
        """Le modèle AgentMetric est créé correctement."""
        from apps.ai_agent.models import AgentMetric
        metric = AgentMetric.objects.create(
            user=self.admin,
            question='Test question',
            response_length=100,
            response_time_ms=1500,
            tokens_used=50,
            tool_called='chercher_etudiant',
            action_success=True,
        )
        self.assertEqual(metric.temps_en_secondes, 1.5)
        self.assertEqual(AgentMetric.taux_succes_global(), 100.0)
