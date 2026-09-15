"""
apps/administration/api/views.py
─────────────────────────────────────────────────────────────────────
API REST complète pour l'administration.

PROBLÈME V1 : pas d'API REST. L'agent IA et les vues accédaient
directement aux modèles sans couche d'abstraction.

SOLUTION V2 : ViewSets DRF avec pagination, filtres, recherche,
permissions RBAC, et documentation OpenAPI auto-générée.

Endpoints générés :
  GET    /api/etudiants/              → liste paginée
  POST   /api/etudiants/              → créer
  GET    /api/etudiants/{id}/         → détail
  PUT    /api/etudiants/{id}/         → modifier complet
  PATCH  /api/etudiants/{id}/         → modifier partiel
  DELETE /api/etudiants/{id}/         → supprimer
  GET    /api/etudiants/{id}/notes/   → notes de l'étudiant
  GET    /api/etudiants/{id}/absences/ → absences
─────────────────────────────────────────────────────────────────────
"""
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, OpenApiParameter

from core.permissions import IsAdminOrReadOnly, CanValidate, IsSuperAdmin
from apps.administration.models import (
    Etudiant, Enseignant, Filiere, Departement, Inscription
)
from apps.administration.services import EtudiantService, InscriptionService
from .serializers import (
    EtudiantSerializer, EtudiantDetailSerializer, EtudiantCreateSerializer,
    EnseignantSerializer, FiliereSerializer, DepartementSerializer,
    InscriptionSerializer,
)


class EtudiantViewSet(viewsets.ModelViewSet):
    """
    CRUD complet sur les étudiants.
    - Lecture : tous les utilisateurs authentifiés
    - Écriture : admin, scolarite, super_admin
    - Suppression : admin, super_admin uniquement
    """
    queryset = (
        Etudiant.objects
        .select_related('filiere', 'filiere__departement')
        .order_by('nom', 'prenom')
    )
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = {
        'statut': ['exact'],
        'filiere': ['exact'],
        'filiere__departement': ['exact'],
        'annee_inscription': ['exact', 'gte', 'lte'],
    }
    search_fields = ['nom', 'prenom', 'numero_etudiant', 'email', 'cin']
    ordering_fields = ['nom', 'prenom', 'numero_etudiant', 'annee_inscription']

    def get_serializer_class(self):
        """Serializer différent selon l'action."""
        if self.action == 'create':
            return EtudiantCreateSerializer
        if self.action in ('retrieve', 'update', 'partial_update'):
            return EtudiantDetailSerializer
        return EtudiantSerializer

    def perform_create(self, serializer):
        """Déléguer la création au service pour avoir la logique métier et l'audit."""
        etudiant = EtudiantService.creer(
            data=self.request.data,
            created_by=self.request.user
        )
        # Le serializer a déjà validé, on retourne l'instance créée
        serializer.instance = etudiant

    def destroy(self, request, *args, **kwargs):
        """Seuls admin et super_admin peuvent supprimer."""
        if request.user.role not in ('admin', 'super_admin'):
            return Response(
                {'detail': 'Permission refusée. Rôle admin requis.'},
                status=status.HTTP_403_FORBIDDEN
            )
        return super().destroy(request, *args, **kwargs)

    @extend_schema(summary="Notes de l'étudiant", tags=['étudiants'])
    @action(detail=True, methods=['get'], url_path='notes')
    def notes(self, request, pk=None):
        """Retourne toutes les notes d'un étudiant."""
        from apps.pedagogie.models import Note
        from apps.pedagogie.api.serializers import NoteSerializer
        etudiant = self.get_object()
        notes = Note.objects.filter(etudiant=etudiant).select_related('matiere')
        return Response(NoteSerializer(notes, many=True).data)

    @extend_schema(summary="Absences de l'étudiant", tags=['étudiants'])
    @action(detail=True, methods=['get'], url_path='absences')
    def absences(self, request, pk=None):
        """Retourne toutes les absences d'un étudiant."""
        from apps.pedagogie.models import Absence
        from apps.pedagogie.api.serializers import AbsenceSerializer
        etudiant = self.get_object()
        absences = Absence.objects.filter(etudiant=etudiant).select_related('seance__matiere')
        return Response(AbsenceSerializer(absences, many=True).data)

    @extend_schema(summary="Changer le statut", tags=['étudiants'])
    @action(detail=True, methods=['patch'], url_path='statut')
    def changer_statut(self, request, pk=None):
        """Change le statut d'un étudiant (inscrit → diplômé, etc.)."""
        etudiant = self.get_object()
        nouveau_statut = request.data.get('statut')
        if not nouveau_statut:
            return Response({'detail': 'Champ statut requis.'}, status=400)
        try:
            etudiant = EtudiantService.changer_statut(
                etudiant, nouveau_statut, changed_by=request.user
            )
            return Response(EtudiantSerializer(etudiant).data)
        except Exception as e:
            return Response({'detail': str(e)}, status=400)


