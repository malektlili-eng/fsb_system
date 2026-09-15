"""
apps/administration/admin.py (V2)
Interface d'administration Django enrichie.
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html
from apps.accounts.models import CustomUser
from .models import (
    Departement, Filiere, Classe,
    Enseignant, Etudiant, Salle,
    Inscription, AuditLog,
)


# ─── CustomUser ───────────────────────────────────────────────────

@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display  = ('username', 'get_full_name', 'email', 'role', 'is_active')
    list_filter   = ('role', 'is_active')
    search_fields = ('username', 'first_name', 'last_name', 'email')
    fieldsets     = UserAdmin.fieldsets + (
        ('FSB', {'fields': ('role', 'telephone', 'departement')}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('FSB', {'fields': ('role', 'telephone', 'departement')}),
    )


# ─── Département / Filière / Classe ──────────────────────────────

@admin.register(Departement)
class DepartementAdmin(admin.ModelAdmin):
    list_display  = ('nom', 'get_nom_display', 'chef', 'email', 'created_at')
    search_fields = ('nom', 'chef')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Filiere)
class FiliereAdmin(admin.ModelAdmin):
    list_display  = ('code', 'nom', 'departement', 'niveau', 'type_formation',
                     'nb_etudiants')
    list_filter   = ('departement', 'niveau', 'type_formation')
    search_fields = ('nom', 'code')
    readonly_fields = ('created_at', 'updated_at')

    def nb_etudiants(self, obj):
        return obj.nb_etudiants()
    nb_etudiants.short_description = 'Étudiants'


@admin.register(Classe)
class ClasseAdmin(admin.ModelAdmin):
    list_display  = ('code', 'nom', 'filiere', 'niveau', 'annee_universitaire')
    list_filter   = ('niveau', 'annee_universitaire', 'filiere__departement')
    search_fields = ('nom', 'code')


# ─── Enseignant ───────────────────────────────────────────────────

@admin.register(Enseignant)
class EnseignantAdmin(admin.ModelAdmin):
    list_display  = ('matricule', 'get_full_name', 'departement', 'grade', 'actif')
    list_filter   = ('departement', 'grade', 'actif')
    search_fields = ('nom', 'prenom', 'matricule', 'email')
    readonly_fields = ('created_at', 'updated_at')
    list_editable = ('actif',)


# ─── Étudiant ─────────────────────────────────────────────────────

@admin.register(Etudiant)
class EtudiantAdmin(admin.ModelAdmin):
    list_display  = ('numero_etudiant', 'get_full_name', 'filiere', 'statut',
                     'annee_inscription', 'email')
    list_filter   = ('statut', 'annee_inscription', 'filiere__departement', 'filiere')
    search_fields = ('nom', 'prenom', 'numero_etudiant', 'email', 'cin')
    readonly_fields = ('created_at', 'updated_at')
    list_per_page = 50

    def get_full_name(self, obj):
        return obj.get_full_name()
    get_full_name.short_description = 'Nom complet'


# ─── Salle ────────────────────────────────────────────────────────

@admin.register(Salle)
class SalleAdmin(admin.ModelAdmin):
    list_display = ('nom', 'type_salle', 'capacite', 'batiment')
    list_filter  = ('type_salle', 'batiment')
    search_fields = ('nom',)


# ─── Inscription ──────────────────────────────────────────────────

@admin.register(Inscription)
class InscriptionAdmin(admin.ModelAdmin):
    list_display  = ('etudiant', 'filiere', 'annee_universitaire',
                     'statut', 'date_inscription', 'valide_par')
    list_filter   = ('statut', 'annee_universitaire', 'filiere__departement')
    search_fields = ('etudiant__nom', 'etudiant__prenom', 'etudiant__numero_etudiant')
    readonly_fields = ('date_inscription', 'created_at', 'updated_at')
    date_hierarchy  = 'date_inscription'


# ─── AuditLog ─────────────────────────────────────────────────────

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display  = ('timestamp', 'user', 'action', 'model_name', 'object_id', 'details_court')
    list_filter   = ('action', 'model_name')
    search_fields = ('user__username', 'details', 'model_name')
    readonly_fields = ('timestamp', 'user', 'action', 'model_name', 'object_id',
                       'details', 'ip_address')
    date_hierarchy = 'timestamp'

    def details_court(self, obj):
        return obj.details[:80] + '…' if len(obj.details) > 80 else obj.details
    details_court.short_description = 'Détails'

    def has_add_permission(self, request):
        return False  # Les logs ne se créent pas manuellement

    def has_change_permission(self, request, obj=None):
        return False  # Les logs ne se modifient pas
