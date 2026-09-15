# docker/Dockerfile
# ═══════════════════════════════════════════════════════════════════
#  FSB System — Image Docker multi-stage
#  Stage 1 : installation des dépendances
#  Stage 2 : image de production minimale
# ═══════════════════════════════════════════════════════════════════

FROM python:3.12-slim AS builder

WORKDIR /app

# Dépendances système
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Installer les dépendances Python
COPY requirements/production.txt .
RUN pip install --no-cache-dir --prefix=/install -r production.txt


# ─── Image finale ─────────────────────────────────────────────────
FROM python:3.12-slim AS production

WORKDIR /app

# Dépendances runtime uniquement
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copier les packages installés
COPY --from=builder /install /usr/local

# Copier le code source
COPY . .

# Collecter les fichiers statiques
RUN python manage.py collectstatic --noinput \
    --settings=config.settings.production

# Utilisateur non-root pour la sécurité
RUN adduser --disabled-password --gecos '' appuser
USER appuser

EXPOSE 8000

# Gunicorn avec workers optimisés
CMD ["gunicorn", "config.wsgi:application", \
    "--bind", "0.0.0.0:8000", \
    "--workers", "3", \
    "--timeout", "120", \
    "--access-logfile", "-", \
    "--error-logfile", "-"]
