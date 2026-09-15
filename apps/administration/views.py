"""
apps/administration/views.py (V2)
─────────────────────────────────────────────────────────────────────
Toutes les vues refactorisées avec :
 ✓ @role_required / @min_role_required sur chaque vue sensible
 ✓ Délégation au service layer (EtudiantService, AuditLogService)
 ✓ Formulaires Django (EtudiantForm, EnseignantForm)
 ✓ Pagination sur les listes longues
 ✓ QR codes pour attestations
─────────────────────────────────────────────────────────────────────
"""
import io
import base64
import logging
import qrcode

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.utils import timezone

from apps.administration.models import (
    Departement, Filiere, Enseignant, Etudiant,
    Salle, Inscription, Classe,
)
from apps.administration.forms import EtudiantForm, EnseignantForm, InscriptionForm
from apps.administration.services import EtudiantService, AuditLogService
from apps.pedagogie.models import Note, Absence
from apps.examens.models import SessionExamen
from core.permissions import role_required, min_role_required

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════
# DASHBOARD
# ════════════════════════════════════════════════════════════════

@min_role_required('scolarite')
def dashboard(request):
    stats = {
        'nb_etudiants':    Etudiant.objects.filter(statut='inscrit').count(),
        'nb_enseignants':  Enseignant.objects.filter(actif=True).count(),
        'nb_filieres':     Filiere.objects.count(),
        'nb_inscriptions': Inscription.objects.filter(statut='validee').count(),
    }
    formations = {
        tf: Filiere.objects.filter(type_formation=tf).count()
        for tf in ('licence', 'master', 'doctorat', 'cpi', 'ci')
    }
    sessions = SessionExamen.objects.filter(
        date_fin__gte=timezone.now().date()
    ).order_by('date_debut')[:5]

    return render(request, 'administration/dashboard.html', {
        'stats':      stats,
        'formations': formations,
        'sessions':   sessions,
    })


# ════════════════════════════════════════════════════════════════
# NAVIGATION FORMATIONS / FILIÈRES
# ════════════════════════════════════════════════════════════════

@min_role_required('scolarite')
def formation_detail(request, type_formation):
    LABELS = {
        'licence': 'Licences', 'master': 'Masters',
        'doctorat': 'Doctorats', 'cpi': 'CPI', 'ci': 'CI',
    }
    departements = Departement.objects.filter(
        filieres__type_formation=type_formation
    ).distinct()
    dept_data = []
    for dept in departements:
        filieres = Filiere.objects.filter(departement=dept, type_formation=type_formation)
        dept_data.append({
            'dept': dept,
            'filieres': filieres,
            'nb_etudiants': Etudiant.objects.filter(
                filiere__in=filieres, statut='inscrit'
            ).count(),
            'nb_enseignants': Enseignant.objects.filter(
                departement=dept, actif=True
            ).count(),
        })
    return render(request, 'administration/formation_detail.html', {
        'type_formation': type_formation,
        'label': LABELS.get(type_formation, type_formation),
        'dept_data': dept_data,
        'type_list': list(LABELS.items()),
    })


@min_role_required('scolarite')
def departement_detail(request, type_formation, dept_id):
    dept = get_object_or_404(Departement, pk=dept_id)
    filieres = Filiere.objects.filter(departement=dept, type_formation=type_formation)
    return render(request, 'administration/departement_detail.html', {
        'dept': dept,
        'type_formation': type_formation,
        'filieres': filieres,
        'nb_etudiants': Etudiant.objects.filter(
            filiere__in=filieres, statut='inscrit').count(),
        'enseignants': Enseignant.objects.filter(
            departement=dept, actif=True).order_by('grade', 'nom'),
    })


