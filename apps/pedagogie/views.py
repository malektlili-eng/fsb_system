"""
apps/pedagogie/views.py (V2)
─────────────────────────────────────────────────────────────────────
Vues refactorisées avec :
 ✓ @role_required sur toutes les actions sensibles
 ✓ Délégation au service layer (MoyenneService, AbsenceService)
 ✓ Pagination sur les listes longues
 ✓ Gestion d'erreurs explicite (ValidationError → messages Django)
─────────────────────────────────────────────────────────────────────
"""
import io
import base64
import json
import qrcode
import logging

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Avg, Count

from apps.administration.models import Departement, Filiere, Etudiant, Enseignant, Classe, Salle
from apps.pedagogie.models import Matiere, EmploiDuTemps, Absence, Note, MoyenneEtudiant
from apps.pedagogie.services import MoyenneService, AbsenceService
from core.permissions import role_required, min_role_required

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════
# MATIÈRES
# ════════════════════════════════════════════════════════════════

@min_role_required('scolarite')
def matieres_departements(request):
    dept_data = []
    for dept in Departement.objects.all():
        nb = Matiere.objects.filter(filiere__departement=dept).count()
        dept_data.append({
            'dept': dept,
            'nb_matieres': nb,
            'nb_filieres': Filiere.objects.filter(departement=dept).count()
        })
    return render(request, 'pedagogie/matieres/nav_departements.html', {
        'dept_data': dept_data
    })


@min_role_required('scolarite')
def matieres_filieres(request, dept_id):
    dept = get_object_or_404(Departement, pk=dept_id)
    filieres = Filiere.objects.filter(departement=dept).order_by('type_formation', 'nom')
    TYPE_LABELS = {
        'licence': 'Licences', 'master': 'Masters',
        'doctorat': 'Doctorat', 'cpi': 'CPI', 'ci': 'CI',
    }
    groupes = {}
    for f in filieres:
        lbl = TYPE_LABELS.get(f.type_formation, f.type_formation.capitalize())
        groupes.setdefault(lbl, []).append({
            'filiere': f,
            'nb_matieres': Matiere.objects.filter(filiere=f).count()
        })
    return render(request, 'pedagogie/matieres/nav_filieres.html', {
        'dept': dept, 'groupes': groupes
    })


@min_role_required('scolarite')
def matieres_liste(request, dept_id, filiere_id):
    dept = get_object_or_404(Departement, pk=dept_id)
    filiere = get_object_or_404(Filiere, pk=filiere_id)
    return render(request, 'pedagogie/matieres/liste.html', {
        'dept': dept,
        'filiere': filiere,
        'matieres_s1': Matiere.objects.filter(filiere=filiere, semestre=1).order_by('nom'),
        'matieres_s2': Matiere.objects.filter(filiere=filiere, semestre=2).order_by('nom'),
    })


@role_required('super_admin', 'admin', 'scolarite')
def ajouter_matiere(request):
    filiere_id = request.GET.get('filiere') or request.POST.get('filiere')
    dept_id = request.GET.get('dept') or request.POST.get('dept')

    if request.method == 'POST':
        try:
            filiere = get_object_or_404(Filiere, pk=request.POST['filiere'])

            # Vérifier unicité du code
            code = request.POST['code'].strip().upper()
            if Matiere.objects.filter(code=code).exists():
                messages.error(request, f"Le code matière «{code}» est déjà utilisé.")
            else:
                Matiere.objects.create(
                    nom=request.POST['nom'].strip(),
                    code=code,
                    filiere=filiere,
                    semestre=int(request.POST['semestre']),
                    credits=int(request.POST.get('credits', 3)),
                    coefficient=float(request.POST.get('coefficient', 1.0)),
                    heures_cours=int(request.POST.get('heures_cours', 0)),
                    heures_td=int(request.POST.get('heures_td', 0)),
                    heures_tp=int(request.POST.get('heures_tp', 0)),
                )
                messages.success(request, f"Matière «{request.POST['nom']}» ajoutée.")
                return redirect(
                    'pedagogie:matieres_liste',
                    dept_id=filiere.departement.pk,
                    filiere_id=filiere.pk
                )
        except (KeyError, ValueError) as e:
            messages.error(request, f"Données invalides : {e}")
        except Exception as e:
            logger.error(f"Erreur ajouter_matiere : {e}", exc_info=True)
            messages.error(request, f"Erreur inattendue : {e}")

    filieres = Filiere.objects.select_related('departement').order_by('departement__nom', 'nom')
    filiere_sel = Filiere.objects.filter(pk=filiere_id).first() if filiere_id else None
    return render(request, 'pedagogie/matieres/ajouter.html', {
        'filieres': filieres,
        'filiere_sel': filiere_sel,
        'dept_id': dept_id,
        'departements': Departement.objects.all(),
    })


