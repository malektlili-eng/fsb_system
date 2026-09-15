"""
config/settings/development.py
─────────────────────────────────────────────────────────────────────
Settings de développement. Ne jamais utiliser en production.
─────────────────────────────────────────────────────────────────────
"""
from .base import *
from decouple import config

DEBUG = True

# ─── Base de données SQLite pour le dev ──────────────────────────────
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'fsb_database.db',
    }
}

# ─── Django Debug Toolbar ─────────────────────────────────────────────
INSTALLED_APPS += ['debug_toolbar']
MIDDLEWARE.insert(0, 'debug_toolbar.middleware.DebugToolbarMiddleware')
INTERNAL_IPS = ['127.0.0.1']

# ─── Email console (affiche les emails dans le terminal) ──────────────
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# ─── CORS permissif en dev ───────────────────────────────────────────
CORS_ALLOW_ALL_ORIGINS = True

# Permettre au test client Django de fonctionner
ALLOWED_HOSTS += ['testserver', '*']
