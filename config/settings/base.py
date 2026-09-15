"""
config/settings/base.py
─────────────────────────────────────────────────────────────────────
Settings communs à tous les environnements.
Les valeurs sensibles sont lues depuis les variables d'environnement
via python-decouple. Ne JAMAIS hardcoder de secret ici.
─────────────────────────────────────────────────────────────────────
"""
from pathlib import Path
from decouple import config, Csv

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# ─── Sécurité (valeurs depuis .env) ─────────────────────────────────
SECRET_KEY = config('SECRET_KEY')
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost', cast=Csv())

# ─── Applications ────────────────────────────────────────────────────
DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

THIRD_PARTY_APPS = [
    'rest_framework',
    'rest_framework_simplejwt',
    'django_filters',
    'corsheaders',
    'crispy_forms',
    'crispy_bootstrap5',
    'drf_spectacular',
]

LOCAL_APPS = [
    'apps.accounts',
    'apps.administration',
    'apps.pedagogie',
    'apps.examens',
    'apps.stages',
    'apps.ai_agent',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# ─── Middleware ───────────────────────────────────────────────────────
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [BASE_DIR / 'templates'],
    'APP_DIRS': True,
    'OPTIONS': {'context_processors': [
        'django.template.context_processors.debug',
        'django.template.context_processors.request',
        'django.contrib.auth.context_processors.auth',
        'django.contrib.messages.context_processors.messages',
    ]},
}]

WSGI_APPLICATION = 'config.wsgi.application'

# ─── Validation des mots de passe ────────────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
     'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ─── Internationalisation ─────────────────────────────────────────────
LANGUAGE_CODE = 'fr-fr'
TIME_ZONE = 'Africa/Tunis'
USE_I18N = True
USE_TZ = True

# ─── Fichiers statiques ──────────────────────────────────────────────
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# ─── Auth ─────────────────────────────────────────────────────────────
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
AUTH_USER_MODEL = 'accounts.CustomUser'
LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/accounts/login/'

# ─── Crispy Forms ────────────────────────────────────────────────────
CRISPY_ALLOWED_TEMPLATE_PACKS = 'bootstrap5'
CRISPY_TEMPLATE_PACK = 'bootstrap5'

# ─── Django REST Framework ────────────────────────────────────────────
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 25,
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

# ─── Documentation API ───────────────────────────────────────────────
SPECTACULAR_SETTINGS = {
    'TITLE': 'FSB System API',
    'DESCRIPTION': 'API REST du Système de Gestion Universitaire FSB',
    'VERSION': '2.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
}

# ─── API Keys IA ─────────────────────────────────────────────────────
GROQ_API_KEY = config('GROQ_API_KEY', default='')
GROQ_MODEL = config('GROQ_MODEL', default='llama-3.3-70b-versatile')

# ─── Logging ─────────────────────────────────────────────────────────
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{levelname}] {asctime} {module} — {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'file': {
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'logs' / 'fsb.log',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'apps.ai_agent': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'django': {
            'handlers': ['console'],
            'level': 'WARNING',
        },
    },
}

# ─── Agent IA : RAG et fournisseur LLM ────────────────────────────────
# Fournisseur de génération : "groq" (production) | "offline" (tests/CI)
LLM_PROVIDER = config('LLM_PROVIDER', default='groq')

# Si LLM_PROVIDER="groq" mais que le SDK ou la clé manquent, basculer
# silencieusement sur le fournisseur déterministe hors-ligne plutôt que
# de planter. Objectif : un déploiement de démonstration reste utilisable
# sans secret (RAG, tool calling et streaming SSE restent observables).
# En production réelle, mettre False pour échouer bruyamment.
LLM_FALLBACK_OFFLINE = config(
    'LLM_FALLBACK_OFFLINE', default=True, cast=bool
)

# Backend d'embeddings du RAG :
#   "tfidf"   → défaut : creux, aucun téléchargement, CI reproductible
#   "spacy" | "hybrid" | "sentence-transformers" → backends sémantiques
# Voir l'ablation A4 (reports/rag_evaluation.md) : les backends
# sémantiques améliorent les paraphrases mais dégradent le rejet
# hors-corpus. Repli automatique sur tfidf si le modèle est absent.
RAG_EMBEDDING_BACKEND = config('RAG_EMBEDDING_BACKEND', default='tfidf')

# Répertoire de persistance de l'index vectoriel
RAG_INDEX_DIR = BASE_DIR / 'var' / 'rag_index'

# Dossier du corpus RAG. Par défaut : corpus institutionnel FSB.
# Le pointer ailleurs (dossier de .md d'un autre domaine) fait tourner
# le même moteur RAG sur ce domaine, sans changement de code.
RAG_CORPUS_DIR = config('RAG_CORPUS_DIR', default='')
