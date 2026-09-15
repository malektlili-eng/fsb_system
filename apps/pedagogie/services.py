"""
apps/pedagogie/services.py
apps/stages/services.py
apps/examens/services.py
─────────────────────────────────────────────────────────────────────
Couches de service pour pédagogie, stages et examens.
Logique métier extraite des vues, testable indépendamment.
─────────────────────────────────────────────────────────────────────
"""

# ══════════════════════════════════════════════════════════════════
# PÉDAGOGIE
# ══════════════════════════════════════════════════════════════════

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.db import transaction
from django.core.exceptions import ValidationError

# Imports paresseux dans les fonctions pour éviter les cycles entre
# applications. Ce bloc n'est jamais exécuté à l'exécution : il ne sert
# qu'aux annotations de type (et à flake8, qui signalerait sinon F821
# sur chaque annotation de retour).
if TYPE_CHECKING:  # pragma: no cover
    from apps.examens.models import PlanningExamen
    from apps.pedagogie.models import Absence, Note
    from apps.stages.models import DemandeStage, Diplome

logger = logging.getLogger(__name__)


class MoyenneService:
    """
    Calcul des moyennes pondérées avec coefficients.

    Règle tunisienne standard :
      Note matière = DS×40% + Examen×60% (si TP : ×70% + TP×30%)
      Moyenne semestre = Σ(note_mat × coeff) / Σ(coeff)
    """

    @staticmethod
    @transaction.atomic
    def calculer_classe(classe, semestre: int, annee: str, calculated_by=None) -> dict:
        """
        Calcule les moyennes de tous les étudiants d'une classe.

        Returns:
            dict avec nb_calcules, nb_admis, nb_echec
        """
        from apps.pedagogie.models import Note, MoyenneEtudiant, Matiere
        from apps.administration.models import Etudiant

        etudiants = Etudiant.objects.filter(
            filiere=classe.filiere, statut='inscrit'
        )
        matieres = Matiere.objects.filter(
            filiere=classe.filiere, semestre=semestre
        )

        nb_calcules = 0
        nb_admis = 0

        for etudiant in etudiants:
            somme_pond = 0.0
            somme_coeff = 0.0

            for mat in matieres:
                note_mat = MoyenneService._note_matiere(
                    etudiant, mat, semestre, annee
                )
                if note_mat is not None:
                    somme_pond += note_mat * mat.coefficient
                    somme_coeff += mat.coefficient

            if somme_coeff == 0:
                continue

            moy = round(somme_pond / somme_coeff, 2)
            mention = MoyenneEtudiant.calculer_mention(moy)

            MoyenneEtudiant.objects.update_or_create(
                etudiant=etudiant,
                classe=classe,
                annee_universitaire=annee,
                semestre=semestre,
                defaults={
                    'moyenne': moy,
                    'mention': mention,
                    'admis':   moy >= 10.0,
                }
            )
            nb_calcules += 1
            if moy >= 10.0:
                nb_admis += 1

        logger.info(
            f"Moyennes calculées : {nb_calcules} étudiants, classe {classe}, "
            f"S{semestre} {annee}"
        )
        return {
            'nb_calcules': nb_calcules,
            'nb_admis': nb_admis,
            'nb_echec': nb_calcules - nb_admis,
            'taux_reussite': round(nb_admis / nb_calcules * 100, 1) if nb_calcules else 0,
        }

    @staticmethod
    def _note_matiere(etudiant, matiere, semestre: int, annee: str):
        """Calcule la note pondérée pour une matière."""
        from apps.pedagogie.models import Note

        notes = Note.objects.filter(
            etudiant=etudiant,
            matiere=matiere,
            semestre=semestre,
            annee_universitaire=annee,
        )
        if not notes.exists():
            return None

        note_ds   = notes.filter(type_note='ds').first()
        note_exam = notes.filter(type_note='exam').first()
        note_tp   = notes.filter(type_note='tp').first()

        # Calcul base : DS + Examen
        if note_ds and note_exam:
            base = note_ds.note * 0.4 + note_exam.note * 0.6
        elif note_exam:
            base = note_exam.note
        elif note_ds:
            base = note_ds.note
        else:
            from django.db.models import Avg
            base = notes.aggregate(Avg('note'))['note__avg'] or 0

        # Intégration TP si présent
        if note_tp:
            return round(base * 0.7 + note_tp.note * 0.3, 2)

        return round(base, 2)

    @staticmethod
    def saisir_note(etudiant, matiere, type_note: str, valeur: float,
                    semestre: int, annee: str, saisie_par=None) -> 'Note':
        """
        Saisit ou met à jour une note avec validation.

        Raises:
            ValidationError si la note est hors plage [0, 20]
        """
        from apps.pedagogie.models import Note
        from apps.administration.services import AuditLogService

        if not (0 <= valeur <= 20):
            raise ValidationError(f"La note {valeur} est hors plage [0, 20].")

        # Arrondir au quart de point
        valeur = round(valeur * 4) / 4

        note, created = Note.objects.update_or_create(
            etudiant=etudiant,
            matiere=matiere,
            type_note=type_note,
            annee_universitaire=annee,
            semestre=semestre,
            defaults={
                'note': valeur,
                'saisie_par': saisie_par.get_full_name() if saisie_par else '',
                'enseignant': None,
            }
        )

        action = 'Saisie' if created else 'Modification'
        logger.info(
            f"{action} note {type_note} pour {etudiant} en {matiere} : {valeur}/20"
        )
        return note


