# CHANGELOG

## V2.4 → V2.5 (réconciliation de la couverture)

### Le 71 % / 78 % : trois chiffres pour une même notion

`coverage_split.md` affichait **71 %** en bas de tableau pendant que le
README et les badges annonçaient **78 %**, sans qu'aucun document
n'explique l'écart. Un relecteur qui ouvre les deux fichiers le voit en
quelques secondes — sur un projet dont l'argument est la rigueur de
mesure, c'est une faille sérieuse.

Diagnostic : **trois** mesures circulaient en réalité.

| Chiffre | Ce qu'il mesurait |
|---|---|
| 78 % | total brut de `coverage report`, **fichiers de tests inclus** |
| 71 % | somme des seuls sous-systèmes nommés du split |
| 70 % | code applicatif réel — jamais affiché nulle part |

Deux causes distinctes, corrigées séparément.

**1. Les fichiers de tests gonflaient le dénominateur.** 1 293
instructions couvertes à 99,1 % — du code de test est exécuté par
construction. Les compter faisait afficher 78 % sans qu'une seule ligne
applicative soit mieux testée. `tests/*` est désormais exclu dès la
collecte, dans la CI comme dans le README.

**2. Le tableau ne se réconciliait pas.** Les sous-systèmes nommés
laissaient 573 instructions hors décompte (settings, URLs, `apps.py`,
serializers). Ajout d'un poste résiduel explicite : les lignes se
somment maintenant **exactement** au total.

Résultat : `coverage report`, `coverage_split.md` et les badges
annoncent tous **le même 70 %**. Il n'existe plus deux mesures
concurrentes dans le dépôt. La section « Ce que ce total mesure
exactement » explicite les deux exclusions.

### Portes de couverture repensées

La porte était à `--fail-under=70` pour un total réel de 70,3 % : marge
de 0,3 point, donc CI rouge au premier ajout de code non testé — le
défaut même corrigé deux fois dans la révision précédente.

- Porte **globale à 65 %** : marge délibérée, assumée comme telle.
- Porte **IA/RAG à 90 %** (`coverage_split --fail-under-ai`), nouvelle.
  C'est elle qui porte le sens : la phrase « l'effort de test est
  concentré sur la couche IA/RAG » cesse d'être une affirmation de
  README pour devenir une porte qui casse le build. Testée dans les
  deux sens, franchie et non franchie.

### Tests ajoutés (160 → 162)

- `test_le_tableau_se_reconcilie_exactement` — vérifie que la somme des
  sous-systèmes égale la ligne de total. Empêche le retour exact du
  défaut 71/78.
- `test_porte_ia_rag_casse_le_build_si_non_franchie`.

### Report de l'URL de démonstration

Ajout de `set_demo_url.py` : propage l'URL réelle dans `README.md` et
`DEPLOYMENT.md` en une commande, valide le format, et affiche l'état
courant sans argument. Reporter l'URL à la main dans plusieurs fichiers,
c'est en oublier un et laisser une adresse morte.

---

## V2.3 → V2.4 (repositionnement : « présente-le comme ton projet d'ingénierie »)

Cette révision applique un **renversement de cadrage**. FSB cessait
d'être défendable comme projet de recherche dès lors qu'un second
projet (Vector RAG vs Graph RAG, en laboratoire) couvrait le même
terrain avec un corpus de 475 abstracts. Lu après lui, l'évaluation de
FSB (34 chunks, 6 documents, interne à une faculté) se lisait comme une
version réduite du même travail.

FSB est donc désormais présenté pour ce qu'il démontre **seul** :
Django de production, CI/CD contraignante, tool calling, streaming SSE,
et surtout l'abstraction `OfflineProvider` qui rend un pipeline LLM
testable sans réseau ni clé. Les deux projets forment une trajectoire
— livrer un système de retrieval, puis aller interroger l'architecture
en laboratoire — au lieu de se répéter.