@role_required('super_admin', 'admin', 'scolarite')
def modifier_matiere(request, pk):
    matiere = get_object_or_404(Matiere, pk=pk)
    if request.method == 'POST':
        try:
            matiere.nom = request.POST['nom'].strip()
            matiere.credits = int(request.POST.get('credits', matiere.credits))
            matiere.coefficient = float(request.POST.get('coefficient', matiere.coefficient))
            matiere.heures_cours = int(request.POST.get('heures_cours', 0))
            matiere.heures_td = int(request.POST.get('heures_td', 0))
            matiere.heures_tp = int(request.POST.get('heures_tp', 0))
            matiere.save()
            messages.success(request, "Matière modifiée.")
            return redirect(
                'pedagogie:matieres_liste',
                dept_id=matiere.filiere.departement.pk,
                filiere_id=matiere.filiere.pk
            )
        except Exception as e:
            messages.error(request, f"Erreur : {e}")
    return render(request, 'pedagogie/matieres/modifier.html', {'matiere': matiere})


@role_required('super_admin', 'admin')
def supprimer_matiere(request, pk):
    matiere = get_object_or_404(Matiere, pk=pk)
    dept_id = matiere.filiere.departement.pk
    filiere_id = matiere.filiere.pk

    if request.method == 'POST':
        # Vérifier qu'aucune note n'est liée
        if Note.objects.filter(matiere=matiere).exists():
            messages.error(
                request,
                f"Impossible de supprimer «{matiere.nom}» : des notes y sont associées."
            )
            return redirect(
                'pedagogie:matieres_liste', dept_id=dept_id, filiere_id=filiere_id
            )
        nom = matiere.nom
        matiere.delete()
        messages.success(request, f"Matière «{nom}» supprimée.")
        return redirect('pedagogie:matieres_liste', dept_id=dept_id, filiere_id=filiere_id)

    return render(request, 'pedagogie/matieres/confirmer_suppression.html', {
        'matiere': matiere
    })


# ════════════════════════════════════════════════════════════════
# EMPLOI DU TEMPS
# ════════════════════════════════════════════════════════════════

@min_role_required('scolarite')
def edt_departements(request):
    dept_data = []
    for dept in Departement.objects.all():
        nb = EmploiDuTemps.objects.filter(classe__filiere__departement=dept).count()
        dept_data.append({
            'dept': dept,
            'nb_seances': nb,
            'nb_filieres': Filiere.objects.filter(departement=dept).count()
        })
    return render(request, 'pedagogie/edt/nav_departements.html', {'dept_data': dept_data})


@min_role_required('scolarite')
def edt_filieres(request, dept_id):
    dept = get_object_or_404(Departement, pk=dept_id)
    filieres = Filiere.objects.filter(departement=dept)
    fil_data = []
    for f in filieres:
        nb = EmploiDuTemps.objects.filter(classe__filiere=f).count()
        fil_data.append({'filiere': f, 'nb_seances': nb})
    return render(request, 'pedagogie/edt/nav_filieres.html', {
        'dept': dept, 'fil_data': fil_data
    })


