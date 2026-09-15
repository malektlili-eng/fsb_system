"""
apps/stages/models.py (V2)
"""
from django.db import models
from apps.administration.models import Etudiant, Enseignant, TimeStampedModel


class DemandeStage(TimeStampedModel):
    TYPE_CHOICES = [
        ('observation', 'Stage Observation'),
        ('initiation',  'Stage Initiation'),
        ('pfe',         'PFE'),
    ]
    STATUT_CHOICES = [
        ('en_attente', 'En Attente'),
        ('valide',     'Validé'),
        ('refuse',     'Refusé'),
        ('en_cours',   'En Cours'),
        ('termine',    'Terminé'),
    ]
    etudiant             = models.ForeignKey(Etudiant, on_delete=models.CASCADE, related_name='stages')
    type_stage           = models.CharField(max_length=20, choices=TYPE_CHOICES)
    entreprise           = models.CharField(max_length=200)
    sujet                = models.CharField(max_length=300)
    description          = models.TextField(blank=True)
    date_debut           = models.DateField()
    date_fin             = models.DateField()
    encadrant_fsb        = models.ForeignKey(
        Enseignant, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='stages_encadres'
    )
    encadrant_entreprise = models.CharField(max_length=100, blank=True)
    statut               = models.CharField(max_length=15, choices=STATUT_CHOICES, default='en_attente')
    date_demande         = models.DateField(auto_now_add=True)
    rapport              = models.FileField(upload_to='rapports_stage/', blank=True, null=True)
    note_stage           = models.FloatField(null=True, blank=True)
    commentaire_admin    = models.TextField(blank=True)

    class Meta:
        ordering = ['-date_demande']
        indexes  = [models.Index(fields=['statut', 'type_stage'])]

    def __str__(self):
        return f"{self.etudiant} — {self.sujet[:50]}"


class Diplome(TimeStampedModel):
    MENTION_CHOICES = [
        ('passable',   'Passable'),
        ('assez_bien', 'Assez Bien'),
        ('bien',       'Bien'),
        ('tres_bien',  'Très Bien'),
    ]
    etudiant         = models.ForeignKey(Etudiant, on_delete=models.CASCADE, related_name='diplomes')
    type_diplome     = models.CharField(max_length=50)
    specialite       = models.CharField(max_length=100)
    annee_obtention  = models.IntegerField()
    mention          = models.CharField(max_length=20, choices=MENTION_CHOICES, blank=True)
    moyenne_generale = models.FloatField(null=True, blank=True)
    numero_diplome   = models.CharField(max_length=50, unique=True)
    date_delivrance  = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['-annee_obtention']

    def __str__(self):
        return f"Diplôme {self.type_diplome} — {self.etudiant}"