@min_role_required('scolarite')
def filiere_detail(request, type_formation, dept_id, filiere_id):
    filiere = get_object_or_404(Filiere, pk=filiere_id)
    dept = get_object_or_404(Departement, pk=dept_id)
    return render(request, 'administration/filiere_detail.html', {
        'filiere': filiere,
        'dept': dept,
        'type_formation': type_formation,
        'etudiants': Etudiant.objects.filter(
            filiere=filiere, statut='inscrit').order_by('nom'),
        'classes': filiere.classes.all().order_by('niveau'),
        'nb_enseignants': Enseignant.objects.filter(
            departement=filiere.departement, actif=True).count(),
    })


# ════════════════════════════════════════════════════════════════
# ÉTUDIANTS — Navigation à 4 niveaux
# ════════════════════════════════════════════════════════════════

@min_role_required('scolarite')
def etudiants_departements(request):
    dept_data = [{
        'dept': d,
        'nb_etudiants': Etudiant.objects.filter(
            filiere__departement=d, statut='inscrit').count()
    } for d in Departement.objects.all()]
    return render(request, 'administration/etudiants/nav_departements.html', {
        'dept_data': dept_data
    })


@min_role_required('scolarite')
def etudiants_filieres(request, dept_id):
    dept = get_object_or_404(Departement, pk=dept_id)
    TYPE_LABELS = [
        ('licence','Licences'), ('master','Masters'),
        ('doctorat','Doctorat'), ('cpi','CPI'), ('ci','CI'),
    ]
    groupes = []
    for tf, label in TYPE_LABELS:
        filieres = Filiere.objects.filter(departement=dept, type_formation=tf)
        if filieres.exists():
            groupes.append({'label': label, 'type': tf, 'filieres': [{
                'filiere': f,
                'nb_etudiants': Etudiant.objects.filter(
                    filiere=f, statut='inscrit').count(),
                'nb_classes': f.classes.count(),
            } for f in filieres]})
    return render(request, 'administration/etudiants/nav_filieres.html', {
        'dept': dept, 'groupes': groupes
    })


@min_role_required('scolarite')
def etudiants_classes(request, dept_id, filiere_id):
    dept = get_object_or_404(Departement, pk=dept_id)
    filiere = get_object_or_404(Filiere, pk=filiere_id)
    classes = filiere.classes.all().order_by('niveau', 'nom')
    if not classes.exists():
        return render(request, 'administration/etudiants/nav_classes.html', {
            'dept': dept, 'filiere': filiere, 'classes_data': [],
            'etudiants_direct': Etudiant.objects.filter(
                filiere=filiere, statut='inscrit').order_by('nom'),
        })
    return render(request, 'administration/etudiants/nav_classes.html', {
        'dept': dept, 'filiere': filiere,
        'classes_data': [{'classe': cl, 'nb_etudiants': Etudiant.objects.filter(
            filiere=filiere, statut='inscrit').count()} for cl in classes],
    })


@min_role_required('scolarite')
def etudiants_liste_classe(request, dept_id, filiere_id, classe_id):
    dept = get_object_or_404(Departement, pk=dept_id)
    filiere = get_object_or_404(Filiere, pk=filiere_id)
    classe = get_object_or_404(Classe, pk=classe_id)

    qs = Etudiant.objects.filter(
        filiere=filiere, statut='inscrit'
    ).order_by('nom', 'prenom')

    query = request.GET.get('q', '')
    if query:
        qs = qs.filter(
            Q(nom__icontains=query) | Q(prenom__icontains=query)
            | Q(numero_etudiant__icontains=query)
        )

    paginator = Paginator(qs, 30)
    page = paginator.get_page(request.GET.get('page'))

    return render(request, 'administration/etudiants/nav_liste.html', {
        'dept': dept, 'filiere': filiere, 'classe': classe,
        'etudiants': page, 'query': query,
    })


@min_role_required('scolarite')
def detail_etudiant(request, pk):
    etudiant = get_object_or_404(
        Etudiant.objects.select_related('filiere', 'filiere__departement'), pk=pk
    )
    notes = Note.objects.filter(
        etudiant=etudiant).select_related('matiere').order_by('semestre', 'matiere__nom')
    absences = Absence.objects.filter(
        etudiant=etudiant).select_related('seance__matiere').order_by('-date')[:20]
    stages = etudiant.stages.all().order_by('-date_demande')

    return render(request, 'administration/etudiants/detail.html', {
        'etudiant': etudiant,
        'notes': notes,
        'absences': absences,
        'stages': stages,
    })