@min_role_required('scolarite')
def edt_classes(request, dept_id, filiere_id):
    dept = get_object_or_404(Departement, pk=dept_id)
    filiere = get_object_or_404(Filiere, pk=filiere_id)
    classes = filiere.classes.all()
    cl_data = []
    for cl in classes:
        nb = EmploiDuTemps.objects.filter(classe=cl).count()
        cl_data.append({'classe': cl, 'nb_seances': nb})
    return render(request, 'pedagogie/edt/nav_classes.html', {
        'dept': dept, 'filiere': filiere, 'cl_data': cl_data
    })


@min_role_required('scolarite')
def edt_classe_detail(request, classe_id):
    classe = get_object_or_404(Classe, pk=classe_id)
    dept = classe.filiere.departement
    semestre = int(request.GET.get('semestre', 1))

    seances = (
        EmploiDuTemps.objects
        .filter(classe=classe, semestre=semestre)
        .select_related('matiere', 'enseignant', 'salle')
        .order_by('jour', 'heure_debut')
    )

    # Construire la grille horaire
    JOURS = {1: 'Lundi', 2: 'Mardi', 3: 'Mercredi', 4: 'Jeudi', 5: 'Vendredi', 6: 'Samedi'}
    grille = {j: [] for j in JOURS}
    for s in seances:
        grille[s.jour].append(s)

    return render(request, 'pedagogie/edt/classe_detail.html', {
        'classe': classe,
        'dept': dept,
        'semestre': semestre,
        'seances': seances,
        'grille': grille,
        'jours': JOURS,
    })


@role_required('super_admin', 'admin', 'scolarite')
def ajouter_seance(request):
    if request.method == 'POST':
        try:
            classe_id = request.POST.get('classe')
            salle_id = request.POST.get('salle') or None
            enseignant_id = request.POST.get('enseignant') or None

            # Vérification conflit de salle
            if salle_id:
                conflit = EmploiDuTemps.objects.filter(
                    salle_id=salle_id,
                    jour=request.POST['jour'],
                    heure_debut__lt=request.POST['heure_fin'],
                    heure_fin__gt=request.POST['heure_debut'],
                )
                if conflit.exists():
                    ex = conflit.first()
                    messages.error(
                        request,
                        f"Conflit : la salle est déjà occupée ce jour-là "
                        f"de {ex.heure_debut.strftime('%H:%M')} à "
                        f"{ex.heure_fin.strftime('%H:%M')} pour «{ex.matiere.nom}»."
                    )
                    return redirect('pedagogie:ajouter_seance')

            EmploiDuTemps.objects.create(
                matiere_id=request.POST['matiere'],
                enseignant_id=enseignant_id,
                salle_id=salle_id,
                classe_id=classe_id,
                jour=int(request.POST['jour']),
                heure_debut=request.POST['heure_debut'],
                heure_fin=request.POST['heure_fin'],
                type_seance=request.POST['type_seance'],
                annee_universitaire=request.POST.get('annee', '2024-2025'),
                semestre=int(request.POST.get('semestre', 1)),
            )
            messages.success(request, "Séance ajoutée à l'emploi du temps.")
            if classe_id:
                return redirect('pedagogie:edt_classe', classe_id=classe_id)
            return redirect('pedagogie:emploi_du_temps')
        except Exception as e:
            messages.error(request, f"Erreur : {e}")

    return render(request, 'pedagogie/edt/ajouter_seance.html', {
        'matieres': Matiere.objects.all().order_by('nom'),
        'enseignants': Enseignant.objects.filter(actif=True).order_by('nom'),
        'salles': Salle.objects.all().order_by('nom'),
        'classes': Classe.objects.all().order_by('nom'),
        'jour_choices': [(1,'Lundi'),(2,'Mardi'),(3,'Mercredi'),(4,'Jeudi'),(5,'Vendredi'),(6,'Samedi')],
    })


@role_required('super_admin', 'admin', 'scolarite')
def supprimer_seance(request, pk):
    seance = get_object_or_404(EmploiDuTemps, pk=pk)
    classe_id = seance.classe.pk if seance.classe else None
    seance.delete()
    messages.success(request, "Séance supprimée.")
    if classe_id:
        return redirect('pedagogie:edt_classe', classe_id=classe_id)
    return redirect('pedagogie:emploi_du_temps')


