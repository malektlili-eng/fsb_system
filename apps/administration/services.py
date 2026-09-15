"""
apps/administration/services.py (V2 - corrigé)
"""
from __future__ import annotations

import logging
from datetime import date
from typing import TYPE_CHECKING

from django.db import transaction
from django.core.exceptions import ValidationError

# Les modèles sont importés paresseusement DANS les fonctions pour
# éviter les imports circulaires au chargement des applications. Ce bloc
# ne s'exécute jamais à l'exécution : il sert uniquement aux annotations
# de type (et à flake8, qui sinon signale F821 sur chaque annotation).
if TYPE_CHECKING:  # pragma: no cover
    from apps.administration.models import Etudiant, Inscription

logger = logging.getLogger(__name__)


class EtudiantService:

    @staticmethod
    def generer_numero(annee: int = None) -> str:
        from apps.administration.models import Etudiant
        if annee is None:
            annee = date.today().year
        with transaction.atomic():
            count = (
                Etudiant.objects
                .select_for_update()
                .filter(annee_inscription=annee)
                .count()
            ) + 1
            numero = f"ETU{annee}{count:05d}"
            while Etudiant.objects.filter(numero_etudiant=numero).exists():
                count += 1
                numero = f"ETU{annee}{count:05d}"
        return numero

    @staticmethod
    @transaction.atomic
    def creer(data: dict, created_by=None) -> 'Etudiant':
        """
        Crée un étudiant. data peut être un dict brut ou cleaned_data d'un form.
        numero_etudiant et statut sont auto-générés si absents.
        """
        from apps.administration.models import Etudiant, Filiere
        from apps.administration.forms import EtudiantForm

        # Normaliser data : filiere peut être un int (id) ou une instance
        form_data = {}
        for k, v in data.items():
            if k == 'filiere' and hasattr(v, 'pk'):
                form_data[k] = v.pk
            else:
                form_data[k] = v

        form = EtudiantForm(form_data)
        if not form.is_valid():
            raise ValidationError(dict(form.errors))

        etudiant = form.save(commit=False)

        if not etudiant.numero_etudiant:
            etudiant.numero_etudiant = EtudiantService.generer_numero(
                annee=etudiant.annee_inscription or date.today().year
            )

        if not etudiant.statut:
            etudiant.statut = 'inscrit'

        if not etudiant.email:
            prenom = (etudiant.prenom or '').lower().replace(' ', '.')
            nom = (etudiant.nom or '').lower().replace(' ', '.')
            # Générer email unique
            base = f"{prenom}.{nom}@etu.fsb.tn"
            email = base
            counter = 1
            while Etudiant.objects.filter(email=email).exists():
                email = f"{prenom}.{nom}{counter}@etu.fsb.tn"
                counter += 1
            etudiant.email = email

        if not etudiant.annee_inscription:
            etudiant.annee_inscription = date.today().year

        etudiant.save()

        AuditLogService.log(
            user=created_by,
            action='CREATE',
            model='Etudiant',
            object_id=etudiant.pk,
            details=f"Étudiant {etudiant.get_full_name()} (N°{etudiant.numero_etudiant}) créé"
        )
        logger.info(f"Étudiant créé : {etudiant} par {getattr(created_by, 'username', 'système')}")
        return etudiant

    @staticmethod
    @transaction.atomic
    def modifier(etudiant, data: dict, modified_by=None) -> 'Etudiant':
        from apps.administration.forms import EtudiantForm
        form_data = {}
        for k, v in data.items():
            if k == 'filiere' and hasattr(v, 'pk'):
                form_data[k] = v.pk
            else:
                form_data[k] = v
        form = EtudiantForm(form_data, instance=etudiant)
        if not form.is_valid():
            raise ValidationError(dict(form.errors))
        etudiant = form.save()
        AuditLogService.log(
            user=modified_by, action='UPDATE', model='Etudiant',
            object_id=etudiant.pk, details=f"Étudiant {etudiant.get_full_name()} modifié"
        )
        return etudiant

    @staticmethod
    @transaction.atomic
    def changer_statut(etudiant, nouveau_statut: str, changed_by=None) -> 'Etudiant':
        from apps.administration.models import Etudiant
        statuts_valides = [c[0] for c in Etudiant.STATUT_CHOICES]
        if nouveau_statut not in statuts_valides:
            raise ValidationError(f"Statut invalide : {nouveau_statut}")
        ancien = etudiant.statut
        etudiant.statut = nouveau_statut
        etudiant.save(update_fields=['statut'])
        AuditLogService.log(
            user=changed_by, action='STATUS_CHANGE', model='Etudiant',
            object_id=etudiant.pk, details=f"Statut : {ancien} → {nouveau_statut}"
        )
        return etudiant


class InscriptionService:

    @staticmethod
    @transaction.atomic
    def valider(inscription, validated_by=None) -> 'Inscription':
        if inscription.statut == 'validee':
            raise ValidationError("Inscription déjà validée.")
        inscription.statut = 'validee'
        inscription.date_validation = date.today()
        inscription.valide_par = getattr(validated_by, 'get_full_name', lambda: 'système')()
        inscription.save()
        AuditLogService.log(
            user=validated_by, action='VALIDATE', model='Inscription',
            object_id=inscription.pk,
            details=f"Inscription de {inscription.etudiant} validée"
        )
        return inscription

    @staticmethod
    @transaction.atomic
    def rejeter(inscription, raison: str, rejected_by=None) -> 'Inscription':
        inscription.statut = 'annulee'
        inscription.commentaire = raison
        inscription.save()
        AuditLogService.log(
            user=rejected_by, action='REJECT', model='Inscription',
            object_id=inscription.pk,
            details=f"Inscription de {inscription.etudiant} rejetée : {raison}"
        )
        return inscription


class AuditLogService:

    @staticmethod
    def log(user, action: str, model: str, object_id: int, details: str = ''):
        try:
            from apps.administration.models import AuditLog
            AuditLog.objects.create(
                user=user,
                action=action,
                model_name=model,
                object_id=object_id,
                details=details,
            )
        except Exception as e:
            logger.error(f"Erreur audit log : {e}")
