# Déploiement

Le projet est **prêt à déployer** : la configuration de production
(sécurité HTTPS, PostgreSQL, WhiteNoise pour les statiques, Redis) est
complète et vérifiée par le job `deploy-check` de la CI
(`python manage.py check --deploy` + `collectstatic`).

> **URL de démonstration** :
> **[https://fsb-system.onrender.com](https://fsb-system.onrender.com)**
>
> Déployée depuis ce blueprint, sans aucune intervention manuelle ni
> secret : migrations, données de démonstration et index vectoriel sont
> construits par la phase de build. Offre gratuite Render, donc mise en
> veille après ~15 min d'inactivité (premier chargement ~50 s).

### Ce que le déploiement produit, sans intervention manuelle

Le blueprint est **autonome**. La phase de build enchaîne
`migrate` → `init_data` → `build_rag_index`, donc l'instance déployée
est peuplée et indexée au premier démarrage. Il n'y a **rien à lancer
à la main dans un shell**.

**Aucun secret n'est nécessaire pour que la démo soit utile.** Sans
`GROQ_API_KEY`, le réglage `LLM_FALLBACK_OFFLINE` fait basculer la
génération sur `OfflineProvider` : le retrieval RAG, la sélection
d'outils, le contrôle RBAC et le streaming SSE restent tous
observables. Seule la fluidité rédactionnelle des réponses est
dégradée. Renseigner la clé Groq dans le dashboard active la
génération complète.

**Identifiants de démonstration** : `admin` / `demo-fsb-2026`.

Ce mot de passe est **volontairement public**. L'instance ne contient
que des données fictives, et un examinateur qui ne peut pas se connecter
ne voit rien du travail. Le compromis penche donc nettement du côté de
l'accessibilité. En local, le défaut reste `admin123` ; il se surcharge
par `--admin-password` ou `DEMO_ADMIN_PASSWORD`.

**Stockage sans état** : l'instance tourne sur SQLite, reconstruite à
chaque démarrage par `init_data`. Deux raisons. D'abord, une base
PostgreSQL gratuite Render expire après 30 jours puis est supprimée :
un lien destiné à rester vivant plusieurs mois ne peut pas en dépendre.
Ensuite, cette démo est publique et l'agent sait écrire en base — sans
état, les modifications d'un visiteur ne pénalisent pas les suivants.

Pour rétablir PostgreSQL : décommenter le bloc `databases:` et la
variable `DATABASE_URL` dans `render.yaml`. Aucune modification de code
— `config/settings/production.py` bascule selon la présence de
`DATABASE_URL`.

### Limites des offres gratuites, à connaître avant de partager l'URL

- Les instances gratuites **s'endorment** après ~15 min d'inactivité :
  le premier chargement peut demander ~50 s. Un examinateur pressé peut
  croire que le site est cassé — le signaler à côté du lien.
- Les bases de données gratuites **expirent après 30 jours**. Pour une
  URL destinée à rester cliquable pendant une campagne de candidature,
  prévoir le plan payant le plus bas ou redéployer avant échéance.

---

## Option A — Render (recommandé, offre gratuite)

Le fichier [`render.yaml`](render.yaml) est un *blueprint* qui
provisionne automatiquement les trois services (web, PostgreSQL, Redis).

1. Pousser ce dépôt sur GitHub.
2. Sur [render.com](https://render.com) → **New → Blueprint** →
   sélectionner le dépôt. Render lit `render.yaml`.
3. *Facultatif* : renseigner **`GROQ_API_KEY`** dans le dashboard
   (clé gratuite sur [console.groq.com](https://console.groq.com))
   pour activer la génération Groq. Sans elle, la démo fonctionne en
   mode déterministe. Les autres variables
   (`SECRET_KEY`, `DATABASE_URL`, `REDIS_URL`…) sont générées ou câblées
   automatiquement par le blueprint.
4. Le `buildCommand` exécute `collectstatic`, `migrate`,
   `init_data` **et** `build_rag_index` : l'instance est peuplée et
   l'index vectoriel prêt au premier démarrage. L'URL publique
   s'affiche à la fin du déploiement.
5. Relever `DEMO_ADMIN_PASSWORD` dans le dashboard pour se connecter.
6. **Reporter l'URL obtenue** dans le README (ligne « Démo en ligne »)
   et en tête de ce fichier.

`init_data` étant idempotent, il peut être rejoué à chaque déploiement
sans dupliquer de données.

---

## Option B — Toute plateforme compatible Procfile

Le [`Procfile`](Procfile) et [`runtime.txt`](runtime.txt) permettent un
déploiement sur Railway, Fly.io, Heroku, etc. :

```
web:     gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 3 --timeout 120
release: python manage.py migrate && python manage.py build_rag_index
```

Variables d'environnement minimales à définir :

| Variable | Valeur |
|---|---|
| `DJANGO_SETTINGS_MODULE` | `config.settings.production` |
| `SECRET_KEY` | (générer une clé forte) |
| `DEBUG` | `False` |
| `ALLOWED_HOSTS` | domaine du service |
| `DATABASE_URL` | fournie par le module PostgreSQL |
| `REDIS_URL` | fournie par le module Redis |
| `GROQ_API_KEY` | votre clé Groq |

---

## Option C — Docker

```bash
# Build de l'image de production (multi-stage, voir docker/Dockerfile)
docker build -f docker/Dockerfile -t fsb-system .

# La stack complète de développement (web + PostgreSQL + Redis)
docker-compose up -d
# → http://localhost:8000
```

---

## Après déploiement : vérifications

```bash
# Santé de l'application
curl -I https://VOTRE-URL/accounts/login/        # → 200

# L'agent IA répond (nécessite une session authentifiée)
#   se connecter, ouvrir /ai/chat/ et poser une question

# Reconstruire l'index RAG si le corpus a changé
python manage.py build_rag_index
```

## Notes de production

- **Statiques** : servis par WhiteNoise (`CompressedManifestStaticFilesStorage`),
  aucun nginx requis. `collectstatic` est exécuté au build.
- **Index RAG** : reconstruit à chaque release (`build_rag_index` dans
  le `release`/`buildCommand`), stocké dans `var/rag_index/`. Sur un
  système de fichiers éphémère, il est simplement reconstruit au
  démarrage — l'opération prend moins d'une seconde.
- **Embeddings** : `RAG_EMBEDDING_BACKEND=tfidf` par défaut (aucun
  téléchargement). Pour la qualité sémantique maximale, passer à
  `sentence-transformers` (ajouter le paquet à `requirements/production.txt`).
- **LLM** : `LLM_PROVIDER=groq` en production. Le mode `offline` n'est
  destiné qu'aux tests et à la CI.
