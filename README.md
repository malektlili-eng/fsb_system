# FSB System V2 — Plateforme de gestion universitaire avec agent IA testable

[![CI/CD](https://github.com/malektlili-eng/fsb_system/actions/workflows/ci.yml/badge.svg)](https://github.com/malektlili-eng/fsb_system/actions)
[![Coverage AI/RAG](https://img.shields.io/badge/coverage%20AI%2FRAG-94%25-brightgreen.svg)](reports/coverage_split.md)
[![Coverage applicatif](https://img.shields.io/badge/coverage%20applicatif-70%25-yellow.svg)](reports/coverage_split.md)
[![Tests](https://img.shields.io/badge/tests-162%20passing-brightgreen.svg)](tests/)
[![RAG eval](https://img.shields.io/badge/RAG-eval%20%2B%205%20ablations-blue.svg)](reports/rag_evaluation.md)
[![Python](https://img.shields.io/badge/Python-3.12-blue.svg)](https://python.org)
[![Django](https://img.shields.io/badge/Django-5.x-green.svg)](https://djangoproject.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> Application Django de production — couche service, DRF, RBAC,
> PostgreSQL, Redis, CI/CD complète — dotée d'un agent IA dont
> **l'intégralité du pipeline se teste sans réseau ni clé API**.

---

## Le problème que ce projet résout vraiment

Une application qui appelle un LLM est facile à écrire et **pénible à
tester**. Le fournisseur est non déterministe, payant, et exige un
secret : la plupart des équipes finissent par mocker le client HTTP, ce
qui ne teste plus rien d'intéressant, ou par ne pas tester du tout la
couche agent.

Ici, la génération est isolée derrière une interface
(`apps/ai_agent/llm/providers.py`) dont il existe une implémentation
**déterministe et hors-ligne**, `OfflineProvider`. Elle ne renvoie pas
une chaîne figée : elle **rejoue le protocole complet** — streaming
fragment par fragment, émission de `tool_calls` structurés, second tour
après injection des résultats d'outils.

Conséquence directe, et c'est le point central de ce dépôt :

```bash
# Aucune variable d'environnement. Aucun réseau. Aucune clé API.
python manage.py test tests/
# → 162 tests, dont le pipeline agent de bout en bout
```

Ces tests vérifient des propriétés qu'on ne peut normalement pas
vérifier en CI :

| Propriété vérifiée | Test |
|---|---|
| Le RAG se déclenche sur une question documentaire, **et pas** sur une question transactionnelle | `test_orchestrator_stream.py` |
| Le bon outil est sélectionné et **réellement exécuté** en base | `test_tool_executor.py` |
| Le RBAC bloque un outil interdit au rôle courant | `test_tool_executor.py` |
| Les `tool_calls` **fragmentés** par le streaming sont réassemblés correctement | `test_views_and_commands.py` |
| Une requête hors-corpus est **rejetée** au lieu de polluer le prompt | `test_rag_retrieval.py` |

La même abstraction rend les benchmarks reproductibles : `run_benchmarks`
mesure la latence et la conformité sur 20 requêtes sans dépendre de la
charge d'un fournisseur externe.

---

## Démo en ligne

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/malektlili-eng/fsb_system)

**→ [https://fsb-system.onrender.com](https://fsb-system.onrender.com)** — instance en service.

> L'instance tourne sur l'offre gratuite Render et **se met en veille
> après ~15 min d'inactivité** : le tout premier chargement peut
> demander ~50 s. Ce n'est pas une panne.

Le blueprint est **autonome** : la phase de build enchaîne
`migrate` → `init_data` → `build_rag_index`, donc l'instance déployée
est peuplée et indexée dès le premier démarrage — rien à lancer
manuellement dans un shell.

**Aucun secret n'est nécessaire.** Sans `GROQ_API_KEY`, le réglage
`LLM_FALLBACK_OFFLINE` bascule la génération sur `OfflineProvider` : le
retrieval, la sélection d'outils, le RBAC et le streaming SSE restent
tous observables. Ajouter la clé active la génération Groq complète.
Identifiants : `admin`, mot de passe généré par Render
(`DEMO_ADMIN_PASSWORD`, à relever dans le dashboard). Détails et
limites des offres gratuites : [`DEPLOYMENT.md`](DEPLOYMENT.md).

---

## Ce que le projet démontre

### 1. Ingénierie Django de production

- **Couche service** séparée des vues (`apps/*/services.py`) — la
  logique métier n'est pas dans les contrôleurs
- **API REST DRF** avec ViewSets, serializers et schéma OpenAPI généré
- **RBAC centralisé** (`core/permissions.py`), 5 rôles, appliqué
  aussi bien aux vues qu'aux outils de l'agent
- **PostgreSQL** en production, **Redis** pour le cache, **WhiteNoise**
  pour les statiques
- Settings segmentés `base` / `development` / `production`

### 2. CI/CD réellement contraignante

Le pipeline ([`.github/workflows/ci.yml`](.github/workflows/ci.yml))
comporte quatre jobs :

| Job | Contenu |
|---|---|
| `lint` | flake8 bloquant sur les erreurs de syntaxe, black et isort en conseil |
| `test` | **matrice Python 3.11/3.12**, migrations, porte globale ≥ 65 % **et** porte IA/RAG ≥ 90 % |
| `rag-eval` | installe le backend sémantique, régénère l'évaluation RAG et les benchmarks, publie les rapports en artefacts |
| `deploy-check` | `check --deploy`, `collectstatic`, **bandit** sur `apps/` |

Les portes de couverture sont **exécutées**, pas décoratives : le build
échoue sous 65 % global ou sous 90 % sur la couche IA/RAG.

### 3. Tool calling et streaming SSE

L'agent n'écrit pas seulement du texte : il **agit** en base
(création d'étudiant avec numérotation automatique, planification
d'examen avec détection de conflits de salles), sous contrôle RBAC, et
diffuse sa réponse en Server-Sent Events avec les événements
intermédiaires (`rag`, `tool_start`, `tool_done`, `token`).

### 4. Une couche retrieval possédée, pas un appel d'API

Le sous-système RAG est implémenté ici : découpage phrase-aligné,
embeddings locaux, index vectoriel cosinus, score hybride
dense + lexical, seuil de rejet. Il est **évalué** plutôt que décrit —
voir la section suivante.

---

## Évaluation du retrieval

> Ce volet a été mené en amont d'un stage de recherche en laboratoire
> consacré à la comparaison d'architectures de retrieval (Vector RAG vs
> Graph RAG). L'ordre compte : d'abord livrer un système de retrieval en
> production et mesurer ses limites, ensuite aller poser la question de
> l'architecture en laboratoire. Ce dépôt est le premier temps de cette
> trajectoire — le versant ingénierie.

Gold set de 30 requêtes annotées (27 avec pertinence + 3 hors-corpus),
métriques IR, **5 ablations exécutées**
([`reports/rag_evaluation.md`](reports/rag_evaluation.md)) :

| Métrique | Valeur |
|---|---|
| Recall@4 | 0,759 |
| MRR | 0,778 |
| nDCG@4 | 0,763 |
| Rejet hors-corpus | 0,67 |
| Precision@4 | 0,259 *(plafond du gold set : 0,343)* |

Trois résultats valent d'être lus :

- **Deux configurations rejetées malgré de meilleurs scores.** La
  projection LSA (A5) atteint 0,889 de Recall@4 contre 0,759 pour le
  défaut, et le backend hybride (A4) 0,833 — les deux ont été
  **écartées** parce que le rejet hors-corpus s'effondre à 0,00. La
  métrique optimisée n'est pas l'objectif visé.
- **Aucun seuil ne résout le compromis.** Recalibré à 0,42, l'hybride
  retrouve un rejet de 1,00 mais perd le gain sur les paraphrases : le
  seuil qui filtre le hors-sujet filtre aussi les reformulations
  rattrapées.
- **Un mode d'échec documenté** : les requêtes reformulées plafonnent à
  0,350 de rappel, faute de recouvrement lexical. Cause identifiée,
  correctif quantifié, coût du correctif mesuré.

**Passage à l'échelle** — mesuré jusqu'à 20 000 chunks, deux régimes
(réaliste et adversarial). En régime réaliste la qualité tient
(Recall@4 ≈ 0,796) sous ~15 ms p50 : la recherche exacte creuse suffit
très au-delà du corpus actuel.

**Avant/après** ([`BENCHMARKS.md`](BENCHMARKS.md)) — l'injection
sélective fait passer le contexte de 2 663 tokens (déversement V1) à
96 tokens en moyenne, soit **−96,4 %**, mesuré par un harnais qui
reconstruit les deux prompts.

---

## Tests et couverture

**162 tests**, sans réseau ni clé API. La couverture est **délibérément
inégale**, et annoncée comme telle
([`reports/coverage_split.md`](reports/coverage_split.md), généré
depuis les données réelles — pas écrit à la main) :

| Sous-système | Instructions | Couverture |
|---|---|---|
| **Agent IA & RAG** (cœur du projet) | 1 460 | **94 %** |
| Logique métier (services, models, RBAC) | 733 | 78 % |
| Vues CRUD (Django classique) | 783 | 25 % |
| Divers (settings, URLs, serializers…) | 573 | 63 % |
| **Total — code applicatif** | **3 549** | **70 %** |

Les lignes **se somment exactement** au total : le poste « Divers »
existe pour qu'aucune instruction ne reste hors du décompte. Un chiffre
global unique survendrait la couche CRUD, testée surtout indirectement ;
l'effort est concentré là où se trouve la difficulté.

**Le dénominateur exclut les fichiers de tests eux-mêmes.** Du code de
test est exécuté par construction, donc couvert à ~99 % : le compter
ferait afficher 78 % sans qu'une ligne applicative soit mieux testée.
C'est pourquoi `coverage report`, `coverage_split.md` et les badges
ci-dessus annoncent tous **le même 70 %** — il n'existe pas deux mesures
concurrentes dans ce dépôt.

**Deux portes en CI**, et c'est la seconde qui compte : le global doit
rester ≥ 65 % (marge délibérée), et le sous-système **IA/RAG ≥ 90 %**
(`coverage_split --fail-under-ai=90`). La phrase « l'effort est
concentré sur la couche IA » n'est donc pas une affirmation de README :
c'est une porte qui casse le build si elle tombe.

```bash
# Suite complète (aucun prérequis réseau)
python manage.py test tests/

# Couverture + répartition par sous-système
coverage run --source='.' \
  --omit='*/migrations/*,tests/*,manage.py,config/wsgi.py,config/asgi.py,init_data.py,QUICKSTART.py' \
  manage.py test tests/
coverage report
python manage.py coverage_split --fail-under-ai=90   # → reports/coverage_split.md

# Évaluation du retrieval (gold set + 5 ablations + scaling)
python manage.py run_rag_eval         # → reports/rag_evaluation.md
python manage.py run_rag_eval --no-scaling    # version rapide

# Benchmark de l'agent (20 requêtes, déterministe)
python manage.py run_benchmarks       # → reports/benchmark_results_offline.json
```

---

## Installation

### Prérequis
- Python 3.11+ — PostgreSQL 14+ (ou SQLite en développement) — Redis (optionnel)
- Clé API Groq **facultative** (gratuite sur [console.groq.com](https://console.groq.com))

```bash
git clone https://github.com/malektlili-eng/fsb_system.git
cd fsb_system
python -m venv venv && source venv/bin/activate
pip install -r requirements/development.txt

cp .env.example .env          # renseigner SECRET_KEY ; GROQ_API_KEY facultative
python manage.py migrate
python manage.py init_data    # données de démonstration (idempotent)
python manage.py build_rag_index
python manage.py runserver    # → http://localhost:8000
```

Comptes de démonstration en local : `admin / admin123`,
`scolarite1 / scolarite123`, `chef_info / chef123`, `doyen / doyen123`.
Le mot de passe admin est surchargeable via `--admin-password` ou
`DEMO_ADMIN_PASSWORD`.

### Avec Docker

```bash
docker-compose up -d          # → http://localhost:8000
```

---

## Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                  Navigateur (Django Templates)                  │
│              SSE streaming ←→ REST API (/api/v1/)               │
└──────────────────────────┬─────────────────────────────────────┘
                           │
┌──────────────────────────▼─────────────────────────────────────┐
│                       Django Backend                            │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────────────┐ │
│  │  Views      │  │  REST API    │  │ Agent IA — Orchestrateur │ │
│  │ (Templates) │  │  (DRF)       │  │                          │ │
│  └─────────────┘  └──────────────┘  │  ┌────────────────────┐  │ │
│  ┌─────────────────────────────────┐│  │ RAG                │  │ │
│  │     Services Layer (RBAC)       ││  │  chunking →        │  │ │
│  └──────────────┬──────────────────┘│  │  embeddings →      │  │ │
│                 │                    │  │  vector store →    │  │ │
│                 │                    │  │  retriever (seuil) │  │ │
│                 │                    │  ├────────────────────┤  │ │
│                 │                    │  │ Tool Executor      │  │ │
│                 │                    │  │  (actions + RBAC)  │  │ │
│                 │                    │  ├────────────────────┤  │ │
│                 │                    │  │ LLM Provider       │  │ │
│                 │                    │  │  Groq ⇄ Offline    │  │ │
│                 │                    │  └────────────────────┘  │ │
│                 │                    └─────────────────────────┘ │
└─────────────────┼──────────────────────────────────────────────┘
                  │
    ┌─────────────┼──────────────┬──────────────────┐
┌───▼───┐  ┌──────▼──┐  ┌───────▼──────┐  ┌────────▼────────┐
│  DB   │  │  Redis  │  │  Groq API    │  │ Index vectoriel │
│  PG   │  │  Cache  │  │  LLaMA-3.3   │  │  (var/rag_index)│
└───────┘  └─────────┘  └──────────────┘  └─────────────────┘
```

**Deux voies d'accès à l'information, choisies explicitement** :

1. **Retrieval sémantique** pour la connaissance stable (règlements,
   procédures, FAQ) — avec citation des sources (`S1`, `S2`…).
2. **Tool calling sous RBAC** pour les données transactionnelles
   vivantes (étudiants, notes, plannings) : jamais indexées, jamais
   périmées, jamais servies sans vérification de rôle.

Justifications de conception : [`docs/RAG.md`](docs/RAG.md).

**Outils exposés** : `chercher_etudiant`, `creer_etudiant`,
`planifier_examen`, `obtenir_statistiques`, `notes_etudiant`,
`lister_filieres`.

```
"Comment se passe la session de rattrapage ?"              → RAG (règlement)
"Combien d'étudiants sont inscrits en L3 Informatique ?"   → outil + stats
"Crée un étudiant : Sarra Trabelsi, filière Licence Maths" → outil (RBAC)
"Quelle est la capitale du Japon ?"                        → rejeté (hors-corpus)
```

---

## Portée du domaine

La faculté est un **corpus de démonstration**, pas une contrainte
d'architecture. Le moteur RAG + agent est domaine-agnostique : pointer
`RAG_CORPUS_DIR` vers d'autres documents `.md` (support client, RH,
juridique…) suffit à le réutiliser sans changement de code — propriété
**vérifiée par un test** (`DomainPortabilityTest`). Impact quantifié :
[`IMPACT.md`](IMPACT.md).

---

## API REST

Documentation interactive : `/api/schema/swagger-ui/`

```bash
curl -H "Authorization: Bearer <token>" http://localhost:8000/api/etudiants/

curl -X POST http://localhost:8000/api/etudiants/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"nom": "BEN ALI", "prenom": "Mohamed", "filiere": 1}'
```

Endpoints : `/api/etudiants/`, `/api/etudiants/{id}/notes/`,
`/api/enseignants/`, `/api/inscriptions/`,
`/api/inscriptions/{id}/valider/`, `/api/filieres/`.

---

## Variables d'environnement

| Variable | Description | Défaut |
|---|---|---|
| `SECRET_KEY` | Clé secrète Django (**obligatoire**) | — |
| `DEBUG` | Mode debug | `False` |
| `DATABASE_URL` | URL de connexion à la base | SQLite |
| `REDIS_URL` | URL Redis pour le cache | — |
| `GROQ_API_KEY` | Clé API Groq (**facultative**, cf. repli) | — |
| `GROQ_MODEL` | Modèle de génération | `openai/gpt-oss-120b` |
| `LLM_PROVIDER` | `groq` ou `offline` | `groq` |
| `LLM_FALLBACK_OFFLINE` | Repli déterministe si Groq indisponible | `True` |
| `RAG_EMBEDDING_BACKEND` | `tfidf`, `spacy`, `hybrid`, `sentence-transformers` | `tfidf` |
| `RAG_CORPUS_DIR` | Dossier du corpus (vide = corpus FSB) | — |
| `DEMO_ADMIN_PASSWORD` | Mot de passe du compte de démonstration | `admin123` |
| `ALLOWED_HOSTS` | Hôtes autorisés (virgule-séparés) | `localhost` |

---

## Structure

```
fsb_system/
├── apps/
│   ├── accounts/        # Auth, rôles RBAC
│   ├── administration/  # Étudiants, enseignants, filières
│   │   ├── api/         # ViewSets + Serializers DRF
│   │   ├── services.py  # Logique métier
│   │   └── management/commands/init_data.py   # Seeding idempotent
│   ├── pedagogie/       # Notes, absences, emplois du temps
│   ├── examens/         # Sessions et plannings
│   ├── stages/          # Stages et diplômes
│   └── ai_agent/
│       ├── orchestrator.py     # RAG + tool calling + streaming
│       ├── views.py            # SSE
│       ├── llm/providers.py    # Groq (prod) / Offline (déterministe)
│       ├── rag/
│       │   ├── chunking.py     # Découpage phrase-aligné
│       │   ├── embeddings.py   # TF-IDF creux / spaCy / hybride
│       │   ├── vector_store.py # Index cosinus + persistance
│       │   ├── retriever.py    # Ranking hybride + seuil
│       │   └── corpus/         # Documents institutionnels (.md)
│       ├── evaluation/         # Gold set, métriques IR, ablations, scaling
│       ├── benchmarks/         # 20 requêtes + harnais offline/live
│       └── management/commands/
├── core/permissions.py  # RBAC centralisé
├── config/settings/     # base / development / production
├── tests/               # 162 tests
├── reports/             # Couverture, évaluation RAG, benchmarks
├── docs/RAG.md          # Conception et justifications du RAG
├── BENCHMARKS.md        # Qualité, latence, comparaison V1 vs V2
├── IMPACT.md            # Portabilité de domaine, impact quantifié
├── DEPLOYMENT.md        # Render / Procfile / Docker
└── .github/workflows/   # CI/CD
```

---

## Auteur

**Malek Tlili** — architecture, agent IA, pipeline RAG, évaluation, CI/CD.

---

## Licence

MIT — voir [LICENSE](LICENSE).

---

*Projet issu d'un stage universitaire à la Faculté des Sciences de
Bizerte, repris et étendu en projet personnel.*
