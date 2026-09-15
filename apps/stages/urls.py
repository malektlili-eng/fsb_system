"""
apps/stages/urls.py (V2)
"""
from django.urls import path
from . import views

app_name = 'stages'

urlpatterns = [
    path('demandes/', views.liste_demandes, name='demandes'),
    path('demandes/<int:pk>/', views.detail_demande, name='detail_demande'),
    path('demandes/<int:pk>/attestation/', views.attestation_stage, name='attestation_stage'),

    path('diplomes/', views.liste_diplomes, name='diplomes'),
    path('diplomes/ajouter/', views.ajouter_diplome, name='ajouter_diplome'),
    path('diplomes/eligibles/', views.etudiants_eligibles_diplome, name='eligibles_diplome'),
    path('diplomes/generer/<int:etudiant_id>/', views.generer_diplome, name='generer_diplome'),
    path('diplomes/<int:pk>/officiel/', views.diplome_officiel, name='diplome_officiel'),
]
