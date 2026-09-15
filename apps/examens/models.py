"""
apps/examens/models.py (V2)
"""
from django.db import models
from apps.administration.models import Etudiant, Salle, Classe, Enseignant, TimeStampedModel
from apps.pedagogie.models import Matiere


class SessionExamen(TimeStampedModel):
    TYPE_CHOICES = [('principale','Principale'),('rattrapage','Rattrapage')]
    nom                 = models.CharField(max_length=100)
    type_session        = models.CharField(max_length=15, choices=TYPE_CHOICES)
    annee_universitaire = models.CharField(max_length=9)
    semestre            = models.IntegerField(choices=[(1,'S1'),(2,'S2')])
    date_debut          = models.DateField()
    date_fin            = models.DateField()

    class Meta:
        ordering = ['-date_debut']

    def __str__(self):
        return f"Session {self.nom} — {self.annee_universitaire}"


class PlanningExamen(TimeStampedModel):
    session      = models.ForeignKey(SessionExamen, on_delete=models.CASCADE)
    matiere      = models.ForeignKey(Matiere, on_delete=models.CASCADE)
    salle        = models.ForeignKey(Salle, on_delete=models.SET_NULL, null=True, blank=True)
    classe       = models.ForeignKey(Classe, on_delete=models.SET_NULL, null=True, blank=True, related_name='examens')
    date         = models.DateField()
    heure_debut  = models.TimeField()
    heure_fin    = models.TimeField()
    surveillants = models.ManyToManyField(Enseignant, blank=True)

    class Meta:
        ordering = ['date', 'heure_debut']
        indexes  = [models.Index(fields=['date', 'salle'])]

    def is_conflit_salle(self):
        if not self.salle: return False
        return PlanningExamen.objects.filter(
            salle=self.salle, date=self.date,
            heure_debut__lt=self.heure_fin,
            heure_fin__gt=self.heure_debut,
        ).exclude(pk=self.pk).exists()

    def is_conflit_classe(self):
        if not self.classe: return False
        return PlanningExamen.objects.filter(
            classe=self.classe, date=self.date,
            heure_debut__lt=self.heure_fin,
            heure_fin__gt=self.heure_debut,
        ).exclude(pk=self.pk).exists()

    def __str__(self):
        return f"{self.matiere} — {self.date}"


class ResultatExamen(TimeStampedModel):
    etudiant    = models.ForeignKey(Etudiant, on_delete=models.CASCADE)
    session     = models.ForeignKey(SessionExamen, on_delete=models.CASCADE)
    matiere     = models.ForeignKey(Matiere, on_delete=models.CASCADE)
    note_exam   = models.FloatField(null=True, blank=True)
    note_ds     = models.FloatField(null=True, blank=True)
    note_tp     = models.FloatField(null=True, blank=True)
    note_finale = models.FloatField(null=True, blank=True)
    valide      = models.BooleanField(default=False)

    class Meta:
        unique_together = ['etudiant','session','matiere']

    def calculer_note_finale(self):
        if self.note_exam and self.note_ds:
            self.note_finale = (self.note_exam * 0.6) + (self.note_ds * 0.4)
            self.valide = self.note_finale >= 10
            return self.note_finale
        return None

    def __str__(self):
        return f"{self.etudiant} — {self.matiere}: {self.note_finale}"
