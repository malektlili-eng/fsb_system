"""
apps/administration/models.py — ajout AuditLog + TimeStampedModel
─────────────────────────────────────────────────────────────────────
Ce fichier étend les modèles existants avec :
 - TimeStampedModel : mixin created_at / updated_at
 - AuditLog : journal de toutes les actions sensibles
 - Index explicites sur les champs fréquemment filtrés
─────────────────────────────────────────────────────────────────────
"""
from django.db import models
from django.contrib.auth import get_user_model


# ─── Mixin timestamps ─────────────────────────────────────────────

class TimeStampedModel(models.Model):
    """
    Mixin abstrait qui ajoute created_at et updated_at à tout modèle.
    Usage : class MonModel(TimeStampedModel): ...
    """
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


# ─── Journal d'audit ─────────────────────────────────────────────

class AuditLog(models.Model):
    """
    Trace toutes les actions sensibles sur les données universitaires.
    Répond aux exigences légales de traçabilité (RGPD-like).
    """
    ACTION_CHOICES = [
        ('CREATE',        'Création'),
        ('UPDATE',        'Modification'),
        ('DELETE',        'Suppression'),
        ('VALIDATE',      'Validation'),
        ('REJECT',        'Rejet'),
        ('STATUS_CHANGE', 'Changement de statut'),
        ('LOGIN',         'Connexion'),
        ('LOGOUT',        'Déconnexion'),
        ('EXPORT',        'Export de données'),
    ]

    timestamp  = models.DateTimeField(auto_now_add=True, db_index=True)
    user       = models.ForeignKey(
        get_user_model(),
        on_delete=models.SET_NULL,
        null=True,
        related_name='audit_logs',
        help_text="Utilisateur qui a effectué l'action"
    )
    action     = models.CharField(max_length=20, choices=ACTION_CHOICES, db_index=True)
    model_name = models.CharField(max_length=50, db_index=True)
    object_id  = models.PositiveIntegerField(null=True, blank=True)
    details    = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ['-timestamp']
        verbose_name = "Journal d'audit"
        verbose_name_plural = "Journal d'audit"
        indexes = [
            models.Index(fields=['model_name', 'object_id']),
            models.Index(fields=['user', 'timestamp']),
        ]

    def __str__(self):
        return (
            f"[{self.timestamp.strftime('%d/%m/%Y %H:%M')}] "
            f"{self.get_action_display()} — {self.model_name} #{self.object_id} "
            f"par {self.user or 'système'}"
        )


# ─── Extension des modèles existants ─────────────────────────────
# Ces classes REMPLACENT les modèles V1 en ajoutant timestamps + index.
# Les champs existants restent identiques, on ajoute seulement :
#   created_at, updated_at, et des indexes DB.

class Departement(TimeStampedModel):
    NOM_CHOICES = [
        ('mathematiques', 'Mathématiques'),
        ('informatique',  'Informatique'),
        ('physique',      'Physique'),
        ('chimie',        'Chimie'),
        ('biologie',      'Biologie'),
        ('geologie',      'Géologie'),
    ]
    nom         = models.CharField(max_length=50, choices=NOM_CHOICES, unique=True)
    chef        = models.CharField(max_length=100, blank=True, null=True)
    email       = models.EmailField(blank=True)
    telephone   = models.CharField(max_length=20, blank=True)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.get_nom_display()


class Filiere(TimeStampedModel):
    NIVEAU_CHOICES = [
        ('L1','Licence 1'), ('L2','Licence 2'), ('L3','Licence 3'),
        ('M1','Master 1'),  ('M2','Master 2'),  ('Doc','Doctorat'),
        ('CPI','CPI'), ('CI','CI Ingénieur'),
    ]
    TYPE_CHOICES = [
        ('licence','Licence'), ('master','Master'),
        ('doctorat','Doctorat'), ('cpi','CPI'), ('ci','CI'),
    ]
    nom            = models.CharField(max_length=100)
    code           = models.CharField(max_length=20, unique=True)
    departement    = models.ForeignKey(
        Departement, on_delete=models.CASCADE, related_name='filieres'
    )
    niveau         = models.CharField(max_length=5, choices=NIVEAU_CHOICES)
    type_formation = models.CharField(max_length=20, choices=TYPE_CHOICES, default='licence')
    description    = models.TextField(blank=True, default='')

    def nb_etudiants(self):
        return Etudiant.objects.filter(filiere=self, statut='inscrit').count()

    def __str__(self):
        return f"{self.code} — {self.nom}"


class Classe(TimeStampedModel):
    NIVEAU_CHOICES = [
        ('L1','L1'), ('L2','L2'), ('L3','L3'),
        ('M1','M1'), ('M2','M2'),
        ('Doc1','Doc1'), ('Doc2','Doc2'), ('Doc3','Doc3'),
        ('CPI1','CPI1'), ('CPI2','CPI2'),
        ('CI1','CI1'), ('CI2','CI2'), ('CI3','CI3'),
    ]
    nom                 = models.CharField(max_length=100)
    code                = models.CharField(max_length=20, unique=True)
    filiere             = models.ForeignKey(Filiere, on_delete=models.CASCADE, related_name='classes')
    niveau              = models.CharField(max_length=10, choices=NIVEAU_CHOICES)
    annee_universitaire = models.CharField(max_length=9, default='2024-2025')
    capacite            = models.IntegerField(default=30)

    def __str__(self):
        return f"{self.code} — {self.nom}"

    def nb_etudiants(self):
        return Etudiant.objects.filter(filiere=self.filiere, statut='inscrit').count()


