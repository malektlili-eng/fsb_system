"""
apps/administration/api/urls.py
─────────────────────────────────────────────────────────────────────
Router DRF — génère automatiquement toutes les URLs CRUD.

Endpoints générés par DefaultRouter :
  GET    /api/etudiants/              Liste paginée + filtres
  POST   /api/etudiants/              Créer un étudiant
  GET    /api/etudiants/{id}/         Détail
  PATCH  /api/etudiants/{id}/         Modification partielle
  DELETE /api/etudiants/{id}/         Suppression
  GET    /api/etudiants/{id}/notes/   Notes de l'étudiant
  GET    /api/etudiants/{id}/absences/ Absences
  PATCH  /api/etudiants/{id}/statut/  Changer le statut

  GET    /api/enseignants/
  GET    /api/filieres/
  GET    /api/departements/
  GET    /api/inscriptions/
  POST   /api/inscriptions/{id}/valider/
  POST   /api/inscriptions/{id}/rejeter/

Auth :
  POST   /api/token/         Obtenir un JWT (username + password)
  POST   /api/token/refresh/ Rafraîchir le JWT
─────────────────────────────────────────────────────────────────────
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .views import (
    EtudiantViewSet,
    EnseignantViewSet,
    FiliereViewSet,
    DepartementViewSet,
    InscriptionViewSet,
)

router = DefaultRouter()
router.register(r'etudiants',    EtudiantViewSet,    basename='etudiant')
router.register(r'enseignants',  EnseignantViewSet,  basename='enseignant')
router.register(r'filieres',     FiliereViewSet,     basename='filiere')
router.register(r'departements', DepartementViewSet, basename='departement')
router.register(r'inscriptions', InscriptionViewSet, basename='inscription')

urlpatterns = [
    # CRUD généré automatiquement
    path('', include(router.urls)),

    # Auth JWT
    path('token/',         TokenObtainPairView.as_view(),  name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(),     name='token_refresh'),
]
