"""
apps/administration/urls.py (V2)
"""
from django.urls import path
from . import views

app_name = 'administration'

urlpatterns = [
    # Dashboard
    path('', views.dashboard, name='dashboard'),

    # Étudiants — navigation 4 niveaux
    path('etudiants/',
         views.etudiants_departements, name='liste_etudiants'),
    path('etudiants/departement/<int:dept_id>/',
         views.etudiants_filieres, name='etudiants_filieres'),
    path('etudiants/departement/<int:dept_id>/filiere/<int:filiere_id>/',
         views.etudiants_classes, name='etudiants_classes'),
    path('etudiants/departement/<int:dept_id>/filiere/<int:filiere_id>/classe/<int:classe_id>/',
         views.etudiants_liste_classe, name='etudiants_liste_classe'),
    path('etudiants/<int:pk>/',
         views.detail_etudiant, name='detail_etudiant'),
    path('etudiants/ajouter/',
         views.ajouter_etudiant, name='ajouter_etudiant'),
    path('etudiants/<int:pk>/modifier/',
         views.modifier_etudiant, name='modifier_etudiant'),
    path('etudiants/<int:pk>/supprimer/',
         views.supprimer_etudiant, name='supprimer_etudiant'),
    path('etudiants/<int:etudiant_id>/releve/',
         views.releve_notes, name='releve_notes'),

    # Enseignants
    path('enseignants/',
         views.enseignants_departements, name='liste_enseignants'),
    path('enseignants/departement/<int:dept_id>/',
         views.enseignants_liste, name='enseignants_liste'),
    path('enseignants/<int:pk>/',
         views.detail_enseignant, name='detail_enseignant'),
    path('enseignants/ajouter/',
         views.ajouter_enseignant, name='ajouter_enseignant'),
    path('enseignants/<int:pk>/modifier/',
         views.modifier_enseignant, name='modifier_enseignant'),

    # Inscriptions & Salles
    path('inscriptions/',       views.gestion_inscriptions, name='inscriptions'),
    path('inscriptions/<int:pk>/valider/',
         views.valider_inscription, name='valider_inscription'),
    path('attestation/<int:pk>/',
         views.attestation_inscription, name='attestation'),
    path('salles/',             views.gestion_salles, name='salles'),

    # Navigation formations (dashboard)
    path('formation/<str:type_formation>/',
         views.formation_detail, name='formation_detail'),
    path('formation/<str:type_formation>/departement/<int:dept_id>/',
         views.departement_detail, name='departement_detail'),
    path('formation/<str:type_formation>/departement/<int:dept_id>/filiere/<int:filiere_id>/',
         views.filiere_detail, name='filiere_detail'),
]