@role_required('super_admin', 'admin', 'scolarite')
def ajouter_etudiant(request):
    if request.method == 'POST':
        form = EtudiantForm(request.POST)
        if form.is_valid():
            try:
                etudiant = EtudiantService.creer(
                    data=form.cleaned_data,
                    created_by=request.user,
                )
                messages.success(
                    request,
                    f"Étudiant {etudiant.get_full_name()} ajouté "
                    f"(N° {etudiant.numero_etudiant})."
                )
                return redirect('administration:detail_etudiant', pk=etudiant.pk)
            except ValidationError as e:
                messages.error(request, str(e))
            except Exception as e:
                logger.error(f"Erreur ajouter_etudiant: {e}", exc_info=True)
                messages.error(request, f"Erreur : {e}")
    else:
        form = EtudiantForm()

    return render(request, 'administration/etudiants/ajouter.html', {
        'form': form,
        'filieres': Filiere.objects.select_related('departement').order_by('departement__nom', 'nom'),
    })


@role_required('super_admin', 'admin', 'scolarite')
def modifier_etudiant(request, pk):
    etudiant = get_object_or_404(Etudiant, pk=pk)
    if request.method == 'POST':
        form = EtudiantForm(request.POST, instance=etudiant)
        if form.is_valid():
            try:
                etudiant = EtudiantService.modifier(
                    etudiant, data=form.cleaned_data, modified_by=request.user
                )
                messages.success(request, "Étudiant modifié avec succès.")
                return redirect('administration:detail_etudiant', pk=pk)
            except ValidationError as e:
                messages.error(request, str(e))
    else:
        form = EtudiantForm(instance=etudiant)

    return render(request, 'administration/etudiants/modifier.html', {
        'form': form,
        'etudiant': etudiant,
        'filieres': Filiere.objects.select_related('departement').order_by('nom'),
    })


@role_required('super_admin', 'admin')
def supprimer_etudiant(request, pk):
    etudiant = get_object_or_404(Etudiant, pk=pk)
    if request.method == 'POST':
        nom = etudiant.get_full_name()
        AuditLogService.log(
            user=request.user, action='DELETE',
            model='Etudiant', object_id=pk,
            details=f"Étudiant {nom} supprimé"
        )
        etudiant.delete()
        messages.success(request, f"Étudiant {nom} supprimé.")
        return redirect('administration:liste_etudiants')
    return render(request, 'administration/etudiants/confirmer_suppression.html', {
        'etudiant': etudiant
    })


@min_role_required('scolarite')
def releve_notes(request, etudiant_id):
    etudiant = get_object_or_404(Etudiant, pk=etudiant_id)
    notes = Note.objects.filter(etudiant=etudiant).select_related('matiere').order_by(
        'semestre', 'matiere__nom')
    matieres_notes = {}
    for note in notes:
        key = (note.semestre, note.matiere.pk)
        matieres_notes.setdefault(key, {
            'matiere': note.matiere, 'semestre': note.semestre, 'notes': []
        })['notes'].append(note)
    return render(request, 'administration/releve_notes.html', {
        'etudiant': etudiant,
        'matieres_notes': matieres_notes.values(),
    })


# ════════════════════════════════════════════════════════════════
# ENSEIGNANTS
# ════════════════════════════════════════════════════════════════

@min_role_required('scolarite')
def enseignants_departements(request):
    dept_data = [{
        'dept': d,
        'nb_enseignants': Enseignant.objects.filter(departement=d, actif=True).count()
    } for d in Departement.objects.all()]
    return render(request, 'administration/enseignants/nav_departements.html', {
        'dept_data': dept_data
    })


