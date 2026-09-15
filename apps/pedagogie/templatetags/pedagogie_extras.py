"""
apps/pedagogie/templatetags/pedagogie_extras.py
Tags de template personnalisés pour la pédagogie.
"""
from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Accède à un dictionnaire par clé variable dans un template."""
    if isinstance(dictionary, dict):
        return dictionary.get(key)
    return None


@register.filter
def note_couleur(note):
    """Retourne une classe CSS selon la note."""
    if note is None:
        return 'b-gray'
    note = float(note)
    if note >= 16:
        return 'b-green'
    if note >= 12:
        return 'b-blue'
    if note >= 10:
        return 'b-yellow'
    return 'b-red'


@register.filter
def mention_couleur(mention):
    """Retourne une classe CSS selon la mention."""
    mapping = {
        'excellent':  'b-green',
        'tres_bien':  'b-green',
        'bien':       'b-blue',
        'assez_bien': 'b-blue',
        'passable':   'b-yellow',
        '':           'b-red',
    }
    return mapping.get(mention, 'b-gray')


@register.filter
def statut_couleur(statut):
    """Retourne une classe CSS selon le statut."""
    mapping = {
        'inscrit':    'b-green',
        'diplome':    'b-blue',
        'suspendu':   'b-yellow',
        'abandonne':  'b-red',
        'validee':    'b-green',
        'en_attente': 'b-yellow',
        'annulee':    'b-red',
        'valide':     'b-green',
        'refuse':     'b-red',
        'en_cours':   'b-blue',
        'termine':    'b-purple',
    }
    return mapping.get(statut, 'b-gray')


@register.filter
def pct(value, total):
    """Calcule un pourcentage."""
    try:
        return round(float(value) / float(total) * 100, 1)
    except (TypeError, ZeroDivisionError):
        return 0


@register.filter
def abs_count(etudiant, matiere):
    """Compte les absences d'un étudiant pour une matière."""
    from apps.pedagogie.models import Absence
    return Absence.objects.filter(etudiant=etudiant, seance__matiere=matiere).count()


@register.simple_tag
def note_of(etudiant, matiere, type_note, annee='2024-2025', semestre=1):
    """Retourne la note d'un étudiant pour une matière et un type donné."""
    from apps.pedagogie.models import Note
    note = Note.objects.filter(
        etudiant=etudiant, matiere=matiere,
        type_note=type_note,
        annee_universitaire=annee,
        semestre=semestre,
    ).first()
    return note.note if note else '—'


@register.filter
def dict_lookup(dictionary, key):
    """Accès à un dict par clé variable — alias de get_item."""
    if isinstance(dictionary, dict):
        return dictionary.get(key)
    return None
