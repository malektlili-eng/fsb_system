"""
apps/administration/api/serializers.py
─────────────────────────────────────────────────────────────────────
Serializers DRF pour l'API REST.

Les serializers jouent le rôle des formulaires côté API :
- Validation des données entrantes
- Sérialisation des données sortantes
- Contrôle des champs exposés
─────────────────────────────────────────────────────────────────────
"""
from rest_framework import serializers
from apps.administration.models import (
    Etudiant, Enseignant, Filiere, Departement, Inscription, Classe
)


class DepartementSerializer(serializers.ModelSerializer):
    nb_filieres = serializers.SerializerMethodField()
    nb_etudiants = serializers.SerializerMethodField()
    nom_display = serializers.CharField(source='get_nom_display', read_only=True)

    class Meta:
        model = Departement
        fields = ['id', 'nom', 'nom_display', 'chef', 'email',
                  'telephone', 'description', 'nb_filieres', 'nb_etudiants']

    def get_nb_filieres(self, obj):
        return obj.filieres.count()

    def get_nb_etudiants(self, obj):
        return Etudiant.objects.filter(
            filiere__departement=obj, statut='inscrit'
        ).count()


class FiliereSerializer(serializers.ModelSerializer):
    departement_nom = serializers.CharField(
        source='departement.get_nom_display', read_only=True
    )
    nb_etudiants = serializers.SerializerMethodField()
    niveau_display = serializers.CharField(source='get_niveau_display', read_only=True)

    class Meta:
        model = Filiere
        fields = [
            'id', 'nom', 'code', 'departement', 'departement_nom',
            'niveau', 'niveau_display', 'type_formation',
            'description', 'nb_etudiants'
        ]

    def get_nb_etudiants(self, obj):
        return obj.nb_etudiants()


class EtudiantSerializer(serializers.ModelSerializer):
    """Serializer liste (champs essentiels uniquement)."""
    filiere_nom = serializers.CharField(source='filiere.nom', read_only=True)
    nom_complet = serializers.SerializerMethodField()
    statut_display = serializers.CharField(source='get_statut_display', read_only=True)

    class Meta:
        model = Etudiant
        fields = [
            'id', 'nom', 'prenom', 'nom_complet',
            'numero_etudiant', 'email',
            'filiere', 'filiere_nom',
            'statut', 'statut_display',
            'annee_inscription',
        ]

    def get_nom_complet(self, obj):
        return obj.get_full_name()


class EtudiantDetailSerializer(serializers.ModelSerializer):
    """Serializer détail (tous les champs)."""
    filiere_detail = FiliereSerializer(source='filiere', read_only=True)
    statut_display = serializers.CharField(source='get_statut_display', read_only=True)

    class Meta:
        model = Etudiant
        fields = [
            'id', 'nom', 'prenom', 'numero_etudiant', 'cin',
            'email', 'telephone',
            'filiere', 'filiere_detail',
            'annee_inscription', 'date_naissance',
            'lieu_naissance', 'adresse',
            'statut', 'statut_display',
        ]


class EtudiantCreateSerializer(serializers.ModelSerializer):
    """
    Serializer de création — délègue la validation au service.
    Le numéro étudiant est optionnel (auto-généré si absent).
    """
    class Meta:
        model = Etudiant
        fields = [
            'nom', 'prenom', 'numero_etudiant', 'cin',
            'email', 'telephone', 'filiere',
            'annee_inscription', 'date_naissance',
        ]
        extra_kwargs = {
            'numero_etudiant': {'required': False},
            'cin': {'required': False},
            'telephone': {'required': False},
        }

    def validate_nom(self, value):
        if not value.strip():
            raise serializers.ValidationError("Le nom ne peut pas être vide.")
        return value.upper().strip()

    def validate_prenom(self, value):
        if not value.strip():
            raise serializers.ValidationError("Le prénom ne peut pas être vide.")
        return value.title().strip()

    def validate_email(self, value):
        if value:
            if Etudiant.objects.filter(email=value).exists():
                raise serializers.ValidationError("Cet email est déjà utilisé.")
        return value.lower().strip()


class EnseignantSerializer(serializers.ModelSerializer):
    departement_nom = serializers.CharField(
        source='departement.get_nom_display', read_only=True
    )
    grade_display = serializers.CharField(source='get_grade_display', read_only=True)
    nom_complet = serializers.SerializerMethodField()

    class Meta:
        model = Enseignant
        fields = [
            'id', 'nom', 'prenom', 'nom_complet', 'matricule',
            'email', 'telephone',
            'departement', 'departement_nom',
            'grade', 'grade_display',
            'specialite', 'date_recrutement', 'actif',
        ]

    def get_nom_complet(self, obj):
        return obj.get_full_name()


class InscriptionSerializer(serializers.ModelSerializer):
    etudiant_nom = serializers.CharField(
        source='etudiant.get_full_name', read_only=True
    )
    filiere_nom = serializers.CharField(source='filiere.nom', read_only=True)
    statut_display = serializers.CharField(source='get_statut_display', read_only=True)

    class Meta:
        model = Inscription
        fields = [
            'id', 'etudiant', 'etudiant_nom',
            'filiere', 'filiere_nom',
            'annee_universitaire',
            'date_inscription',
            'statut', 'statut_display',
            'commentaire',
            'date_validation', 'valide_par',
        ]
        read_only_fields = ['date_inscription', 'date_validation', 'valide_par']