class EnseignantViewSet(viewsets.ModelViewSet):
    """CRUD pour les enseignants."""
    queryset = (
        Enseignant.objects
        .select_related('departement')
        .filter(actif=True)
        .order_by('nom', 'prenom')
    )
    serializer_class = EnseignantSerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['departement', 'grade', 'actif']
    search_fields = ['nom', 'prenom', 'matricule', 'specialite']

    @action(detail=True, methods=['patch'], url_path='desactiver')
    def desactiver(self, request, pk=None):
        """Désactive un enseignant (soft delete)."""
        enseignant = self.get_object()
        enseignant.actif = False
        enseignant.save(update_fields=['actif'])
        return Response({'detail': f'{enseignant} désactivé.'})


class FiliereViewSet(viewsets.ModelViewSet):
    """CRUD pour les filières."""
    queryset = Filiere.objects.select_related('departement').order_by('departement', 'nom')
    serializer_class = FiliereSerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['departement', 'niveau', 'type_formation']
    search_fields = ['nom', 'code']


class DepartementViewSet(viewsets.ReadOnlyModelViewSet):
    """Lecture seule des départements (modification via l'admin Django)."""
    queryset = Departement.objects.prefetch_related('filieres').order_by('nom')
    serializer_class = DepartementSerializer
    permission_classes = [IsAdminOrReadOnly]


class InscriptionViewSet(viewsets.ModelViewSet):
    """Gestion des inscriptions avec workflow de validation."""
    queryset = (
        Inscription.objects
        .select_related('etudiant', 'filiere')
        .order_by('-date_inscription')
    )
    serializer_class = InscriptionSerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['statut', 'annee_universitaire', 'filiere']

    @extend_schema(summary="Valider une inscription", tags=['inscriptions'])
    @action(detail=True, methods=['post'], url_path='valider',
            permission_classes=[CanValidate])
    def valider(self, request, pk=None):
        """Valide une inscription (nécessite rôle admin/doyen/chef_dept)."""
        inscription = self.get_object()
        try:
            inscription = InscriptionService.valider(
                inscription, validated_by=request.user
            )
            return Response(InscriptionSerializer(inscription).data)
        except Exception as e:
            return Response({'detail': str(e)}, status=400)

    @extend_schema(summary="Rejeter une inscription", tags=['inscriptions'])
    @action(detail=True, methods=['post'], url_path='rejeter',
            permission_classes=[CanValidate])
    def rejeter(self, request, pk=None):
        """Rejette une inscription avec une raison."""
        inscription = self.get_object()
        raison = request.data.get('raison', '')
        if not raison:
            return Response({'detail': 'Une raison est requise.'}, status=400)
        try:
            inscription = InscriptionService.rejeter(
                inscription, raison=raison, rejected_by=request.user
            )
            return Response(InscriptionSerializer(inscription).data)
        except Exception as e:
            return Response({'detail': str(e)}, status=400)