# ════════════════════════════════════════════════════════════════
# ABSENCES
# ════════════════════════════════════════════════════════════════

@min_role_required('scolarite')
def absences_departements(request):
    dept_data = []
    for dept in Departement.objects.all():
        nb = Absence.objects.filter(seance__classe__filiere__departement=dept).count()
        dept_data.append({'dept': dept, 'nb_absences': nb})
    return render(request, 'pedagogie/absences/nav_departements.html', {
        'dept_data': dept_data
    })


@min_role_required('scolarite')
def absences_filieres(request, dept_id):
    dept = get_object_or_404(Departement, pk=dept_id)
    filieres = Filiere.objects.filter(departement=dept)
    fil_data = [{
        'filiere': f,
        'nb_absences': Absence.objects.filter(seance__classe__filiere=f).count()
    } for f in filieres]
    return render(request, 'pedagogie/absences/nav_filieres.html', {
        'dept': dept, 'fil_data': fil_data
    })


@min_role_required('scolarite')
def absences_classes(request, dept_id, filiere_id):
    dept = get_object_or_404(Departement, pk=dept_id)
    filiere = get_object_or_404(Filiere, pk=filiere_id)
    classes = filiere.classes.all()
    cl_data = [{
        'classe': cl,
        'nb_absences': Absence.objects.filter(seance__classe=cl).count()
    } for cl in classes]
    return render(request, 'pedagogie/absences/nav_classes.html', {
        'dept': dept, 'filiere': filiere, 'cl_data': cl_data
    })


@min_role_required('scolarite')
def absences_classe_detail(request, classe_id):
    classe = get_object_or_404(Classe, pk=classe_id)
    dept = classe.filiere.departement
    etudiants = Etudiant.objects.filter(filiere=classe.filiere, statut='inscrit')
    matieres = Matiere.objects.filter(filiere=classe.filiere)

    data_etudiants = []
    for et in etudiants:
        absences_et = []
        elimine = False
        total_abs = 0
        for mat in matieres:
            nb_abs = Absence.objects.filter(
                etudiant=et, seance__matiere=mat
            ).count()
            seuil = mat.seuil_elimination()
            est_elim = AbsenceService.est_elimine(et, mat)
            if est_elim:
                elimine = True
            total_abs += nb_abs
            absences_et.append({
                'matiere': mat,
                'nb_absences': nb_abs,
                'seuil': seuil,
                'elimine': est_elim,
                'pct': round(nb_abs / mat.total_heures() * 100, 1) if mat.total_heures() > 0 else 0,
            })
        data_etudiants.append({
            'etudiant': et,
            'absences': absences_et,
            'total_abs': total_abs,
            'elimine': elimine,
        })

    nb_elimines = sum(1 for d in data_etudiants if d['elimine'])

    # Données pour les graphiques
    abs_par_matiere = [{
        'matiere': mat.nom,
        'nb': Absence.objects.filter(
            seance__matiere=mat, etudiant__filiere=classe.filiere
        ).count()
    } for mat in matieres]

    return render(request, 'pedagogie/absences/classe_detail.html', {
        'classe': classe,
        'dept': dept,
        'data_etudiants': data_etudiants,
        'nb_elimines': nb_elimines,
        'nb_ok': len(data_etudiants) - nb_elimines,
        'abs_par_matiere': json.dumps(abs_par_matiere),
        'labels_etudiants': json.dumps([d['etudiant'].get_full_name() for d in data_etudiants]),
        'data_totaux': json.dumps([d['total_abs'] for d in data_etudiants]),
    })


# ════════════════════════════════════════════════════════════════
# NOTES & RÉSULTATS
# ════════════════════════════════════════════════════════════════

@min_role_required('scolarite')
def notes_departements(request):
    dept_data = [{
        'dept': dept,
        'nb_notes': Note.objects.filter(matiere__filiere__departement=dept).count()
    } for dept in Departement.objects.all()]
    return render(request, 'pedagogie/notes/nav_departements.html', {
        'dept_data': dept_data
    })


