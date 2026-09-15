"""
apps/stages/views.py (V2)
apps/examens/views.py (V2)
─────────────────────────────────────────────────────────────────────
Vues refactorisées avec RBAC, services et gestion d'erreurs propre.
─────────────────────────────────────────────────────────────────────
"""

# ══════════════════════════════════════════════════════════════════
# STAGES & DIPLÔMES
# ══════════════════════════════════════════════════════════════════

import io
import base64
import logging
import qrcode

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.stages.models import DemandeStage, Diplome
from apps.administration.models import Etudiant, Enseignant
from apps.pedagogie.models import MoyenneEtudiant
from apps.pedagogie.services import DiplomeService, StageService
from core.permissions import role_required, min_role_required

logger = logging.getLogger(__name__)


def _generer_qr(data: str) -> str:
    """Génère un QR code en base64."""
    qr = qrcode.QRCode(version=1, box_size=6, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#0b1e3d", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return base64.b64encode(buf.getvalue()).decode()


# ─── Demandes de stage ────────────────────────────────────────────

@min_role_required('scolarite')
def liste_demandes(request):
    statut = request.GET.get('statut', '')
    query = request.GET.get('q', '')

    qs = DemandeStage.objects.select_related(
        'etudiant', 'encadrant_fsb'
    ).order_by('-date_demande')

    if statut:
        qs = qs.filter(statut=statut)
    if query:
        qs = (
            qs.filter(etudiant__nom__icontains=query)
            | qs.filter(etudiant__prenom__icontains=query)
            | qs.filter(etudiant__numero_etudiant__icontains=query)
            | qs.filter(sujet__icontains=query)
        )

    stats = {s: DemandeStage.objects.filter(statut=s).count()
             for s, _ in DemandeStage.STATUT_CHOICES}

    return render(request, 'stages/liste.html', {
        'demandes': qs,
        'statut': statut,
        'query': query,
        'stats': stats,
    })


@min_role_required('scolarite')
def detail_demande(request, pk):
    demande = get_object_or_404(DemandeStage, pk=pk)

    if request.method == 'POST':
        action = request.POST.get('action')
        commentaire = request.POST.get('commentaire', '').strip()

        try:
            if action == 'valider':
                encadrant_id = request.POST.get('encadrant') or None
                StageService.valider(demande, encadrant_id, commentaire, request.user)
                messages.success(request, "Demande de stage validée.")

            elif action == 'refuser':
                StageService.refuser(demande, commentaire, request.user)
                messages.success(request, "Demande de stage refusée.")

            elif action == 'en_cours':
                StageService.changer_statut(demande, 'en_cours', request.user)
                messages.success(request, "Stage marqué en cours.")

            elif action == 'terminer':
                note_str = request.POST.get('note_stage', '').strip()
                if not note_str:
                    raise ValidationError("La note du stage est requise pour le terminer.")
                StageService.terminer(demande, float(note_str), request.user)
                messages.success(request, "Stage terminé et noté.")

            else:
                messages.warning(request, f"Action «{action}» inconnue.")

        except ValidationError as e:
            messages.error(request, str(e))
        except Exception as e:
            logger.error(f"Erreur detail_demande : {e}", exc_info=True)
            messages.error(request, f"Erreur : {e}")

        return redirect('stages:detail_demande', pk=pk)

    transitions = StageService.TRANSITIONS_AUTORISEES.get(demande.statut, [])
    return render(request, 'stages/detail.html', {
        'demande': demande,
        'enseignants': Enseignant.objects.filter(actif=True).order_by('nom'),
        'transitions': transitions,
    })


@min_role_required('scolarite')
def attestation_stage(request, pk):
    demande = get_object_or_404(DemandeStage, pk=pk)

    if demande.statut not in ['valide', 'en_cours', 'termine']:
        messages.error(request, "Attestation disponible uniquement pour les stages validés.")
        return redirect('stages:detail_demande', pk=pk)

    qr_data = (
        f"FSB-STAGE\n"
        f"Etudiant: {demande.etudiant.get_full_name()}\n"
        f"N°: {demande.etudiant.numero_etudiant}\n"
        f"Sujet: {demande.sujet}\n"
        f"Entreprise: {demande.entreprise}\n"
        f"Période: {demande.date_debut} – {demande.date_fin}\n"
        f"Type: {demande.get_type_stage_display()}"
    )
    return render(request, 'stages/attestation_stage.html', {
        'demande': demande,
        'qr_b64': _generer_qr(qr_data),
    })


# ─── Diplômes ─────────────────────────────────────────────────────

@min_role_required('scolarite')
def liste_diplomes(request):
    diplomes = Diplome.objects.select_related('etudiant').order_by('-annee_obtention')
    return render(request, 'stages/diplomes.html', {'diplomes': diplomes})


@min_role_required('scolarite')
def etudiants_eligibles_diplome(request):
    """Liste les étudiants éligibles au diplôme selon DiplomeService."""
    NIVEAUX_TERMINAUX = DiplomeService.NIVEAUX_TERMINAUX
    filieres_terminales = __import__(
        'apps.administration.models', fromlist=['Filiere']
    ).Filiere.objects.filter(niveau__in=NIVEAUX_TERMINAUX)

    etudiants_data = []
    for filiere in filieres_terminales:
        etudiants = Etudiant.objects.filter(filiere=filiere, statut='inscrit')
        for et in etudiants:
            check = DiplomeService.verifier_eligibilite(et)
            deja_diplome = Diplome.objects.filter(etudiant=et).exists()
            moyennes = MoyenneEtudiant.objects.filter(etudiant=et)
            etudiants_data.append({
                'etudiant': et,
                'filiere': filiere,
                'eligible': check['eligible'],
                'raisons': check['raisons'],
                'stage_pfe': check['stage_pfe'],
                'deja_diplome': deja_diplome,
                'moyennes': moyennes,
            })

    filtre = request.GET.get('filtre', 'tous')
    if filtre == 'eligible':
        etudiants_data = [d for d in etudiants_data if d['eligible'] and not d['deja_diplome']]
    elif filtre == 'non_eligible':
        etudiants_data = [d for d in etudiants_data if not d['eligible']]

    return render(request, 'stages/eligibles_diplome.html', {
        'etudiants_data': etudiants_data,
        'filtre': filtre,
        'nb_eligibles': sum(1 for d in etudiants_data if d['eligible'] and not d['deja_diplome']),
    })


@role_required('super_admin', 'admin', 'chef_dept', 'doyen')
def generer_diplome(request, etudiant_id):
    etudiant = get_object_or_404(Etudiant, pk=etudiant_id)

    check = DiplomeService.verifier_eligibilite(etudiant)
    if not check['eligible'] and request.method == 'GET':
        messages.error(
            request,
            "Conditions non remplies : " + " | ".join(check['raisons'])
        )
        return redirect('stages:eligibles_diplome')

    if request.method == 'POST':
        try:
            diplome = DiplomeService.generer(etudiant, generated_by=request.user)
            messages.success(request, f"Diplôme généré pour {etudiant.get_full_name()}.")
            return redirect('stages:diplome_officiel', pk=diplome.pk)
        except ValidationError as e:
            messages.error(request, str(e))
        except Exception as e:
            logger.error(f"Erreur generer_diplome : {e}", exc_info=True)
            messages.error(request, f"Erreur : {e}")

    moyennes = MoyenneEtudiant.objects.filter(etudiant=etudiant)
    return render(request, 'stages/confirmer_diplome.html', {
        'etudiant': etudiant,
        'moyennes': moyennes,
        'stage_pfe': check['stage_pfe'],
        'check': check,
    })


@role_required('super_admin', 'admin', 'scolarite')
def ajouter_diplome(request):
    """Ajout manuel d'un diplôme (sans passer par le workflow automatique)."""
    if request.method == 'POST':
        try:
            etudiant_id = request.POST['etudiant']
            type_diplome = request.POST['type_diplome']
            etudiant = get_object_or_404(Etudiant, pk=etudiant_id)

            if Diplome.objects.filter(etudiant=etudiant, type_diplome=type_diplome).exists():
                messages.warning(
                    request,
                    f"Un diplôme «{type_diplome}» existe déjà pour {etudiant.get_full_name()}."
                )
                return redirect('stages:ajouter_diplome')

            moyenne_raw = request.POST.get('moyenne', '').strip()
            diplome = Diplome.objects.create(
                etudiant=etudiant,
                type_diplome=type_diplome,
                specialite=request.POST['specialite'],
                annee_obtention=int(request.POST['annee_obtention']),
                mention=request.POST.get('mention', ''),
                moyenne_generale=float(moyenne_raw) if moyenne_raw else None,
                numero_diplome=request.POST['numero_diplome'],
                date_delivrance=request.POST.get('date_delivrance') or None,
            )
            etudiant.statut = 'diplome'
            etudiant.save(update_fields=['statut'])

            messages.success(
                request,
                f"Diplôme enregistré pour {etudiant.get_full_name()} — N° {diplome.numero_diplome}"
            )
            return redirect('stages:diplome_officiel', pk=diplome.pk)

        except KeyError as e:
            messages.error(request, f"Champ manquant : {e}")
        except ValueError as e:
            messages.error(request, f"Valeur invalide : {e}")
        except Exception as e:
            messages.error(request, f"Erreur : {e}")

    annees = list(range(timezone.now().year, timezone.now().year - 10, -1))
    return render(request, 'stages/ajouter_diplome.html', {
        'etudiants': Etudiant.objects.filter(
            statut__in=['inscrit', 'diplome']
        ).select_related('filiere').order_by('nom', 'prenom'),
        'annees': annees,
        'today': timezone.now().date().isoformat(),
    })


@min_role_required('scolarite')
def diplome_officiel(request, pk):
    diplome = get_object_or_404(Diplome, pk=pk)
    etudiant = diplome.etudiant

    qr_data = (
        f"FSB-DIPLOME\n"
        f"N°: {diplome.numero_diplome}\n"
        f"Etudiant: {etudiant.get_full_name()}\n"
        f"Matricule: {etudiant.numero_etudiant}\n"
        f"Diplôme: {diplome.type_diplome}\n"
        f"Spécialité: {diplome.specialite}\n"
        f"Mention: {diplome.get_mention_display() if diplome.mention else 'N/A'}\n"
        f"Moyenne: {diplome.moyenne_generale}/20\n"
        f"Année: {diplome.annee_obtention}\n"
        f"Délivré le: {diplome.date_delivrance}"
    )
    return render(request, 'stages/diplome_officiel.html', {
        'diplome': diplome,
        'qr_b64': _generer_qr(qr_data),
    })
