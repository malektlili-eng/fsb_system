"""
apps/pedagogie/models.py (V2)
Identique à la V1 avec ajout du mixin TimeStampedModel.
"""
from django.db import models
from apps.administration.models import (
    Enseignant, Filiere, Salle, Etudiant, Classe, TimeStampedModel
)


class Matiere(TimeStampedModel):
    nom          = models.CharField(max_length=100)
    code         = models.CharField(max_length=20, unique=True)
    filiere      = models.ForeignKey(Filiere, on_delete=models.CASCADE, related_name='matieres')
    credits      = models.IntegerField(default=3)
    coefficient  = models.FloatField(default=1.0)
    heures_cours = models.IntegerField(default=0)
    heures_td    = models.IntegerField(default=0)
    heures_tp    = models.IntegerField(default=0)
    semestre     = models.IntegerField(choices=[(1,'S1'),(2,'S2')])

    class Meta:
        ordering = ['filiere', 'semestre', 'nom']
        indexes = [models.Index(fields=['filiere', 'semestre'])]

    def total_heures(self):
        return self.heures_cours + self.heures_td + self.heures_tp

    def seuil_elimination(self):
        return self.total_heures() * 0.25

    def __str__(self):
        return f"{self.code} — {self.nom}"


class EmploiDuTemps(TimeStampedModel):
    JOUR_CHOICES = [(1,'Lundi'),(2,'Mardi'),(3,'Mercredi'),(4,'Jeudi'),(5,'Vendredi'),(6,'Samedi')]
    TYPE_CHOICES = [('cours','Cours'),('td','TD'),('tp','TP')]

    matiere             = models.ForeignKey(Matiere, on_delete=models.CASCADE)
    enseignant          = models.ForeignKey(Enseignant, on_delete=models.SET_NULL, null=True, blank=True)
    salle               = models.ForeignKey(Salle, on_delete=models.SET_NULL, null=True, blank=True)
    classe              = models.ForeignKey(Classe, on_delete=models.SET_NULL, null=True, blank=True, related_name='seances')
    jour                = models.IntegerField(choices=JOUR_CHOICES)
    heure_debut         = models.TimeField()
    heure_fin           = models.TimeField()
    type_seance         = models.CharField(max_length=10, choices=TYPE_CHOICES)
    annee_universitaire = models.CharField(max_length=9, default='2024-2025')
    semestre            = models.IntegerField(choices=[(1,'S1'),(2,'S2')])

    class Meta:
        ordering = ['jour', 'heure_debut']

    def __str__(self):
        return f"{self.matiere} — {self.get_jour_display()} {self.heure_debut}"


class Absence(TimeStampedModel):
    etudiant  = models.ForeignKey(Etudiant, on_delete=models.CASCADE, related_name='absences')
    seance    = models.ForeignKey(EmploiDuTemps, on_delete=models.CASCADE)
    date      = models.DateField()
    justifiee = models.BooleanField(default=False)
    motif     = models.TextField(blank=True)

    class Meta:
        unique_together = ['etudiant', 'seance', 'date']
        indexes = [models.Index(fields=['etudiant', 'date'])]

    def __str__(self):
        return f"{self.etudiant} absent le {self.date}"


class Note(TimeStampedModel):
    TYPE_CHOICES = [
        ('ds','DS'),('exam','Examen'),('tp','TP'),
        ('expose','Exposé'),('rattrapage','Rattrapage'),
    ]
    etudiant            = models.ForeignKey(Etudiant, on_delete=models.CASCADE, related_name='notes')
    matiere             = models.ForeignKey(Matiere, on_delete=models.CASCADE)
    type_note           = models.CharField(max_length=15, choices=TYPE_CHOICES)
    note                = models.FloatField()
    annee_universitaire = models.CharField(max_length=9)
    semestre            = models.IntegerField(choices=[(1,'S1'),(2,'S2')])
    date_saisie         = models.DateField(auto_now_add=True)
    enseignant          = models.ForeignKey(Enseignant, on_delete=models.SET_NULL, null=True, blank=True)
    saisie_par          = models.CharField(max_length=100, blank=True)

    class Meta:
        unique_together = ['etudiant','matiere','type_note','annee_universitaire','semestre']
        indexes = [models.Index(fields=['etudiant', 'semestre', 'annee_universitaire'])]

    def __str__(self):
        return f"{self.etudiant} — {self.matiere}: {self.note}"


class MoyenneEtudiant(TimeStampedModel):
    MENTION_CHOICES = [
        ('',           '—'),
        ('passable',   'Passable (10–12)'),
        ('assez_bien', 'Assez Bien (12–14)'),
        ('bien',       'Bien (14–16)'),
        ('tres_bien',  'Très Bien (16–18)'),
        ('excellent',  'Excellent (18–20)'),
    ]
    etudiant            = models.ForeignKey(Etudiant, on_delete=models.CASCADE, related_name='moyennes')
    classe              = models.ForeignKey(Classe, on_delete=models.CASCADE, related_name='moyennes')
    annee_universitaire = models.CharField(max_length=9, default='2024-2025')
    semestre            = models.IntegerField(choices=[(1,'S1'),(2,'S2')], default=1)
    moyenne             = models.FloatField(null=True, blank=True)
    mention             = models.CharField(max_length=20, choices=MENTION_CHOICES, blank=True)
    admis               = models.BooleanField(default=False)

    class Meta:
        unique_together = ['etudiant','classe','annee_universitaire','semestre']

    @staticmethod
    def calculer_mention(moyenne):
        if moyenne is None: return ''
        if moyenne >= 18:   return 'excellent'
        if moyenne >= 16:   return 'tres_bien'
        if moyenne >= 14:   return 'bien'
        if moyenne >= 12:   return 'assez_bien'
        if moyenne >= 10:   return 'passable'
        return ''

    def __str__(self):
        return f"{self.etudiant} — {self.moyenne}/20 ({self.mention})"
