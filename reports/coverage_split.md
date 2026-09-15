# Couverture de tests — répartition par sous-système

*Généré par `python manage.py coverage_split` à partir des données de couverture réelles — jamais écrit à la main.*

Un chiffre global unique serait trompeur : l'effort de test est délibérément concentré sur la couche IA/RAG (le cœur du projet), pas réparti uniformément. Voici la répartition, réconciliée.

| Sous-système | Instructions | Couvertes | Couverture |
|---|---|---|---|
| **Agent IA & RAG** | 1460 | 1367 | **94 %** |
| **Logique métier (services, forms, models)** | 733 | 572 | **78 %** |
| **Vues CRUD (legacy)** | 783 | 196 | **25 %** |
| _Divers (settings, URLs, apps.py, serializers…)_ | 573 | 361 | _63 %_ |
| **Total — code applicatif** | **3549** | **2496** | **70 %** |

## Ce que ce total mesure exactement

**70 % du code applicatif** (2496 / 3549 instructions). Les lignes du tableau se somment exactement à ce total : le poste « Divers » existe précisément pour qu'aucune instruction ne reste hors du décompte.

Ce chiffre est **le même** que celui de `coverage report` et des badges du README. Il n'existe pas deux mesures concurrentes de la couverture dans ce dépôt.

**Deux exclusions, toutes deux volontaires :**

- *Les migrations* — code généré par Django, pas écrit ici.
- *Les fichiers de tests eux-mêmes*, écartés via `--omit` dès la collecte. Du code de test est exécuté par construction, donc couvert à ~99 % : le compter gonflerait le total de plusieurs points sans qu'une seule ligne de code applicatif soit mieux testée. C'est une erreur de mesure courante, et elle a été commise dans une version antérieure de ce dépôt — d'où cette note.

## Lecture

- **Agent IA & RAG — 94 %** : Cœur du projet : chunking, embeddings, index, retrieval, évaluation, orchestrateur.
- **Logique métier (services, forms, models) — 78 %** : Règles métier, seeding et permissions RBAC.
- **Vues CRUD (legacy) — 25 %** : Écrans Django classiques, testés indirectement. Couverture assumée comme plus faible : priorité donnée à la couche IA/RAG.
- **Divers (settings, URLs, apps.py, serializers…) — 63 %** : Câblage et configuration. Présent pour que les lignes ci-dessus se somment exactement au total : aucune instruction applicative n'est laissée hors du tableau.

## Détail par fichier

### Agent IA & RAG

| Fichier | Instr. | Manquantes | % |
|---|---|---|---|
| `apps/ai_agent/benchmarks/__init__.py` | 0 | 0 | 100 % |
| `apps/ai_agent/benchmarks/harness.py` | 71 | 1 | 99 % |
| `apps/ai_agent/benchmarks/queries.py` | 1 | 0 | 100 % |
| `apps/ai_agent/evaluation/__init__.py` | 0 | 0 | 100 % |
| `apps/ai_agent/evaluation/gold_set.py` | 9 | 0 | 100 % |
| `apps/ai_agent/evaluation/metrics.py` | 33 | 5 | 85 % |
| `apps/ai_agent/evaluation/runner.py` | 136 | 1 | 99 % |
| `apps/ai_agent/evaluation/scaling.py` | 105 | 2 | 98 % |
| `apps/ai_agent/llm/__init__.py` | 0 | 0 | 100 % |
| `apps/ai_agent/llm/providers.py` | 138 | 4 | 97 % |
| `apps/ai_agent/management/__init__.py` | 0 | 0 | 100 % |
| `apps/ai_agent/management/commands/__init__.py` | 0 | 0 | 100 % |
| `apps/ai_agent/management/commands/build_rag_index.py` | 12 | 0 | 100 % |
| `apps/ai_agent/management/commands/coverage_split.py` | 123 | 8 | 93 % |
| `apps/ai_agent/management/commands/run_benchmarks.py` | 26 | 2 | 92 % |
| `apps/ai_agent/management/commands/run_rag_eval.py` | 11 | 0 | 100 % |
| `apps/ai_agent/models.py` | 55 | 6 | 89 % |
| `apps/ai_agent/orchestrator.py` | 199 | 22 | 89 % |
| `apps/ai_agent/rag/__init__.py` | 0 | 0 | 100 % |
| `apps/ai_agent/rag/chunking.py` | 98 | 2 | 98 % |
| `apps/ai_agent/rag/embeddings.py` | 130 | 9 | 93 % |
| `apps/ai_agent/rag/knowledge.py` | 50 | 8 | 84 % |
| `apps/ai_agent/rag/retriever.py` | 96 | 5 | 95 % |
| `apps/ai_agent/rag/vector_store.py` | 85 | 3 | 96 % |
| `apps/ai_agent/views.py` | 82 | 15 | 82 % |