class AbsenceService:
    """Gestion des absences avec calcul du seuil d'élimination."""

    @staticmethod
    def enregistrer(etudiant, seance, date, justifiee: bool = False,
                    motif: str = '', created_by=None) -> 'Absence':
        from apps.pedagogie.models import Absence

        absence, created = Absence.objects.get_or_create(
            etudiant=etudiant,
            seance=seance,
            date=date,
            defaults={'justifiee': justifiee, 'motif': motif}
        )
        if not created:
            absence.justifiee = justifiee
            absence.motif = motif
            absence.save()

        return absence

    @staticmethod
    def est_elimine(etudiant, matiere) -> bool:
        """Vérifie si un étudiant dépasse le seuil d'élimination (25% heures)."""
        from apps.pedagogie.models import Absence

        nb_abs = Absence.objects.filter(
            etudiant=etudiant,
            seance__matiere=matiere,
        ).count()
        seuil = matiere.seuil_elimination()
        return seuil > 0 and nb_abs > seuil


# ══════════════════════════════════════════════════════════════════
# STAGES & DIPLÔMES
# ══════════════════════════════════════════════════════════════════

class StageService:
    """Workflow de gestion des demandes de stage."""

    TRANSITIONS_AUTORISEES = {
        'en_attente': ['valide', 'refuse'],
        'valide':     ['en_cours', 'refuse'],
        'en_cours':   ['termine'],
        'refuse':     [],
        'termine':    [],
    }

    @staticmethod
    @transaction.atomic
    def changer_statut(demande, nouveau_statut: str, changed_by,
                       commentaire: str = '', note_stage: float = None) -> 'DemandeStage':
        from apps.stages.models import DemandeStage
        from apps.administration.services import AuditLogService

        transitions = StageService.TRANSITIONS_AUTORISEES.get(demande.statut, [])
        if nouveau_statut not in transitions:
            raise ValidationError(
                f"Transition '{demande.statut}' → '{nouveau_statut}' non autorisée. "
                f"Transitions possibles : {transitions or 'aucune'}"
            )

        ancien_statut = demande.statut
        demande.statut = nouveau_statut

        if commentaire:
            demande.commentaire_admin = commentaire

        if nouveau_statut == 'termine' and note_stage is not None:
            if not (0 <= note_stage <= 20):
                raise ValidationError("La note de stage doit être entre 0 et 20.")
            demande.note_stage = note_stage

        demande.save()

        AuditLogService.log(
            user=changed_by,
            action='STATUS_CHANGE',
            model='DemandeStage',
            object_id=demande.pk,
            details=f"Statut : {ancien_statut} → {nouveau_statut}"
        )
        return demande

    @staticmethod
    def valider(demande, encadrant_fsb_id, commentaire: str, validated_by) -> 'DemandeStage':
        demande.encadrant_fsb_id = encadrant_fsb_id or None
        return StageService.changer_statut(
            demande, 'valide', validated_by, commentaire
        )

    @staticmethod
    def refuser(demande, commentaire: str, refused_by) -> 'DemandeStage':
        if not commentaire.strip():
            raise ValidationError("Un motif de refus est obligatoire.")
        return StageService.changer_statut(
            demande, 'refuse', refused_by, commentaire
        )

    @staticmethod
    def terminer(demande, note_stage: float, terminated_by) -> 'DemandeStage':
        return StageService.changer_statut(
            demande, 'termine', terminated_by, note_stage=note_stage
        )


