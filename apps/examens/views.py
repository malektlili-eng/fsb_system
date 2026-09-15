"""
apps/examens/views.py (V2)
"""
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.exceptions import ValidationError

from apps.examens.models import SessionExamen, PlanningExamen, ResultatExamen
from apps.administration.models import Salle, Classe
from apps.pedagogie.models import Matiere
from apps.pedagogie.services import PlanningExamenService
from core.permissions import role_required, min_role_required

logger = logging.getLogger(__name__)


@min_role_required('scolarite')
def liste_sessions(request):
    sessions = SessionExamen.objects.order_by('-date_debut')
    return render(request, 'examens/sessions.html', {'sessions': sessions})


@role_required('super_admin', 'admin', 'scolarite')
def ajouter_session(request):
    if request.method == 'POST':
        try:
            date_debut = request.POST['date_debut']
            date_fin = request.POST['date_fin']
            if date_fin < date_debut:
                raise ValidationError("La date de fin doit être après la date de début.")

            SessionExamen.objects.create(
                nom=request.POST['nom'].strip(),
                type_session=request.POST['type_session'],
                annee_universitaire=request.POST['annee_univ'],
                semestre=int(request.POST['semestre']),
                date_debut=date_debut,
                date_fin=date_fin,
            )
            messages.success(request, "Session d'examen créée.")
            return redirect('examens:sessions')
        except ValidationError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f"Erreur : {e}")

    return render(request, 'examens/ajouter_session.html', {
        'annees': ['2024-2025', '2025-2026', '2026-2027'],
    })


@min_role_required('scolarite')
def planning_examens(request):
    session_id = request.GET.get('session', '')
    session = None

    if session_id:
        try:
            session = SessionExamen.objects.get(pk=session_id)
        except SessionExamen.DoesNotExist:
            pass

    if request.method == 'POST':
        try:
            salle_id = request.POST.get('salle') or None
            classe_id = request.POST.get('classe') or None
            sess_id = request.POST.get('session') or request.GET.get('session', '')
            if not sess_id:
                messages.error(request, 'Veuillez sélectionner une session.')
                return redirect(request.path)

            session_obj = get_object_or_404(SessionExamen, pk=sess_id)
            matiere_obj = get_object_or_404(Matiere, pk=request.POST['matiere'])
            salle_obj = get_object_or_404(Salle, pk=salle_id) if salle_id else None
            classe_obj = get_object_or_404(Classe, pk=classe_id) if classe_id else None

            PlanningExamenService.ajouter(
                session=session_obj,
                matiere=matiere_obj,
                date=request.POST['date'],
                heure_debut=request.POST['heure_debut'],
                heure_fin=request.POST['heure_fin'],
                salle=salle_obj,
                classe=classe_obj,
                added_by=request.user,
            )
            messages.success(request, "Examen planifié avec succès.")
            return redirect(f"{request.path}?session={sess_id}")

        except ValidationError as e:
            messages.error(request, str(e))
        except Exception as e:
            logger.error(f"Erreur planning_examens : {e}", exc_info=True)
            messages.error(request, f"Erreur : {e}")

    plannings = []
    planning_par_jour = {}
    if session:
        plannings = (
            PlanningExamen.objects
            .filter(session=session)
            .select_related('matiere', 'salle', 'session', 'classe')
            .order_by('date', 'heure_debut')
        )
        for p in plannings:
            planning_par_jour.setdefault(p.date, []).append(p)

    return render(request, 'examens/planning.html', {
        'session': session,
        'sessions': SessionExamen.objects.order_by('-date_debut'),
        'matieres': Matiere.objects.all().order_by('nom'),
        'salles': Salle.objects.all().order_by('nom'),
        'classes': Classe.objects.all().order_by('nom'),
        'planning_par_jour': planning_par_jour,
        'plannings_count': len(plannings),
    })


@role_required('super_admin', 'admin', 'scolarite')
def supprimer_planning(request, pk):
    if request.method != 'POST':
        return redirect('examens:planning')
    planning = get_object_or_404(PlanningExamen, pk=pk)
    session_pk = planning.session.pk
    planning.delete()
    messages.success(request, "Examen supprimé du planning.")
    return redirect(f"/examens/planning/?session={session_pk}")


@min_role_required('scolarite')
def resultats(request):
    session_id = request.GET.get('session', '')
    qs = ResultatExamen.objects.select_related('etudiant', 'matiere', 'session')
    if session_id:
        qs = qs.filter(session_id=session_id)
    return render(request, 'examens/resultats.html', {
        'resultats': qs,
        'sessions': SessionExamen.objects.all(),
        'session_id': session_id,
    })