### Fusion des trois versions livrées

Comparaison exhaustive de `v2.1`, `v2.2` et `v2.3` : arborescences,
signatures de toutes les fonctions et classes `.py`, sections de
documentation. **Aucune régression détectée** — chaque version est un
sur-ensemble strict de la précédente. Aucune récupération n'a donc été
nécessaire depuis les versions antérieures ; `v2.3` sert de base.

### Défauts bloquants corrigés

- **`requirements/base.txt` était cassé** : il listait `crispy-forms`,
  qui n'existe pas sur PyPI (le paquet est `django-crispy-forms`).
  `pip install -r` échouait à la première commande.
- **`LICENSE` absent** alors que le README l'affichait en badge et le
  liait. Ajouté (MIT).
- **`python manage.py init_data` était documenté mais n'existait pas** :
  la logique vivait dans un script racine invoqué via `shell <`. Portée
  en **commande de gestion** idempotente
  (`apps/administration/management/commands/init_data.py`), avec mot de
  passe paramétrable (`--admin-password` / `DEMO_ADMIN_PASSWORD`). Le
  script racine devient un shim de compatibilité.
- **13 erreurs `F821`** (`undefined name`) dans les couches service :
  des annotations de retour en chaîne référençant des modèles importés
  paresseusement. La porte `flake8 --select=E9,F63,F7,F82` de la CI est
  bloquante : **le badge aurait été rouge dès le premier push**.
  Corrigées par `from __future__ import annotations` + bloc
  `TYPE_CHECKING`, sans casser les imports paresseux.
- **La passe de style flake8 était bloquante** malgré son libellé
  « avertissements », et échouait sur 510 remarques. Alignée sur son
  intention avec `--exit-zero`.

### Déploiement — priorité n°1 de cette révision

- **Le blueprint ne semait aucune donnée.** Le README promettait des
  identifiants de démonstration, mais rien ne créait de compte : l'URL
  aurait mené à un formulaire de connexion inutilisable. `render.yaml`
  et `Procfile` enchaînent désormais `migrate` → `init_data` →
  `build_rag_index`. Séquence vérifiée sur base vierge : 52 chunks
  indexés, dont 18 fiches d'entités que l'ancien ordre manquait.
- **La démo cassait sans clé Groq.** `get_provider()` instanciait
  `GroqProvider()` sans condition. Ajout de `groq_is_usable()` et du
  réglage `LLM_FALLBACK_OFFLINE` : sans secret, la génération bascule
  sur `OfflineProvider` et le retrieval, la sélection d'outils, le RBAC
  et le streaming SSE restent tous observables. Couvert par 4 nouveaux
  tests, dont le refus explicite de replier quand le réglage est à
  `False`.
- Mot de passe de démonstration **généré par la plateforme**
  (`generateValue`) : une instance publique ne doit pas exposer un mot
  de passe inscrit en clair dans le dépôt.
- Bouton « Deploy to Render » et limites des offres gratuites
  (mise en veille ~15 min, expiration des bases à 30 jours) documentées
  dans `DEPLOYMENT.md`.

### Testabilité — la promesse rendue vraie

La suite revendiquait « testable sans réseau ni clé API », mais **4
tests échouaient si le paquet `groq` était absent**, précisément là où
l'argument est censé tenir. Ajout de `tests/support.py` et du
décorateur `requires_groq_sdk`. Vérifié par désinstallation effective
du SDK : **160 tests, 0 échec sans lui, 0 skip avec**.

### Rigueur des rapports

- **La ligne « NON EXÉCUTÉ » a été sortie du tableau d'ablations.** A4
  *est* exécutée, mais cette ligne recréait exactement le défaut de
  lecture signalé. `run_ablations()` retourne désormais les variantes
  indisponibles séparément ; le rapport affiche un état explicite
  (« A4 : exécutée — 4 configurations mesurées ») et renvoie la variante
  manquante en note.
