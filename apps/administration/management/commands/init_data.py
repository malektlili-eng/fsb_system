"""
apps/administration/management/commands/init_data.py
─────────────────────────────────────────────────────────────────────
Commande de gestion : charge un jeu de données de démonstration.

    python manage.py init_data
    python manage.py init_data --admin-password=<mdp>

Pourquoi une commande et non un script racine : le déploiement
(`render.yaml`, `Procfile`) doit pouvoir semer la base dans la même
phase que `migrate` et `build_rag_index`, sans bricoler
`DJANGO_SETTINGS_MODULE` ni rediriger un fichier dans `shell`. Une URL
de démonstration qui s'ouvre sur un formulaire de connexion où aucun
compte n'existe est une URL inutile.

Idempotente : repose entièrement sur `get_or_create`, donc rejouable à
chaque déploiement sans dupliquer de données.

Le mot de passe admin est paramétrable (`--admin-password`, ou la
variable d'environnement `DEMO_ADMIN_PASSWORD`) : une instance publique
ne doit pas exposer un mot de passe écrit en clair dans le dépôt.
─────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import os

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import CustomUser
from apps.administration.models import (
    Departement, Filiere, Classe, Enseignant, Etudiant, Salle, Inscription
)
from apps.pedagogie.models import Matiere, EmploiDuTemps
from apps.examens.models import SessionExamen
from apps.stages.models import DemandeStage
from datetime import date, timedelta


class Command(BaseCommand):
    help = "Charge les données de démonstration (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--admin-password",
            default=os.environ.get("DEMO_ADMIN_PASSWORD", "admin123"),
            help=(
                "Mot de passe du compte admin de démonstration. "
                "Défaut : $DEMO_ADMIN_PASSWORD ou 'admin123'."
            ),
        )
        parser.add_argument(
            "--quiet",
            action="store_true",
            help="N'affiche que le résumé final.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        admin_password = options["admin_password"]
        quiet = options["quiet"]

        def echo(message="", *rest, **kwargs):
            if quiet:
                return
            self.stdout.write(str(message))

        echo("🚀 Initialisation des données de démonstration FSB V2...")

        # ─── Utilisateurs ─────────────────────────────────────────────
        users_data = [
            ('admin',       admin_password, 'super_admin', 'Admin',    'FSB'),
            ('scolarite1',  'scolarite123', 'scolarite',   'Amira',    'Ben Salah'),
            ('chef_info',   'chef123',      'chef_dept',   'Mohamed',  'Trabelsi'),
            ('doyen',       'doyen123',     'doyen',       'Fatma',    'Bouchenak'),
        ]
        for username, pwd, role, first, last in users_data:
            u = CustomUser.objects.filter(username=username).first()
            if u is None:
                u = CustomUser.objects.create_user(
                    username=username, password=pwd, role=role,
                    first_name=first, last_name=last,
                    email=f'{username}@fsb.tn',
                )
                echo(f"  ✓ Utilisateur : {username} / {pwd} [{role}]")
            elif not u.check_password(pwd):
                # Le compte existe mais son mot de passe ne correspond plus
                # à celui attendu — typiquement après un changement de
                # DEMO_ADMIN_PASSWORD. Sans ce réalignement, la variable
                # d'environnement serait ignorée sur toute base déjà semée,
                # et personne ne pourrait se connecter à la démonstration.
                # Ce sont des comptes de démonstration : leur mot de passe
                # est une donnée de seed, pas un secret d'utilisateur.
                u.set_password(pwd)
                u.save(update_fields=['password'])
                echo(f"  ↻ Mot de passe réaligné : {username} [{role}]")

        # ─── Départements ─────────────────────────────────────────────
        depts = {}
        for nom in ('informatique', 'mathematiques', 'physique', 'chimie'):
            d, _ = Departement.objects.get_or_create(nom=nom)
            depts[nom] = d
            echo(f"  ✓ Département : {d.get_nom_display()}")

        # ─── Filières ─────────────────────────────────────────────────
        filieres_data = [
            ('Licence Fondamentale en Informatique', 'LFI', 'informatique', 'L3', 'licence'),
            ('Licence Appliquée en Informatique',    'LAI', 'informatique', 'L3', 'licence'),
            ('Master Informatique',                  'MI',  'informatique', 'M2', 'master'),
            ('Licence Mathématiques',                'LM',  'mathematiques','L3', 'licence'),
            ('Licence Physique',                     'LP',  'physique',     'L3', 'licence'),
            ('CPI1',                                 'CPI1','informatique', 'L1', 'cpi'),
        ]
        filieres = {}
        for nom, code, dept_nom, niveau, tf in filieres_data:
            f, created = Filiere.objects.get_or_create(
                code=code,
                defaults={'nom': nom, 'departement': depts[dept_nom],
                          'niveau': niveau, 'type_formation': tf}
            )
            filieres[code] = f
            if created:
                echo(f"  ✓ Filière : {code} — {nom}")

        # ─── Classes ──────────────────────────────────────────────────
        classes_data = [
            ('LFI 3ème année A', 'LFI-3A', 'LFI', 'L3'),
            ('LFI 3ème année B', 'LFI-3B', 'LFI', 'L3'),
            ('LAI 3ème année',   'LAI-3A', 'LAI', 'L3'),
            ('MI 2ème année',    'MI-2A',  'MI',  'M2'),
            ('LM 3ème année',    'LM-3A',  'LM',  'L3'),
        ]
        classes = {}
        for nom, code, fil_code, niveau in classes_data:
            cl, created = Classe.objects.get_or_create(
                code=code,
                defaults={'nom': nom, 'filiere': filieres[fil_code],
                          'niveau': niveau, 'annee_universitaire': '2024-2025'}
            )
            classes[code] = cl
            if created:
                echo(f"  ✓ Classe : {code}")

        # ─── Salles ───────────────────────────────────────────────────
        salles_data = [
            ('Amphi A', 'amphi', 250, 'Bâtiment Principal'),
            ('Amphi B', 'amphi', 200, 'Bâtiment Principal'),
            ('Salle S1', 'salle', 40,  'Bâtiment B'),
            ('Salle S2', 'salle', 40,  'Bâtiment B'),
            ('Salle S3', 'salle', 35,  'Bâtiment B'),
            ('Salle TP1', 'tp', 25,   'Bâtiment Info'),
            ('Salle TP2', 'tp', 25,   'Bâtiment Info'),
            ('Salle Info1', 'info', 30, 'Bâtiment Info'),
        ]
        for nom, type_s, cap, bat in salles_data:
            s, created = Salle.objects.get_or_create(
                nom=nom,
                defaults={'type_salle': type_s, 'capacite': cap, 'batiment': bat}
            )
            if created:
                echo(f"  ✓ Salle : {nom}")

        # ─── Enseignants ──────────────────────────────────────────────
        enseignants_data = [
            ('BEN AMOR',   'Karim',   'MAT001', 'informatique', 'maitre_conf',  'Algorithmique'),
            ('TRABELSI',   'Sonia',   'MAT002', 'informatique', 'professeur',   'Bases de Données'),
            ('HAMDI',      'Youssef', 'MAT003', 'informatique', 'assistant',    'Réseaux'),
            ('MANSOUR',    'Leila',   'MAT004', 'mathematiques','maitre_conf',  'Analyse'),
            ('BOUGHANMI',  'Tarek',   'MAT005', 'physique',     'maitre_assistant','Électronique'),
        ]
        enseignants = {}
        for nom, prenom, mat, dept_nom, grade, spec in enseignants_data:
            e, created = Enseignant.objects.get_or_create(
                matricule=mat,
                defaults={'nom': nom, 'prenom': prenom, 'departement': depts[dept_nom],
                          'grade': grade, 'specialite': spec, 'actif': True,
                          'email': f'{mat.lower()}@fsb.tn'}
            )
            enseignants[mat] = e
            if created:
                echo(f"  ✓ Enseignant : {prenom} {nom}")

        # ─── Matières ─────────────────────────────────────────────────
        matieres_data = [
            ('Algorithmique Avancée',    'ALGO3',  'LFI', 3, 2.0, 1, 42, 21, 21),
            ('Bases de Données',         'BDD3',   'LFI', 3, 2.0, 1, 42, 21, 0),
            ('Réseaux Informatiques',    'RES3',   'LFI', 3, 2.0, 2, 42, 21, 21),
            ('Génie Logiciel',           'GL3',    'LFI', 3, 2.0, 2, 42, 21, 0),
            ('Programmation Web',        'WEB3',   'LFI', 2, 1.5, 2, 21, 21, 21),
            ('Algèbre Linéaire',         'ALG3',   'LM',  3, 2.0, 1, 42, 21, 0),
            ('Analyse Mathématique',     'ANA3',   'LM',  3, 2.0, 2, 42, 21, 0),
        ]
        matieres = {}
        for nom, code, fil, cr, coef, sem, hc, htd, htp in matieres_data:
            m, created = Matiere.objects.get_or_create(
                code=code,
                defaults={'nom': nom, 'filiere': filieres[fil], 'credits': cr,
                          'coefficient': coef, 'semestre': sem,
                          'heures_cours': hc, 'heures_td': htd, 'heures_tp': htp}
            )
            matieres[code] = m
            if created:
                echo(f"  ✓ Matière : {code} — {nom}")

        # ─── Étudiants ────────────────────────────────────────────────
        etudiants_data = [
            ('BEN SALAH',  'Amine',   'ETU202400001', 'LFI', 2024, 'ETU202400001@etu.fsb.tn'),
            ('TRABELSI',   'Nour',    'ETU202400002', 'LFI', 2024, 'ETU202400002@etu.fsb.tn'),
            ('HAMDI',      'Sarra',   'ETU202400003', 'LFI', 2024, 'ETU202400003@etu.fsb.tn'),
            ('MANSOURI',   'Yassine', 'ETU202400004', 'LFI', 2024, 'ETU202400004@etu.fsb.tn'),
            ('BOUGHANMI',  'Fatma',   'ETU202400005', 'LAI', 2024, 'ETU202400005@etu.fsb.tn'),
            ('SASSI',      'Mohamed', 'ETU202400006', 'LAI', 2024, 'ETU202400006@etu.fsb.tn'),
            ('CHABBI',     'Rania',   'ETU202300001', 'MI',  2023, 'ETU202300001@etu.fsb.tn'),
            ('JEBRI',      'Khaled',  'ETU202300002', 'MI',  2023, 'ETU202300002@etu.fsb.tn'),
        ]
        for nom, prenom, numero, fil_code, annee, email in etudiants_data:
            e, created = Etudiant.objects.get_or_create(
                numero_etudiant=numero,
                defaults={'nom': nom, 'prenom': prenom, 'filiere': filieres[fil_code],
                          'annee_inscription': annee, 'statut': 'inscrit', 'email': email}
            )
            if created:
                Inscription.objects.get_or_create(
                    etudiant=e, annee_universitaire='2024-2025',
                    defaults={'filiere': filieres[fil_code], 'statut': 'validee',
                              'valide_par': 'Admin FSB',
                              'date_validation': date.today()}
                )
                echo(f"  ✓ Étudiant : {numero} — {prenom} {nom}")

        # ─── Session d'examen ─────────────────────────────────────────
        sess, created = SessionExamen.objects.get_or_create(
            nom='Session Principale S1 2024-2025',
            defaults={
                'type_session': 'principale',
                'annee_universitaire': '2024-2025',
                'semestre': 1,
                'date_debut': date(2025, 1, 10),
                'date_fin': date(2025, 1, 25),
            }
        )
        if created:
            echo("  ✓ Session : Session Principale S1 2024-2025")

        # ─── Demande de stage ─────────────────────────────────────────
        if Etudiant.objects.filter(numero_etudiant='ETU202300001').exists():
            et_pfe = Etudiant.objects.get(numero_etudiant='ETU202300001')
            stage, created = DemandeStage.objects.get_or_create(
                etudiant=et_pfe,
                type_stage='pfe',
                defaults={
                    'entreprise': 'Société Informatique Tunis',
                    'sujet': 'Développement d\'une plateforme e-learning avec IA',
                    'date_debut': date(2025, 2, 1),
                    'date_fin': date(2025, 7, 31),
                    'statut': 'en_attente',
                }
            )
            if created:
                echo("  ✓ Demande de stage PFE créée")

        echo()
        echo("=" * 55)
        echo("✅  Données de démonstration chargées avec succès !")
        echo("=" * 55)
        echo()
        echo("Comptes disponibles :")
        echo(f"  admin       / {admin_password}      [super_admin]")
        echo("  scolarite1  / scolarite123  [scolarite]")
        echo("  chef_info   / chef123       [chef_dept]")
        echo("  doyen       / doyen123      [doyen]")
        echo()
        echo("→ http://localhost:8000")