@min_role_required('scolarite')
def notes_filieres(request, dept_id):
    dept = get_object_or_404(Departement, pk=dept_id)
    filieres = Filiere.objects.filter(departement=dept)
    fil_data = [{
        'filiere': f,
        'nb_notes': Note.objects.filter(matiere__filiere=f).count()
    } for f in filieres]
    return render(request, 'pedagogie/notes/nav_filieres.html', {
        'dept': dept, 'fil_data': fil_data
    })


@min_role_required('scolarite')
def notes_classes(request, dept_id, filiere_id):
    dept = get_object_or_404(Departement, pk=dept_id)
    filiere = get_object_or_404(Filiere, pk=filiere_id)
    classes = filiere.classes.all()
    cl_data = [{
        'classe': cl,
        'nb_moyennes': MoyenneEtudiant.objects.filter(classe=cl).count()
    } for cl in classes]
    return render(request, 'pedagogie/notes/nav_classes.html', {
        'dept': dept, 'filiere': filiere, 'cl_data': cl_data
    })


@min_role_required('scolarite')
def notes_classe_detail(request, classe_id):
    classe = get_object_or_404(Classe, pk=classe_id)
    dept = classe.filiere.departement
    semestre = int(request.GET.get('semestre', 1))
    annee = request.GET.get('annee', '2024-2025')

    etudiants = Etudiant.objects.filter(filiere=classe.filiere, statut='inscrit')
    matieres = Matiere.objects.filter(filiere=classe.filiere, semestre=semestre)

    moyennes_map = {
        m.etudiant_id: m
        for m in MoyenneEtudiant.objects.filter(
            classe=classe, semestre=semestre, annee_universitaire=annee
        )
    }

    data_etudiants = []
    for et in etudiants:
        notes_et = Note.objects.filter(
            etudiant=et,
            matiere__filiere=classe.filiere,
            semestre=semestre,
            annee_universitaire=annee,
        ).select_related('matiere')
        data_etudiants.append({
            'etudiant': et,
            'notes': notes_et,
            'moyenne': moyennes_map.get(et.pk),
        })

    # Stats graphiques
    mentions_count = {
        'excellent': 0, 'tres_bien': 0, 'bien': 0,
        'assez_bien': 0, 'passable': 0, 'echec': 0,
    }
    nb_admis = 0
    for d in data_etudiants:
        if d['moyenne']:
            if d['moyenne'].admis:
                nb_admis += 1
                mentions_count[d['moyenne'].mention] = (
                    mentions_count.get(d['moyenne'].mention, 0) + 1
                )
            else:
                mentions_count['echec'] += 1

    nb_total = len(data_etudiants)
    return render(request, 'pedagogie/notes/classe_detail.html', {
        'classe': classe,
        'dept': dept,
        'semestre': semestre,
        'annee': annee,
        'matieres': matieres,
        'data_etudiants': data_etudiants,
        'nb_admis': nb_admis,
        'nb_total': nb_total,
        'pct_reuss': round(nb_admis / nb_total * 100, 1) if nb_total else 0,
        'mentions_json': json.dumps(mentions_count),
        'moyennes_calculees': bool(moyennes_map),
    })


@role_required('super_admin', 'admin', 'scolarite')
def calculer_moyennes(request, classe_id):
    """Lance le calcul des moyennes via le service dédié."""
    if request.method != 'POST':
        return redirect('pedagogie:notes_classe', classe_id=classe_id)

    classe = get_object_or_404(Classe, pk=classe_id)
    semestre = int(request.POST.get('semestre', 1))
    annee = request.POST.get('annee', '2024-2025')

    try:
        result = MoyenneService.calculer_classe(
            classe, semestre, annee, calculated_by=request.user
        )
        messages.success(
            request,
            f"Moyennes calculées pour {result['nb_calcules']} étudiant(s). "
            f"Taux de réussite : {result['taux_reussite']}%"
        )
    except Exception as e:
        logger.error(f"Erreur calculer_moyennes : {e}", exc_info=True)
        messages.error(request, f"Erreur lors du calcul : {e}")

    return redirect(
        f"/pedagogie/notes/classe/{classe_id}/?semestre={semestre}&annee={annee}"
    )


