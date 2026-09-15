"""
init_data.py — compatibilité ascendante.
─────────────────────────────────────────────────────────────────────
La logique de seeding vit désormais dans une VRAIE commande Django :

    python manage.py init_data

C'est cette forme qui est documentée, testée et utilisée par le
déploiement (`render.yaml`, `Procfile`). Ce fichier reste uniquement
pour ne pas casser l'ancienne invocation `python init_data.py`.
─────────────────────────────────────────────────────────────────────
"""
import os
import sys

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from django.core.management import call_command  # noqa: E402

if __name__ == '__main__':
    print(
        "ℹ️  `python init_data.py` est conservé par compatibilité.\n"
        "   Forme recommandée : python manage.py init_data\n"
    )
    call_command('init_data', *sys.argv[1:])