### Logique métier (services, forms, models)

| Fichier | Instr. | Manquantes | % |
|---|---|---|---|
| `apps/administration/forms.py` | 95 | 32 | 66 % |
| `apps/administration/management/__init__.py` | 0 | 0 | 100 % |
| `apps/administration/management/commands/__init__.py` | 0 | 0 | 100 % |
| `apps/administration/models.py` | 126 | 8 | 94 % |
| `apps/administration/services.py` | 109 | 43 | 61 % |
| `apps/examens/models.py` | 54 | 12 | 78 % |
| `apps/pedagogie/models.py` | 87 | 6 | 93 % |
| `apps/pedagogie/services.py` | 175 | 46 | 74 % |
| `apps/stages/models.py` | 38 | 2 | 95 % |
| `core/__init__.py` | 0 | 0 | 100 % |
| `core/permissions.py` | 49 | 12 | 76 % |

### Vues CRUD (legacy)

| Fichier | Instr. | Manquantes | % |
|---|---|---|---|
| `apps/administration/views.py` | 257 | 175 | 32 % |
| `apps/examens/views.py` | 82 | 62 | 24 % |
| `apps/pedagogie/views.py` | 300 | 237 | 21 % |
| `apps/stages/views.py` | 144 | 113 | 22 % |

### Divers (settings, URLs, apps.py, serializers…)

| Fichier | Instr. | Manquantes | % |
|---|---|---|---|
| `apps/__init__.py` | 0 | 0 | 100 % |
| `apps/accounts/__init__.py` | 0 | 0 | 100 % |
| `apps/accounts/apps.py` | 5 | 0 | 100 % |
| `apps/accounts/models.py` | 21 | 5 | 76 % |
| `apps/accounts/urls.py` | 5 | 0 | 100 % |
| `apps/accounts/views.py` | 66 | 50 | 24 % |
| `apps/administration/__init__.py` | 0 | 0 | 100 % |
| `apps/administration/admin.py` | 74 | 5 | 93 % |
| `apps/administration/api/__init__.py` | 0 | 0 | 100 % |
| `apps/administration/api/serializers.py` | 72 | 15 | 79 % |
| `apps/administration/api/urls.py` | 11 | 0 | 100 % |
| `apps/administration/api/views.py` | 108 | 48 | 56 % |
| `apps/administration/apps.py` | 5 | 0 | 100 % |
| `apps/administration/urls.py` | 4 | 0 | 100 % |
| `apps/ai_agent/__init__.py` | 0 | 0 | 100 % |
| `apps/ai_agent/apps.py` | 5 | 0 | 100 % |
| `apps/ai_agent/urls.py` | 4 | 0 | 100 % |
| `apps/examens/__init__.py` | 0 | 0 | 100 % |
| `apps/examens/apps.py` | 5 | 0 | 100 % |
| `apps/examens/urls.py` | 6 | 0 | 100 % |
| `apps/pedagogie/__init__.py` | 0 | 0 | 100 % |
| `apps/pedagogie/api/__init__.py` | 0 | 0 | 100 % |
| `apps/pedagogie/api/serializers.py` | 27 | 27 | 0 % |
| `apps/pedagogie/apps.py` | 5 | 0 | 100 % |
| `apps/pedagogie/templatetags/__init__.py` | 0 | 0 | 100 % |
| `apps/pedagogie/templatetags/pedagogie_extras.py` | 47 | 29 | 38 % |
| `apps/pedagogie/urls.py` | 4 | 0 | 100 % |
| `apps/stages/__init__.py` | 0 | 0 | 100 % |
| `apps/stages/apps.py` | 5 | 0 | 100 % |
| `apps/stages/urls.py` | 4 | 0 | 100 % |
| `config/__init__.py` | 0 | 0 | 100 % |
| `config/settings/__init__.py` | 0 | 0 | 100 % |
| `config/settings/base.py` | 40 | 0 | 100 % |
| `config/settings/development.py` | 10 | 0 | 100 % |
| `config/settings/production.py` | 28 | 28 | 0 % |
| `config/urls.py` | 12 | 5 | 58 % |

