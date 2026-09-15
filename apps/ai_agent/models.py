"""
apps/ai_agent/models.py (V2)
─────────────────────────────────────────────────────────────────────
Modèles pour l'agent IA V2.

AJOUT vs V1 : modèle AgentMetric pour le monitoring des performances.
─────────────────────────────────────────────────────────────────────
"""
from django.db import models
from apps.accounts.models import CustomUser


class ConversationChat(models.Model):
    AGENT_CHOICES = [
        ('multi', 'Agent Multi-Rôles'),
    ]
    user       = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name='conversations'
    )
    agent_type = models.CharField(max_length=30, choices=AGENT_CHOICES, default='multi')
    titre      = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.titre or 'Sans titre'} — {self.user} ({self.created_at.date()})"

    def nb_messages(self):
        return self.messages.count()

    def dernier_message(self):
        return self.messages.order_by('-timestamp').first()


class MessageChat(models.Model):
    ROLE_CHOICES = [
        ('user',      'Utilisateur'),
        ('assistant', 'Assistant IA'),
        ('system',    'Système'),
    ]
    conversation = models.ForeignKey(
        ConversationChat, on_delete=models.CASCADE, related_name='messages'
    )
    role         = models.CharField(max_length=10, choices=ROLE_CHOICES)
    contenu      = models.TextField()
    timestamp    = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        return f"{self.get_role_display()}: {self.contenu[:60]}"


class AgentMetric(models.Model):
    """
    Enregistre les métriques de chaque interaction avec l'agent IA.
    Permet de monitorer :
    - La performance (temps de réponse, tokens utilisés)
    - L'utilisation (quels outils sont les plus demandés)
    - La fiabilité (taux de succès des actions)
    - Les coûts (estimation basée sur les tokens)
    """
    timestamp       = models.DateTimeField(auto_now_add=True)
    user            = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, related_name='agent_metrics'
    )
    question        = models.TextField(max_length=500)
    response_length = models.IntegerField(default=0, help_text="Longueur de la réponse en caractères")
    response_time_ms = models.IntegerField(default=0, help_text="Temps de réponse en millisecondes")
    tokens_used     = models.IntegerField(default=0)
    tool_called     = models.CharField(max_length=50, blank=True, help_text="Nom de l'outil utilisé")
    action_success  = models.BooleanField(null=True, help_text="L'action demandée a-t-elle réussi ?")

    # Télémétrie RAG (V2.1) — permet d'auditer le retrieval en production
    rag_chunks      = models.IntegerField(default=0, help_text="Nombre de chunks injectés dans le prompt")
    rag_top_score   = models.FloatField(null=True, blank=True, help_text="Score du meilleur chunk retrouvé")
    retrieval_ms    = models.IntegerField(default=0, help_text="Latence du retrieval en millisecondes")

    class Meta:
        ordering = ['-timestamp']
        verbose_name = "Métrique agent IA"
        verbose_name_plural = "Métriques agent IA"

    def __str__(self):
        return f"{self.timestamp.strftime('%d/%m %H:%M')} — {self.question[:50]}"

    @property
    def temps_en_secondes(self):
        return round(self.response_time_ms / 1000, 2)

    @staticmethod
    def taux_succes_global():
        """Calcule le taux de succès global des actions."""
        total = AgentMetric.objects.filter(action_success__isnull=False).count()
        if not total:
            return None
        succes = AgentMetric.objects.filter(action_success=True).count()
        return round(succes / total * 100, 1)