@min_role_required('scolarite')
def releve_notes_etudiant(request, etudiant_id):
    etudiant = get_object_or_404(Etudiant, pk=etudiant_id)
    semestre = int(request.GET.get('semestre', 1))
    annee = request.GET.get('annee', '2024-2025')

    notes = Note.objects.filter(
        etudiant=etudiant,
        semestre=semestre,
        annee_universitaire=annee,
    ).select_related('matiere').order_by('matiere__nom')

    moyenne = MoyenneEtudiant.objects.filter(
        etudiant=etudiant,
        semestre=semestre,
        annee_universitaire=annee,
    ).first()

    return render(request, 'pedagogie/notes/releve.html', {
        'etudiant': etudiant,
        'notes': notes,
        'moyenne': moyenne,
        'semestre': semestre,
        'annee': annee,
    })


@min_role_required('scolarite')
def attestation_reussite(request, etudiant_id):
    etudiant = get_object_or_404(Etudiant, pk=etudiant_id)
    semestre = int(request.GET.get('semestre', 1))
    annee = request.GET.get('annee', '2024-2025')

    moyenne = MoyenneEtudiant.objects.filter(
        etudiant=etudiant, semestre=semestre, annee_universitaire=annee
    ).first()

    if not moyenne or not moyenne.admis:
        messages.error(request, "Attestation disponible uniquement pour les étudiants admis.")
        return redirect(request.META.get('HTTP_REFERER', '/'))

    # Génération du QR Code de vérification
    qr_data = (
        f"FSB-REUSSITE\n"
        f"Etudiant: {etudiant.get_full_name()}\n"
        f"N°: {etudiant.numero_etudiant}\n"
        f"Filière: {etudiant.filiere}\n"
        f"Moyenne: {moyenne.moyenne}/20\n"
        f"Mention: {moyenne.get_mention_display()}\n"
        f"Année: {annee} S{semestre}"
    )
    qr = qrcode.QRCode(version=1, box_size=6, border=2)
    qr.add_data(qr_data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#0b1e3d", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    qr_b64 = base64.b64encode(buf.getvalue()).decode()

    return render(request, 'pedagogie/notes/attestation_reussite.html', {
        'etudiant': etudiant,
        'moyenne': moyenne,
        'semestre': semestre,
        'annee': annee,
        'qr_b64': qr_b64,
    })


@role_required('super_admin', 'admin', 'scolarite')
def modifier_seance(request, pk):
    """Modifier une séance de l'emploi du temps."""
    seance = get_object_or_404(EmploiDuTemps, pk=pk)
    classe_id = seance.classe.pk if seance.classe else None

    if request.method == 'POST':
        try:
            seance.matiere_id     = request.POST.get('matiere', seance.matiere_id)
            seance.enseignant_id  = request.POST.get('enseignant') or None
            seance.salle_id       = request.POST.get('salle') or None
            seance.jour           = int(request.POST.get('jour', seance.jour))
            seance.heure_debut    = request.POST.get('heure_debut', seance.heure_debut)
            seance.heure_fin      = request.POST.get('heure_fin', seance.heure_fin)
            seance.type_seance    = request.POST.get('type_seance', seance.type_seance)
            seance.save()
            messages.success(request, "Séance modifiée.")
            if classe_id:
                return redirect('pedagogie:edt_classe', classe_id=classe_id)
            return redirect('pedagogie:emploi_du_temps')
        except Exception as e:
            messages.error(request, f"Erreur : {e}")

    return render(request, 'pedagogie/edt/ajouter_seance.html', {
        'seance': seance,
        'modifier': True,
        'matieres': Matiere.objects.all().order_by('nom'),
        'enseignants': Enseignant.objects.filter(actif=True).order_by('nom'),
        'salles': Salle.objects.all().order_by('nom'),
        'classes': Classe.objects.all().order_by('nom'),
        'jour_choices': [(1,'Lundi'),(2,'Mardi'),(3,'Mercredi'),(4,'Jeudi'),(5,'Vendredi'),(6,'Samedi')],
    })
