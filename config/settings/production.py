"""
config/settings/production.py
─────────────────────────────────────────────────────────────────────
Settings de production. Sécurisés, PostgreSQL, pas de debug.
─────────────────────────────────────────────────────────────────────
"""
from .base import *
from decouple import config
import dj_database_url

DEBUG = False

# ─── Fichiers statiques via WhiteNoise (déploiement PaaS sans nginx) ──
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}
# WhiteNoise doit être inséré juste après le SecurityMiddleware.
_security_idx = MIDDLEWARE.index(
    'django.middleware.security.SecurityMiddleware'
)
MIDDLEWARE.insert(
    _security_idx + 1, 'whitenoise.middleware.WhiteNoiseMiddleware'
)

# ─── Base de données ─────────────────────────────────────────────────
# PostgreSQL dès que DATABASE_URL est fournie — c'est la configuration
# de production, et celle du docker-compose.
#
# Sans DATABASE_URL, repli sur SQLite. Ce n'est pas un raccourci : c'est
# le mode "démonstration sans état". Sur un hébergement gratuit, le
# système de fichiers est éphémère, donc la base se reconstruit à chaque
# démarrage à partir de `init_data`. Deux conséquences voulues :
#   - aucune base à renouveler, donc aucun lien qui meurt en silence ;
#   - la démo se répare seule si un visiteur modifie les données.
# ssl_require ne s'applique qu'à une vraie connexion distante.
_DATABASE_URL = config('DATABASE_URL', default='')

if _DATABASE_URL and not _DATABASE_URL.startswith('sqlite'):
    # Base distante (PostgreSQL) : connexions persistantes et SSL exigé.
    DATABASES = {
        'default': dj_database_url.config(
            default=_DATABASE_URL,
            conn_max_age=600,
            ssl_require=True,
        )
    }
elif _DATABASE_URL:
    # URL SQLite fournie explicitement : surtout pas ssl_require, qui
    # injecterait une option `sslmode` que le pilote SQLite refuse.
    DATABASES = {'default': dj_database_url.config(default=_DATABASE_URL)}
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'demo.sqlite3',
        }
    }

# ─── Cache Redis ─────────────────────────────────────────────────────
REDIS_URL = config('REDIS_URL', default='redis://localhost:6379/0')
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': REDIS_URL,
        'TIMEOUT': 300,
    }
}

# ─── Sécurité HTTPS ──────────────────────────────────────────────────
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
X_FRAME_OPTIONS = 'DENY'

# ─── Email réel ──────────────────────────────────────────────────────
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = config('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS = True
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='noreply@fsb.tn')

# ─── CORS ────────────────────────────────────────────────────────────
CORS_ALLOWED_ORIGINS = config(
    'CORS_ALLOWED_ORIGINS',
    default='',
    cast=lambda v: [s.strip() for s in v.split(',') if s.strip()],
)