@min_role_required('scolarite')
def enseignants_liste(request, dept_id):
    dept = get_object_or_404(Departement, pk=dept_id)
    qs = Enseignant.objects.filter(departement=dept, actif=True).order_by('grade', 'nom')
    query = request.GET.get('q', '')
    if query:
        qs = qs.filter(Q(nom__icontains=query) | Q(prenom__icontains=query)
                       | Q(matricule__icontains=query))
    return render(request, 'administration/enseignants/nav_liste.html', {
        'dept': dept, 'enseignants': qs, 'query': query,
    })


@min_role_required('scolarite')
def detail_enseignant(request, pk):
    from apps.pedagogie.models import EmploiDuTemps
    enseignant = get_object_or_404(Enseignant, pk=pk)
    seances = EmploiDuTemps.objects.filter(enseignant=enseignant).select_related(
        'matiere', 'salle', 'matiere__filiere').order_by('jour', 'heure_debut')
    JOURS = {1:'Lundi',2:'Mardi',3:'Mercredi',4:'Jeudi',5:'Vendredi',6:'Samedi'}
    emploi_par_jour = {}
    for s in seances:
        emploi_par_jour.setdefault(JOURS.get(s.jour, ''), []).append(s)
    return render(request, 'administration/enseignants/detail.html', {
        'enseignant': enseignant,
        'seances': seances,
        'emploi_par_jour': emploi_par_jour,
    })


@role_required('super_admin', 'admin', 'scolarite')
def ajouter_enseignant(request):
    if request.method == 'POST':
        form = EnseignantForm(request.POST)
        if form.is_valid():
            try:
                enseignant = form.save()
                AuditLogService.log(
                    user=request.user, action='CREATE',
                    model='Enseignant', object_id=enseignant.pk,
                    details=f"Enseignant {enseignant.get_full_name()} créé"
                )
                messages.success(request, f"Enseignant {enseignant.get_full_name()} ajouté.")
                return redirect('administration:detail_enseignant', pk=enseignant.pk)
            except Exception as e:
                messages.error(request, f"Erreur : {e}")
    else:
        form = EnseignantForm()
    return render(request, 'administration/enseignants/ajouter.html', {
        'form': form,
        'departements': Departement.objects.all(),
    })


@role_required('super_admin', 'admin', 'scolarite')
def modifier_enseignant(request, pk):
    enseignant = get_object_or_404(Enseignant, pk=pk)
    if request.method == 'POST':
        form = EnseignantForm(request.POST, instance=enseignant)
        if form.is_valid():
            form.save()
            messages.success(request, "Enseignant modifié.")
            return redirect('administration:detail_enseignant', pk=pk)
    else:
        form = EnseignantForm(instance=enseignant)
    return render(request, 'administration/enseignants/modifier.html', {
        'form': form, 'enseignant': enseignant,
        'departements': Departement.objects.all(),
    })


# ════════════════════════════════════════════════════════════════
# INSCRIPTIONS
# ════════════════════════════════════════════════════════════════