class Enseignant(TimeStampedModel):
    GRADE_CHOICES = [
        ('assistant',        'Assistant'),
        ('maitre_assistant', 'Maître Assistant'),
        ('maitre_conf',      'Maître de Conférences'),
        ('professeur',       'Professeur'),
    ]
    nom              = models.CharField(max_length=100)
    prenom           = models.CharField(max_length=100)
    matricule        = models.CharField(max_length=20, unique=True)
    email            = models.EmailField(blank=True)
    telephone        = models.CharField(max_length=20, blank=True)
    departement      = models.ForeignKey(
        Departement, on_delete=models.SET_NULL, null=True, related_name='enseignants'
    )
    grade            = models.CharField(max_length=30, choices=GRADE_CHOICES)
    specialite       = models.CharField(max_length=100, blank=True)
    date_recrutement = models.DateField(null=True, blank=True)
    actif            = models.BooleanField(default=True)

    class Meta:
        ordering = ['nom', 'prenom']
        indexes = [
            models.Index(fields=['matricule']),
            models.Index(fields=['departement', 'actif']),
        ]

    def get_full_name(self):
        return f"{self.prenom} {self.nom}"

    def __str__(self):
        return f"{self.get_grade_display()} {self.get_full_name()}"


class Etudiant(TimeStampedModel):
    STATUT_CHOICES = [
        ('inscrit',   'Inscrit'),
        ('suspendu',  'Suspendu'),
        ('diplome',   'Diplômé'),
        ('abandonne', 'Abandonné'),
    ]
    nom               = models.CharField(max_length=100)
    prenom            = models.CharField(max_length=100)
    numero_etudiant   = models.CharField(max_length=20, unique=True)
    cin               = models.CharField(max_length=20, blank=True)
    email             = models.EmailField(blank=True, unique=True)
    telephone         = models.CharField(max_length=20, blank=True)
    filiere           = models.ForeignKey(
        Filiere, on_delete=models.SET_NULL, null=True, related_name='etudiants'
    )
    annee_inscription = models.IntegerField()
    date_naissance    = models.DateField(null=True, blank=True)
    lieu_naissance    = models.CharField(max_length=100, blank=True)
    adresse           = models.TextField(blank=True)
    statut            = models.CharField(
        max_length=20, choices=STATUT_CHOICES, default='inscrit'
    )

    class Meta:
        ordering = ['nom', 'prenom']
        indexes = [
            models.Index(fields=['numero_etudiant']),
            models.Index(fields=['email']),
            models.Index(fields=['statut', 'annee_inscription']),
            models.Index(fields=['filiere', 'statut']),
        ]

    def get_full_name(self):
        return f"{self.prenom} {self.nom}"

    def __str__(self):
        return f"{self.numero_etudiant} — {self.get_full_name()}"


class Salle(TimeStampedModel):
    TYPE_CHOICES = [
        ('amphi', 'Amphithéâtre'),
        ('salle', 'Salle de Cours'),
        ('tp',    'Salle TP'),
        ('info',  'Salle Informatique'),
    ]
    nom        = models.CharField(max_length=50)
    type_salle = models.CharField(max_length=10, choices=TYPE_CHOICES)
    capacite   = models.IntegerField()
    batiment   = models.CharField(max_length=50, blank=True)

    class Meta:
        ordering = ['nom']

    def __str__(self):
        return f"{self.nom} ({self.get_type_salle_display()}, {self.capacite} pl.)"


class Inscription(TimeStampedModel):
    STATUT_CHOICES = [
        ('en_attente',        'En attente'),
        ('dossier_incomplet', 'Dossier incomplet'),
        ('frais_non_payes',   'Frais non payés'),
        ('validee',           'Validée'),
        ('suspendue',         'Suspendue'),
        ('annulee',           'Annulée'),
    ]
    etudiant            = models.ForeignKey(
        Etudiant, on_delete=models.CASCADE, related_name='inscriptions'
    )
    filiere             = models.ForeignKey(Filiere, on_delete=models.CASCADE)
    annee_universitaire = models.CharField(max_length=9, default='2024-2025')
    date_inscription    = models.DateField(auto_now_add=True)
    statut              = models.CharField(
        max_length=25, choices=STATUT_CHOICES, default='en_attente'
    )
    commentaire         = models.TextField(blank=True, default='')
    date_validation     = models.DateField(null=True, blank=True)
    valide_par          = models.CharField(max_length=100, blank=True, default='')

    class Meta:
        unique_together = ['etudiant', 'annee_universitaire']
        ordering = ['-date_inscription']
        indexes = [
            models.Index(fields=['statut', 'annee_universitaire']),
        ]

    @property
    def valide(self):
        return self.statut == 'validee'

    def __str__(self):
        return f"{self.etudiant} — {self.annee_universitaire} [{self.get_statut_display()}]"