- **Dérive de chiffres corrigée** : `BENCHMARKS.md` annonçait 98 tokens
  et −96,3 % ; la mesure régénérée donne 96 et −96,4 %. Propagé dans
  `IMPACT.md` et `CHANGELOG.md`.
- Tous les rapports (`coverage.xml`, `coverage_summary.txt`,
  `coverage_split.md`, `rag_evaluation.md/json`,
  `benchmark_results_offline.json`) régénérés depuis le code corrigé.
- Chiffres A4 **revalidés par réexécution** après installation de spaCy
  + `fr_core_news_md` : reproduction à l'identique.

---

## V2.2 → V2.3 (seconde revue : « corpus scale unproven, A4 unexecuted »)

### Critique — « Ablation A4 est non exécutée. C'est la seule chose qui se lit comme inachevée »

**Corrigé — A4 est désormais exécutée avec de vrais chiffres.** Les
poids HuggingFace n'étant pas accessibles depuis l'environnement de
build, un backend sémantique **pré-entraîné alternatif** a été
implémenté : `SpacyVectorBackend` (vecteurs FR `fr_core_news_md`,
300 dims, pooling pondéré par IDF), installable par pip, plus un
`HybridDenseSparseBackend`. Résultat mesuré :

| Config | Recall@4 | MRR | Rejet | reformulée R@4 |
|---|---|---|---|---|
| TF-IDF (défaut) | 0,759 | 0,778 | **0,67** | 0,350 |
| Hybride @ 0,20 | **0,833** | **0,815** | 0,00 | **0,550** |
| Hybride @ 0,42 | 0,759 | 0,759 | **1,00** | 0,350 |

L'hybride **résout** la limite sur les paraphrases (0,350 → 0,550) et
bat le défaut sur le rang — mais détruit le rejet hors-corpus, et le
seuil qui restaure le rejet annule le gain. **Aucun seuil ne donne les
deux** : même structure de résultat qu'A5, mesurée et documentée.
La CI installe le backend pour qu'A4 s'exécute réellement à chaque push.

### Critique — « Corpus scale is unproven. Le retriever tient-il à 10 000 chunks ? »

**Corrigé — mesuré jusqu'à 20 000 chunks**, sur deux régimes
(`apps/ai_agent/evaluation/scaling.py`) :

