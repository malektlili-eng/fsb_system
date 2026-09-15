"""
apps/administration/forms.py (V2 - corrigé)
"""
from django import forms
from .models import Etudiant, Enseignant, Inscription
import datetime


class EtudiantForm(forms.ModelForm):
    class Meta:
        model = Etudiant
        fields = [
            'nom', 'prenom', 'numero_etudiant', 'cin',
            'email', 'telephone', 'filiere',
            'annee_inscription', 'date_naissance',
            'lieu_naissance', 'adresse', 'statut',
        ]
        widgets = {
            'date_naissance': forms.DateInput(attrs={'type': 'date'}),
            'adresse': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # numero_etudiant et statut sont optionnels à la création (auto-générés)
        self.fields['numero_etudiant'].required = False
        self.fields['statut'].required = False
        self.fields['statut'].initial = 'inscrit'
        self.fields['cin'].required = False
        self.fields['telephone'].required = False
        self.fields['date_naissance'].required = False
        self.fields['lieu_naissance'].required = False
        self.fields['adresse'].required = False
        self.fields['email'].required = False
        self.fields['annee_inscription'].required = False

    def clean_nom(self):
        nom = self.cleaned_data.get('nom', '').strip()
        if not nom:
            raise forms.ValidationError("Le nom ne peut pas être vide.")
        if len(nom) < 2:
            raise forms.ValidationError("Le nom doit contenir au moins 2 caractères.")
        return nom.upper()

    def clean_prenom(self):
        prenom = self.cleaned_data.get('prenom', '').strip()
        if not prenom:
            raise forms.ValidationError("Le prénom ne peut pas être vide.")
        return prenom.title()

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        if email:
            qs = Etudiant.objects.filter(email=email)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError("Cet email est déjà utilisé.")
        return email

    def clean_numero_etudiant(self):
        numero = self.cleaned_data.get('numero_etudiant', '').strip()
        if numero:
            qs = Etudiant.objects.filter(numero_etudiant=numero)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError("Ce numéro étudiant est déjà attribué.")
        return numero

    def clean_annee_inscription(self):
        annee = self.cleaned_data.get('annee_inscription')
        if annee is None:
            return datetime.date.today().year
        if annee < 2000 or annee > 2100:
            raise forms.ValidationError("Année invalide.")
        return annee

    def clean_statut(self):
        return self.cleaned_data.get('statut') or 'inscrit'


class EnseignantForm(forms.ModelForm):
    class Meta:
        model = Enseignant
        fields = [
            'nom', 'prenom', 'matricule', 'email', 'telephone',
            'departement', 'grade', 'specialite',
            'date_recrutement', 'actif',
        ]
        widgets = {
            'date_recrutement': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].required = False
        self.fields['telephone'].required = False
        self.fields['specialite'].required = False
        self.fields['date_recrutement'].required = False
        self.fields['departement'].required = False

    def clean_matricule(self):
        matricule = self.cleaned_data.get('matricule', '').strip().upper()
        if not matricule:
            raise forms.ValidationError("Le matricule est obligatoire.")
        qs = Enseignant.objects.filter(matricule=matricule)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("Ce matricule est déjà utilisé.")
        return matricule

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        if email:
            qs = Enseignant.objects.filter(email=email)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError("Cet email est déjà utilisé.")
        return email


class InscriptionForm(forms.ModelForm):
    class Meta:
        model = Inscription
        fields = ['statut', 'commentaire']
        widgets = {'commentaire': forms.Textarea(attrs={'rows': 3})}