class DiplomeService:
    """Génération et validation des diplômes."""

    NIVEAUX_TERMINAUX = ['L3', 'M2', 'Doc', 'CI3']

    @staticmethod
    def verifier_eligibilite(etudiant) -> dict:
        """
        Vérifie si un étudiant remplit toutes les conditions pour obtenir son diplôme.

        Returns:
            dict avec 'eligible' (bool) et 'raisons' (list des conditions non remplies)
        """
        from apps.pedagogie.models import MoyenneEtudiant
        from apps.stages.models import DemandeStage, Diplome

        raisons = []

        # 1. Niveau terminal
        filiere = etudiant.filiere
        if not filiere or filiere.niveau not in DiplomeService.NIVEAUX_TERMINAUX:
            raisons.append(f"Filière non terminale (niveau : {filiere.niveau if filiere else 'N/A'})")

        # 2. Toutes les moyennes admises
        moyennes = MoyenneEtudiant.objects.filter(etudiant=etudiant)
        if not moyennes.exists():
            raisons.append("Aucune moyenne calculée")
        elif not all(m.admis for m in moyennes):
            semestres_echec = [
                f"S{m.semestre} ({m.moyenne}/20)"
                for m in moyennes if not m.admis
            ]
            raisons.append(f"Semestres non validés : {', '.join(semestres_echec)}")

        # 3. Stage PFE terminé avec note >= 10
        stage_pfe = DemandeStage.objects.filter(
            etudiant=etudiant,
            type_stage='pfe',
            statut='termine',
            note_stage__gte=10,
        ).first()
        if not stage_pfe:
            raisons.append("Pas de stage PFE terminé avec note ≥ 10")

        # 4. Pas déjà diplômé
        if Diplome.objects.filter(etudiant=etudiant).exists():
            raisons.append("Diplôme déjà délivré")

        return {
            'eligible': len(raisons) == 0,
            'raisons': raisons,
            'stage_pfe': stage_pfe,
        }

    @staticmethod
    @transaction.atomic
    def generer(etudiant, generated_by) -> 'Diplome':
        """
        Génère le diplôme après vérification des conditions.

        Raises:
            ValidationError si l'étudiant n'est pas éligible.
        """
        from apps.stages.models import Diplome
        from apps.pedagogie.models import MoyenneEtudiant
        from apps.administration.services import AuditLogService
        from django.utils import timezone

        check = DiplomeService.verifier_eligibilite(etudiant)
        if not check['eligible']:
            raise ValidationError(
                "Conditions non remplies : " + " | ".join(check['raisons'])
            )

        moyennes = MoyenneEtudiant.objects.filter(etudiant=etudiant)
        moy_gen = round(sum(m.moyenne for m in moyennes) / moyennes.count(), 2)
        mention = MoyenneEtudiant.calculer_mention(moy_gen)

        num = (
            f"FSB-{etudiant.filiere.code}-"
            f"{timezone.now().year}-"
            f"{etudiant.numero_etudiant}"
        )

        diplome = Diplome.objects.create(
            etudiant         = etudiant,
            type_diplome     = etudiant.filiere.get_type_formation_display(),
            specialite       = etudiant.filiere.nom,
            annee_obtention  = timezone.now().year,
            mention          = mention,
            moyenne_generale = moy_gen,
            numero_diplome   = num,
            date_delivrance  = timezone.now().date(),
        )

        etudiant.statut = 'diplome'
        etudiant.save(update_fields=['statut'])

        AuditLogService.log(
            user=generated_by,
            action='CREATE',
            model='Diplome',
            object_id=diplome.pk,
            details=(
                f"Diplôme {diplome.type_diplome} généré pour "
                f"{etudiant.get_full_name()} — N° {num} — Mention {mention}"
            )
        )
        return diplome


# ══════════════════════════════════════════════════════════════════
# EXAMENS
# ══════════════════════════════════════════════════════════════════

class PlanningExamenService:
    """Gestion des plannings d'examens avec détection de conflits."""

    @staticmethod
    @transaction.atomic
    def ajouter(session, matiere, date, heure_debut, heure_fin,
                salle=None, classe=None, added_by=None) -> 'PlanningExamen':
        from apps.examens.models import PlanningExamen
        from apps.administration.services import AuditLogService

        # Vérifier conflit de salle
        if salle:
            conflit = PlanningExamen.objects.filter(
                salle=salle,
                date=date,
                heure_debut__lt=heure_fin,
                heure_fin__gt=heure_debut,
            )
            if conflit.exists():
                ex = conflit.first()
                raise ValidationError(
                    f"Conflit : salle {salle.nom} déjà occupée le {date} "
                    f"de {ex.heure_debut.strftime('%H:%M')} à "
                    f"{ex.heure_fin.strftime('%H:%M')} pour «{ex.matiere.nom}»"
                )

        # Vérifier conflit de classe
        if classe:
            conflit = PlanningExamen.objects.filter(
                classe=classe,
                date=date,
                heure_debut__lt=heure_fin,
                heure_fin__gt=heure_debut,
            )
            if conflit.exists():
                ex = conflit.first()
                raise ValidationError(
                    f"Conflit : la classe {classe.nom} a déjà un examen le {date} "
                    f"pour «{ex.matiere.nom}»"
                )

        planning = PlanningExamen.objects.create(
            session=session,
            matiere=matiere,
            date=date,
            heure_debut=heure_debut,
            heure_fin=heure_fin,
            salle=salle,
            classe=classe,
        )

        if added_by:
            AuditLogService.log(
                user=added_by,
                action='CREATE',
                model='PlanningExamen',
                object_id=planning.pk,
                details=(
                    f"Examen {matiere.nom} planifié le {date} "
                    f"de {heure_debut} à {heure_fin}"
                    + (f" en {salle.nom}" if salle else "")
                )
            )

        return planning
