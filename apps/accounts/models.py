"""
apps/accounts/models.py (V2)
─────────────────────────────────────────────────────────────────────
Modèle CustomUser avec rôles.
Identique à la V1 — pas de changement de schéma nécessaire.
─────────────────────────────────────────────────────────────────────
"""
from django.contrib.auth.models import AbstractUser
from django.db import models


class CustomUser(AbstractUser):
    ROLE_CHOICES = [
        ('super_admin', 'Super Administrateur'),
        ('admin',       'Administrateur'),
        ('scolarite',   'Agent Scolarité'),
        ('chef_dept',   'Chef de Département'),
        ('doyen',       'Doyen / Vice-Doyen'),
    ]
    role        = models.CharField(max_length=20, choices=ROLE_CHOICES, default='scolarite')
    telephone   = models.CharField(max_length=20, blank=True)
    departement = models.CharField(max_length=50, blank=True)

    def __str__(self):
        return f"{self.get_full_name()} ({self.get_role_display()})"

    # ─── Propriétés de permission ────────────────────────────────
    @property
    def is_super_admin(self):
        return self.role == 'super_admin'

    @property
    def can_edit(self):
        return self.role in ('super_admin', 'admin', 'scolarite')

    @property
    def can_validate(self):
        return self.role in ('super_admin', 'admin', 'chef_dept', 'doyen')

    @property
    def can_delete(self):
        return self.role in ('super_admin', 'admin')