- **Réaliste** (documents d'autres sujets) : la qualité **tient**
  (Recall@4 0,796 de 500 à 20 000 chunks), p50 = 14,6 ms à 20 000,
  index = 33 Mo.
- **Adversarial** (recombinaison markovienne du corpus) : dégradation
  jusqu'à 0,148 — borne inférieure pessimiste assumée, car ces
  distracteurs contiennent des phrases réellement pertinentes non
  annotées.

**Bug réel trouvé grâce à cette mesure** : `TfidfBackend` densifiait ses
vecteurs (`.toarray()`), ce qui provoquait un **OOM à 20 000 chunks**
(~1,2 Go). Le vector store est désormais **creux** (scipy CSR) : même
index en 33 Mo. Le choix « recherche exacte plutôt que FAISS » est
maintenant justifié par la mesure, pas par une supposition.

### Critique — « Precision@4 de 0.259 est mauvais et vous ne l'affrontez pas »

**Corrigé — affronté et quantifié.** Le rapport contient désormais une
section dédiée : 20 des 27 requêtes annotées n'ont **qu'un seul** chunk
pertinent, donc avec k = 4 un système **parfait** plafonnerait à
**0,343**. Nous atteignons 0,259, soit **75,5 % du plafond
atteignable**. Precision@4 est un artefact de plafond sur ce gold set ;
MRR (0,778) et nDCG@4 (0,763) portent le signal réel. Le plafond est
**calculé automatiquement** (`precision_ceiling()`), pas affirmé.

### Critique — « Couverture 74 % mais inégalement répartie ; le chiffre global survend la couche CRUD »

**Corrigé — répartition publiée ET plancher relevé.**

- Nouvelle commande `python manage.py coverage_split` qui **génère**
  `reports/coverage_split.md` depuis les données de couverture réelles
  (pas un tableau écrit à la main qui périmerait).
- La répartition est affichée en tête de README, avec deux badges
  distincts (IA/RAG **94 %**, global **78 %**) au lieu d'un chiffre
  unique trompeur.
- Le plancher a aussi été **relevé** : ajout de tests directs du
  `ToolExecutor` (création d'étudiant, statistiques, notes, RBAC) →
  orchestrateur 75 % → **89 %**, IA/RAG 86 % → **94 %**.
- Total : **157 tests** (contre 137).

### Critique — « Pas d'URL live »

**Non résolu.** L'infrastructure est complète (`render.yaml`, `Procfile`,
WhiteNoise, `check --deploy` vérifié en CI) mais l'URL du README reste
un **placeholder** : provisionner un serveur nécessite une action du
propriétaire du dépôt (connexion à Render + clé Groq). Voir
[`DEPLOYMENT.md`](DEPLOYMENT.md).

---

# V2 → V2.1 (première revue)

Cette version répond point par point aux critiques de la revue. Chaque
correction est **vérifiable** (code + tests + rapports générés).

---

## Critique 1 — « Pas de preuve de recherche par similarité vectorielle, ni de stratégie de chunking/embedding : c'est du RAG au sens large »

**Corrigé.** Un vrai sous-système RAG a été implémenté dans
`apps/ai_agent/rag/` :

- **Chunking** (`chunking.py`) : découpage aligné sur les phrases,
  fenêtre glissante ~450 caractères, chevauchement d'une phrase,
  préfixe de section embarqué dans le vecteur. Justifié par ablation.
- **Embeddings** (`embeddings.py`) : couche **possédée** et pluggable —
  TF-IDF n-grammes de caractères par défaut (reproductible, sans
  téléchargement), `sentence-transformers` en option. C'est la réponse
  à « vous ne possédez aucune couche modèle » : la génération reste
  déléguée, mais le **retrieval** est implémenté ici.
- **Vector store** (`vector_store.py`) : recherche **cosinus** exacte
  (numpy), persistance disque. Choix documenté vs FAISS/pgvector.
- **Retriever** (`retriever.py`) : score **hybride** (dense + lexical)
  et **seuil de pertinence** calibré — le vrai mécanisme du « RAG
  sélectif ».

→ Détails et justifications : [`docs/RAG.md`](docs/RAG.md).

## Critique 2 — « L'architecture montre des requêtes DB directes, pas du RAG »

**Clarifié et assumé comme choix de conception.** Le système combine
**deux** voies, séparées explicitement (voir `docs/RAG.md` §1) :

- **RAG sémantique** pour la connaissance stable (règlements,
  procédures, FAQ, fiches d'entités) — recherche par similarité.
- **Tool calling + RBAC** pour les données transactionnelles vivantes
  (notes, étudiants) — jamais indexées (sinon index périmé + RBAC
  contourné).

Ce n'est pas une faiblesse mais la bonne séparation ; elle est
désormais documentée et mesurée.

## Critique 3 — « `orchestrator.py` n'est pas évalué contre de vraies requêtes »

**Corrigé.**

- **`BENCHMARKS.md`** : 20 requêtes représentatives (connaissance,
  action, statistiques, limites) passées dans l'orchestrateur complet,
  avec latences et vérification automatique du comportement attendu.
- **Comparaison avant/après V1 vs V2** : réduction de contexte
  **mesurée** de ~96 % (2 663 → ~96 tokens injectés par requête).
- Rapport machine : `reports/benchmark_results_offline.json`.

## Critique 4 — « Pas de benchmarks, pas d'ablations, pas de "avant/après IA" »

**Corrigé.**

- **Évaluation IR** (`reports/rag_evaluation.md`) : gold set de
  **30 requêtes annotées**, métriques Recall@k / Precision@k / MRR /
  nDCG et taux de rejet hors-corpus.
- **5 ablations** : taille de chunk (A1), chevauchement (A2), poids
  lexical (A3), backend d'embeddings (A4), et un **résultat négatif
  documenté** sur LSA/SVD (A5).
- **Avant/après** : la section 3 de `BENCHMARKS.md` compare V1
  (contexte complet déversé) et V2 (RAG sélectif).

## Critique 5 — « Le CI annonce 60 % de couverture mais il n'y a aucun test dans le zip »

**Corrigé.**

- Le zip contient désormais **115 tests** (contre 51), dont des tests
  de bout en bout de l'orchestrateur (RAG + tool calling via un
  fournisseur LLM déterministe, **sans réseau ni mock fragile**).
- Couverture **réellement exercée : 74 %** (modules IA : 74–100 %).
- La porte CI est passée de `--min-coverage=60` (option **invalide**,
  qui ne bloquait rien) à `coverage report --fail-under=70` (correcte).
- Rapports versionnés : `reports/coverage_summary.txt`,
  `reports/coverage.xml`, `reports/htmlcov/`.

## Critique 6 — « Ajouter : rapport de couverture, log d'évaluation RAG, URL de déploiement »

**Corrigé.**

- **Rapport de couverture** : `reports/coverage_summary.txt` (+ HTML/XML).
- **Log d'évaluation RAG** : `reports/rag_evaluation.md` et `.json`,
  régénérables par `python manage.py run_rag_eval`.
- **Déploiement** : configuration prête (`render.yaml`, `Procfile`,
  WhiteNoise, `check --deploy` vérifié en CI) et instructions dans
  [`DEPLOYMENT.md`](DEPLOYMENT.md). L'URL live reste un **placeholder** à
  renseigner après déploiement (impossible à provisionner depuis le
  dépôt seul), mais tout le nécessaire est fourni pour un déploiement
  en un clic.

---

## Critique — « Le projet est domaine-interne (gestion de faculté), ce qui limite l'impact perçu »

**Adressé.** La faculté est désormais présentée comme un **corpus de
démonstration**, pas une contrainte d'architecture :

- Le moteur RAG est rendu **domaine-agnostique** : la variable
  `RAG_CORPUS_DIR` permet de pointer le corpus vers n'importe quel
  dossier de `.md` (support client, RH, juridique…) **sans changement
  de code**.
- Cette portabilité est **prouvée par un test automatisé**
  (`tests/test_rag_retrieval.py::DomainPortabilityTest`) qui indexe un
  corpus de support e-commerce et vérifie retrieval + rejet hors-domaine.
- [`IMPACT.md`](IMPACT.md) documente la valeur transférable (~90 % du
  code indépendant du domaine), l'impact quantifié et les chemins de
  généralisation (support client, conformité, RH).

---

## Nouvelles commandes de gestion

```bash
python manage.py build_rag_index    # construit / persiste l'index vectoriel
python manage.py run_rag_eval       # évalue le retrieval (gold set + ablations)
python manage.py run_benchmarks     # benchmark de l'agent (offline déterministe)
python manage.py run_benchmarks --live   # idem avec le vrai LLM (GROQ_API_KEY)
```

## Nouvelles variables d'environnement

| Variable | Rôle | Défaut |
|---|---|---|
| `LLM_PROVIDER` | `groq` (prod) ou `offline` (tests/CI) | `groq` |
| `RAG_EMBEDDING_BACKEND` | `tfidf` ou `sentence-transformers` | `tfidf` |

## Migration de base de données

`apps/ai_agent/migrations/0002_*` ajoute la télémétrie RAG au modèle
`AgentMetric` (`rag_chunks`, `rag_top_score`, `retrieval_ms`).
