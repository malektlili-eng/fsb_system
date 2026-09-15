"""
apps/pedagogie/urls.py (V2 - complet)
"""
from django.urls import path
from . import views

app_name = 'pedagogie'

urlpatterns = [
    # ── Matières ──────────────────────────────────────────────
    path('matieres/', views.matieres_departements, name='matieres'),
    path('matieres/departement/<int:dept_id>/', views.matieres_filieres, name='matieres_filieres'),
    path('matieres/departement/<int:dept_id>/filiere/<int:filiere_id>/',
         views.matieres_liste, name='matieres_liste'),
    path('matieres/ajouter/', views.ajouter_matiere, name='ajouter_matiere'),
    path('matieres/<int:pk>/modifier/', views.modifier_matiere, name='modifier_matiere'),
    path('matieres/<int:pk>/supprimer/', views.supprimer_matiere, name='supprimer_matiere'),

    # ── Emploi du temps ───────────────────────────────────────
    path('emploi-du-temps/', views.edt_departements, name='emploi_du_temps'),
    path('emploi-du-temps/departement/<int:dept_id>/', views.edt_filieres, name='edt_filieres'),
    path('emploi-du-temps/departement/<int:dept_id>/filiere/<int:filiere_id>/',
         views.edt_classes, name='edt_classes'),
    path('emploi-du-temps/classe/<int:classe_id>/', views.edt_classe_detail, name='edt_classe'),
    path('emploi-du-temps/seance/ajouter/', views.ajouter_seance, name='ajouter_seance'),
    path('emploi-du-temps/seance/<int:pk>/modifier/', views.modifier_seance, name='modifier_seance'),
    path('emploi-du-temps/seance/<int:pk>/supprimer/', views.supprimer_seance, name='supprimer_seance'),

    # ── Absences ──────────────────────────────────────────────
    path('absences/', views.absences_departements, name='absences'),
    path('absences/departement/<int:dept_id>/', views.absences_filieres, name='absences_filieres'),
    path('absences/departement/<int:dept_id>/filiere/<int:filiere_id>/',
         views.absences_classes, name='absences_classes'),
    path('absences/classe/<int:classe_id>/', views.absences_classe_detail, name='absences_classe'),

    # ── Notes & Résultats ─────────────────────────────────────
    path('notes/', views.notes_departements, name='notes'),
    path('notes/departement/<int:dept_id>/', views.notes_filieres, name='notes_filieres'),
    path('notes/departement/<int:dept_id>/filiere/<int:filiere_id>/',
         views.notes_classes, name='notes_classes'),
    path('notes/classe/<int:classe_id>/', views.notes_classe_detail, name='notes_classe'),
    path('notes/etudiant/<int:etudiant_id>/releve/', views.releve_notes_etudiant, name='releve_notes_etudiant'),
    path('notes/etudiant/<int:etudiant_id>/attestation/', views.attestation_reussite, name='attestation_reussite'),
    path('notes/classe/<int:classe_id>/calculer/', views.calculer_moyennes, name='calculer_moyennes'),
]
