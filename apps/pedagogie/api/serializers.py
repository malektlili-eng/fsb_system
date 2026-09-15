"""
apps/pedagogie/api/serializers.py
Serializers pour les notes et absences (utilisés par l'API étudiants).
"""
from rest_framework import serializers
from apps.pedagogie.models import Note, Absence, MoyenneEtudiant, Matiere


class MatiereSerializer(serializers.ModelSerializer):
    class Meta:
        model = Matiere
        fields = ['id', 'nom', 'code', 'credits', 'coefficient', 'semestre']


class NoteSerializer(serializers.ModelSerializer):
    matiere_nom = serializers.CharField(source='matiere.nom', read_only=True)
    matiere_code = serializers.CharField(source='matiere.code', read_only=True)
    type_display = serializers.CharField(source='get_type_note_display', read_only=True)

    class Meta:
        model = Note
        fields = [
            'id', 'matiere', 'matiere_nom', 'matiere_code',
            'type_note', 'type_display', 'note',
            'semestre', 'annee_universitaire', 'date_saisie',
        ]


class AbsenceSerializer(serializers.ModelSerializer):
    matiere_nom = serializers.SerializerMethodField()

    class Meta:
        model = Absence
        fields = ['id', 'date', 'justifiee', 'motif', 'matiere_nom']

    def get_matiere_nom(self, obj):
        if obj.seance and obj.seance.matiere:
            return obj.seance.matiere.nom
        return None


class MoyenneSerializer(serializers.ModelSerializer):
    mention_display = serializers.CharField(source='get_mention_display', read_only=True)

    class Meta:
        model = MoyenneEtudiant
        fields = [
            'id', 'semestre', 'annee_universitaire',
            'moyenne', 'mention', 'mention_display', 'admis',
        ]
