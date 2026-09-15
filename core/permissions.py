"""
core/permissions.py
─────────────────────────────────────────────────────────────────────
Système de contrôle d'accès basé sur les rôles (RBAC).

PROBLÈME V1 : toutes les vues utilisaient @login_required uniquement.
N'importe quel utilisateur connecté pouvait tout faire.

SOLUTION V2 : décorateur @role_required(*roles) + permissions DRF.
─────────────────────────────────────────────────────────────────────
"""
from functools import wraps
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.contrib import messages
from rest_framework.permissions import BasePermission


# ─── Hiérarchie des rôles ─────────────────────────────────────────────
ROLE_HIERARCHY = {
    'super_admin': 5,
    'doyen':       4,
    'chef_dept':   3,
    'admin':       2,
    'scolarite':   1,
}


def role_required(*roles):
    """
    Décorateur pour les vues Django classiques (templates).

    Usage :
        @role_required('super_admin', 'admin')
        def supprimer_etudiant(request, pk):
            ...

        @role_required('super_admin')
        def gestion_utilisateurs(request):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapper(request, *args, **kwargs):
            if request.user.role not in roles:
                messages.error(
                    request,
                    f"Accès refusé. Cette action requiert le rôle : "
                    f"{' ou '.join(roles)}."
                )
                raise PermissionDenied
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def min_role_required(min_role: str):
    """
    Décorateur basé sur le niveau de rôle minimum.

    Usage :
        @min_role_required('admin')   # admin + chef_dept + doyen + super_admin
        def valider_inscription(request):
            ...
    """
    min_level = ROLE_HIERARCHY.get(min_role, 0)

    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapper(request, *args, **kwargs):
            user_level = ROLE_HIERARCHY.get(request.user.role, 0)
            if user_level < min_level:
                raise PermissionDenied
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


# ─── Permissions DRF (pour l'API REST) ───────────────────────────────

class HasRolePermission(BasePermission):
    """
    Permission DRF qui lit l'attribut `required_roles` sur la vue.

    Usage dans un ViewSet :
        class EtudiantViewSet(viewsets.ModelViewSet):
            required_roles = ['admin', 'scolarite', 'super_admin']
    """
    def has_permission(self, request, view):
        required = getattr(view, 'required_roles', None)
        if required is None:
            return request.user.is_authenticated
        return (
            request.user.is_authenticated
            and request.user.role in required
        )


class IsAdminOrReadOnly(BasePermission):
    """Lecture pour tous les authentifiés, écriture pour admin+."""
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return True
        return request.user.role in ('super_admin', 'admin', 'scolarite')


class IsSuperAdmin(BasePermission):
    """Réservé aux super administrateurs."""
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role == 'super_admin'
        )


class CanValidate(BasePermission):
    """Doyen, chef_dept, admin, super_admin."""
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role in ('super_admin', 'admin', 'chef_dept', 'doyen')
        )


# ─── Matrice de permissions par fonctionnalité ───────────────────────
#
# Fonctionnalité                | super_admin | doyen | chef_dept | admin | scolarite
# Créer/modifier étudiant       |     ✓       |       |           |   ✓   |     ✓
# Supprimer étudiant            |     ✓       |       |           |   ✓   |
# Valider inscription           |     ✓       |   ✓   |     ✓     |   ✓   |
# Valider diplôme               |     ✓       |   ✓   |     ✓     |   ✓   |
# Gérer enseignants             |     ✓       |       |     ✓     |   ✓   |     ✓
# Gérer utilisateurs du système |     ✓       |       |           |       |
# Saisir notes                  |     ✓       |       |           |   ✓   |     ✓
# Voir toutes les données       |     ✓       |   ✓   |     ✓     |   ✓   |     ✓
#