@min_role_required('scolarite')
def gestion_inscriptions(request):
    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'inscrire':
            try:
                etudiant = get_object_or_404(Etudiant, pk=request.POST['etudiant'])
                ins, created = Inscription.objects.get_or_create(
                    etudiant=etudiant,
                    annee_universitaire=request.POST['annee_univ'],
                    defaults={'filiere': etudiant.filiere, 'statut': 'en_attente'}
                )
                if created:
                    messages.success(request, f"Inscription de {etudiant.get_full_name()} créée.")
                else:
                    messages.warning(request, "L'étudiant est déjà inscrit pour cette année.")
            except Exception as e:
                messages.error(request, f"Erreur : {e}")

        elif action == 'changer_statut':
            try:
                ins = get_object_or_404(Inscription, pk=request.POST['inscription_id'])
                form = InscriptionForm(request.POST, instance=ins)
                if form.is_valid():
                    ins = form.save(commit=False)
                    if ins.statut == 'validee':
                        ins.date_validation = timezone.now().date()
                        ins.valide_par = request.user.get_full_name()
                    ins.save()
                    messages.success(request, f"Statut mis à jour : {ins.get_statut_display()}")
            except Exception as e:
                messages.error(request, f"Erreur : {e}")

        return redirect('administration:inscriptions')

    # Filtres
    statut_filtre = request.GET.get('statut', '')
    annee_filtre = request.GET.get('annee', '')
    query = request.GET.get('q', '')

    qs = Inscription.objects.select_related(
        'etudiant', 'filiere', 'filiere__departement').all()
    if statut_filtre:
        qs = qs.filter(statut=statut_filtre)
    if annee_filtre:
        qs = qs.filter(annee_universitaire=annee_filtre)
    if query:
        qs = qs.filter(
            Q(etudiant__nom__icontains=query)
            | Q(etudiant__prenom__icontains=query)
            | Q(etudiant__numero_etudiant__icontains=query)
        )

    paginator = Paginator(qs, 25)
    page = paginator.get_page(request.GET.get('page'))

    stats_statut = {s: Inscription.objects.filter(statut=s).count()
                    for s, _ in Inscription.STATUT_CHOICES}

    return render(request, 'administration/inscriptions.html', {
        'inscriptions': page,
        'etudiants': Etudiant.objects.filter(statut='inscrit').order_by('nom'),
        'departements': Departement.objects.all(),
        'statut_choices': Inscription.STATUT_CHOICES,
        'statut_filtre': statut_filtre,
        'annee_filtre': annee_filtre,
        'query': query,
        'stats': stats_statut,
    })


@role_required('super_admin', 'admin', 'chef_dept', 'doyen')
def valider_inscription(request, pk):
    ins = get_object_or_404(Inscription, pk=pk)
    ins.statut = 'validee'
    ins.date_validation = timezone.now().date()
    ins.valide_par = request.user.get_full_name()
    ins.save()
    AuditLogService.log(
        user=request.user, action='VALIDATE', model='Inscription',
        object_id=pk, details=f"Inscription {ins} validée"
    )
    messages.success(request, f"Inscription de {ins.etudiant.get_full_name()} validée.")
    return redirect('administration:inscriptions')


@min_role_required('scolarite')
def attestation_inscription(request, pk):
    ins = get_object_or_404(Inscription, pk=pk)
    if ins.statut != 'validee':
        messages.error(request, "Seules les inscriptions validées ont une attestation.")
        return redirect('administration:inscriptions')

    qr_data = (
        f"FSB-ATTESTATION\nEtudiant: {ins.etudiant.get_full_name()}\n"
        f"N°: {ins.etudiant.numero_etudiant}\nFilière: {ins.filiere.nom}\n"
        f"Année: {ins.annee_universitaire}\nValidé le: {ins.date_validation}"
    )
    qr = qrcode.QRCode(version=1, box_size=6, border=2)
    qr.add_data(qr_data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#0b1e3d", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    qr_b64 = base64.b64encode(buf.getvalue()).decode()

    return render(request, 'administration/attestation.html', {
        'ins': ins, 'qr_b64': qr_b64,
    })


# ════════════════════════════════════════════════════════════════
# SALLES
# ════════════════════════════════════════════════════════════════

@min_role_required('scolarite')
def gestion_salles(request):
    if request.method == 'POST':
        try:
            Salle.objects.create(
                nom=request.POST['nom'].strip(),
                type_salle=request.POST['type_salle'],
                capacite=int(request.POST['capacite']),
                batiment=request.POST.get('batiment', '').strip(),
            )
            messages.success(request, "Salle ajoutée.")
        except (KeyError, ValueError) as e:
            messages.error(request, f"Données invalides : {e}")
        except Exception as e:
            messages.error(request, f"Erreur : {e}")

    salles = Salle.objects.all().order_by('batiment', 'nom')
    return render(request, 'administration/salles.html', {
        'salles': salles,
        'type_choices': Salle.TYPE_CHOICES,
    })
