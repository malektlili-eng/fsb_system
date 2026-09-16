# Architecture RAG — conception et justifications

Ce document décrit le sous-système de *Retrieval-Augmented Generation*
de l'agent FSB : ce qui est indexé, comment le corpus est découpé et
vectorisé, comment les passages sont retrouvés et filtrés, et
**pourquoi** chaque choix a été fait. Il répond directement à la
question « est-ce un vrai RAG ou juste des requêtes SQL déguisées ? ».

Les affirmations de performance de ce document sont **mesurées** par
`python manage.py run_rag_eval` (voir
[`reports/rag_evaluation.md`](../reports/rag_evaluation.md)).

---

## 1. RAG vs Tool Calling : deux voies, une décision explicite

L'agent combine **deux** mécanismes d'accès à l'information, et le
choix entre les deux est un choix de conception assumé :

| | Retrieval sémantique (RAG) | Tool Calling (BD) |
|---|---|---|
| Sert quoi | connaissance **stable** : règlements, procédures, FAQ, fiches d'entités | données **transactionnelles vivantes** : notes, absences, étudiants, plannings |
| Fraîcheur | corpus versionné, réindexé à la demande | temps réel, lu à chaque requête |
| Contrôle d'accès | contenu public/institutionnel | **RBAC par rôle**, vérifié avant chaque appel |
| Risque si on inverse | indexer les notes → index périmé dès la 1ʳᵉ saisie + contournement du RBAC | interroger le règlement par SQL → pas de recherche par similarité |

> **Pourquoi ne pas tout mettre dans le RAG ?** Indexer les données
> transactionnelles créerait un index obsolète en permanence et, plus
> grave, court-circuiterait le contrôle d'accès par rôle. Les notes
> d'un étudiant ne doivent pas « fuiter » via une recherche
> vectorielle non filtrée. Elles restent donc servies par des outils
> soumis aux permissions (`ToolExecutor.TOOL_PERMISSIONS`).

> **Pourquoi ne pas tout mettre dans les outils ?** C'était la
> faiblesse de la V1 : « comment se passe le rattrapage ? » n'a pas de
> requête SQL naturelle. Le RAG répond par **similarité sémantique**
> sur le texte du règlement, avec citation de la source.

C'est cette séparation — et non un simple appel LLM — qui fait du
système un vrai pipeline RAG.

---

## 2. Le corpus indexé

Deux sources alimentent l'index (`apps/ai_agent/rag/knowledge.py`) :

1. **Documents institutionnels** (`rag/corpus/*.md`) : règlement des
   études, procédures d'inscription, stages et diplômes, organisation
   des examens, rôles et permissions, FAQ scolarité. Connaissance
   stable, rédigée en Markdown structuré (titres = sections).

2. **Fiches d'entités** (base de données) : filières, départements,
   salles — entités peu volatiles dont la description textuelle permet
   de répondre par similarité (« quelles filières de niveau L3 ? »).
   Chaque entité devient une « fiche » d'un chunk via
   `serialize_record()`.

Ce **ne sont pas** indexées : les entités transactionnelles (étudiants
individuels, notes, absences), pour les raisons du §1.

---

## 3. Stratégie de chunking

Implémentation : `apps/ai_agent/rag/chunking.py`.

### 3.1 Fenêtre glissante alignée sur les phrases

Le texte est d'abord segmenté en **phrases** (heuristique adaptée au
français : ponctuation forte suivie d'une majuscule/chiffre), puis les
phrases sont regroupées en fenêtres d'environ **450 caractères
(~110 tokens)**. On ne coupe **jamais** au milieu d'une phrase : chaque
chunk reste sémantiquement cohérent.

**Pourquoi 450 caractères ?** Compromis mesuré (ablation A1) : trop
petit (300) fragmente les réponses sur plusieurs chunks et fait chuter
le rappel ; trop grand (900) dilue le signal et dégrade la précision.
450 offre le meilleur nDCG sur le gold set.

### 3.2 Chevauchement d'une phrase

Deux chunks consécutifs partagent leur phrase de jointure. **Pourquoi ?**
Un fait à cheval sur une frontière de chunk (« … dans un délai de
48 heures. Les justificatifs recevables sont… ») reste retrouvable
quelle que soit la fenêtre qui capte la requête. L'ablation A2 confirme
un gain de rappel du chevauchement.

### 3.3 Préfixe de section embarqué

Chaque chunk est préfixé, **dans le texte embarqué**, par son chemin de
section : `[Règlement des études > Article 4 — Régime des absences]`.
**Pourquoi ?** Beaucoup de requêtes nomment la procédure (« régime des
absences ») plutôt que son contenu. Embarquer le titre dans le vecteur
améliore nettement le rappel sur ces requêtes, sans coût.

---

## 4. Embeddings : une couche modèle *possédée* et pluggable

Implémentation : `apps/ai_agent/rag/embeddings.py`.

C'est ici la réponse à « le LLM est entièrement délégué à Groq, vous ne
possédez aucune couche modèle ». La **génération** est effectivement un
composant interchangeable (Groq par défaut, cf. §7), mais la couche de
**retrieval** — embeddings, index, ranking, seuil, évaluation — est
implémentée et maîtrisée dans ce dépôt.

Deux backends, même interface `EmbeddingBackend` :

### 4.1 TF-IDF n-grammes de caractères (défaut)

`char_wb`, n-grammes 3-5, TF-IDF sublinéaire, vecteurs L2-normalisés.

**Pourquoi ce choix par défaut ?**
- **Robuste à la morphologie française** : *inscrit / inscription /
  inscrire* partagent leurs n-grammes de caractères ; un embedding par
  mots entiers les traiterait comme distincts.
- **Robuste aux fautes de frappe** (n-grammes de sous-chaînes).
- **100 % reproductible en CI** : aucun téléchargement de modèle,
  aucune dépendance réseau, résultats déterministes.

Sorties **creuses** (scipy CSR) : c'est ce qui permet à l'index de
tenir à 20 000 chunks (voir §5.1). Le résultat négatif sur la
projection LSA est traité en §4.3.

### 4.2 Backends sémantiques (ablation A4 — exécutée)

Deux backends sémantiques sont implémentés et **réellement évalués** :

- **`SpacyVectorBackend`** — vecteurs de mots français pré-entraînés
  (`fr_core_news_md`, 300 dims), mis en commun par moyenne **pondérée
  par l'IDF** du corpus (la moyenne simple laisse les mots-outils
  dominer). Les poids s'installent par pip depuis GitHub Releases : pas
  de dépendance à un téléchargement HuggingFace.
- **`HybridDenseSparseBackend`** — concaténation pondérée du dense
  sémantique et du lexical TF-IDF : le dense rattrape les
  reformulations, le lexical garde la précision sur les termes exacts.
- **`SentenceTransformerBackend`** — MiniLM multilingue, si les poids
  sont accessibles.

**Ce que l'ablation A4 mesure** (chiffres complets dans
`reports/rag_evaluation.md`) :

| Config | Recall@4 | MRR | Rejet | reformulée R@4 |
|---|---|---|---|---|
| TF-IDF (défaut) | 0,759 | 0,778 | **0,67** | 0,350 |
| Hybride @ seuil 0,20 | **0,833** | **0,815** | 0,00 | **0,550** |
| Hybride @ seuil 0,42 | 0,759 | 0,759 | **1,00** | 0,350 |

**Le résultat est un vrai compromis, pas une amélioration.** L'hybride
résout bien la limite identifiée : les requêtes *reformulées* passent de
0,350 à 0,550, et il bat le défaut sur toutes les métriques de rang.
Mais son rejet hors-corpus tombe à **zéro** : dans l'espace dense, les
scores des requêtes hors-corpus **chevauchent** ceux des requêtes
couvertes (ce n'est pas un simple décalage d'échelle — mesuré). En
recalibrant le seuil à 0,42, le rejet remonte à 1,00 mais le gain sur
les paraphrases **disparaît** : le seuil qui filtre le hors-sujet filtre
aussi les paraphrases rattrapées. **Aucun seuil ne donne les deux.**

Le défaut lexical est donc conservé : il offre le meilleur équilibre
rappel/rejet, sans dépendance à un modèle téléchargé. Le backend
sémantique reste activable (`RAG_EMBEDDING_BACKEND=hybrid`) pour un
déploiement qui accepterait de perdre le rejet sélectif.

### 4.3 Résultat négatif documenté (ablation A5)

Une projection LSA (TruncatedSVD) a été testée pour densifier les
vecteurs TF-IDF. Elle **bat le défaut sur toutes les métriques de
rappel** (Recall@4 0,889 vs 0,759 ; MRR 0,874 vs 0,778) — et elle a été
**rejetée**, parce qu'elle lisse les similarités au point que le rejet
hors-corpus tombe à 0,00. Même leçon qu'en A4 : la métrique optimisée
n'est pas l'objectif visé. L'option reste dans le code uniquement pour
reproduire l'ablation.

---

## 5. Vector store et recherche

Implémentation : `apps/ai_agent/rag/vector_store.py`.

Recherche **exacte** par produit matriciel sur vecteurs normalisés (la
similarité cosinus se réduit à un produit scalaire), avec persistance
disque.

### 5.1 Représentation creuse — la décision qui permet l'échelle

Le store supporte deux représentations derrière la même interface :
**dense** (numpy) pour les backends à faible dimension (spaCy 300d,
hybride), et **creuse** (scipy CSR) pour le backend TF-IDF par défaut.

Ce n'est pas un détail d'implémentation : la dimension de TF-IDF est la
taille du vocabulaire de n-grammes (≈ 6 400 à 34 chunks, ≈ 15 000 à
20 000 chunks). Une première version densifiait les vecteurs
(`.toarray()`) — l'étude de scaling l'a fait **échouer par OOM à
20 000 chunks** (la matrice dense aurait pesé ~1,2 Go). En creux, le
même index tient en **33 Mo** : chaque chunk n'active qu'une fraction
du vocabulaire. C'est un bug réel trouvé *grâce* à la mesure, pas
malgré elle.

### 5.2 Pourquoi pas FAISS / pgvector ?

Parce que la mesure dit que ce n'est pas nécessaire à cette échelle.
L'étude de scaling (voir `reports/rag_evaluation.md`) montre, en régime
réaliste :

| Chunks | Index | p50 | Recall@4 |
|---|---|---|---|
| 34 | 0,15 Mo | 1,2 ms | 0,759 |
| 10 000 | 16,5 Mo | 8,0 ms | 0,796 |
| 20 000 | 32,9 Mo | 14,6 ms | 0,796 |

La **qualité ne se dégrade pas** quand le corpus grandit (ajouter des
documents sur d'autres sujets n'interfère pas avec les requêtes du gold
set) et la latence reste largement sous le seuil de perception, très
loin derrière l'appel LLM (centaines de ms). Un index ANN apporterait
une latence sous-linéaire au prix d'un rappel < 100 %, d'un temps de
construction et d'une dépendance binaire : ce serait payer un coût réel
pour un problème que l'on n'a pas.

L'interface (`add / search / save / load`) reste celle d'un store
classique : si le corpus atteignait ~100 000 chunks, brancher FAISS ne
toucherait que cette classe. Le seuil de bascule est désormais
**mesuré**, pas supposé.

---

## 6. Ranking et sélectivité

Implémentation : `apps/ai_agent/rag/retriever.py`.

### 6.1 Score hybride

`score = cosinus + α · recouvrement_lexical`, avec α = 0,25.

Le recouvrement lexical (Jaccard sur les mots > 3 lettres) rattrape les
requêtes **très courtes** (« rattrapage ? ») où le signal dense seul
est faible. **Pourquoi α = 0,25 ?** Choisi par l'ablation A3 : α = 0
(cosinus pur) donne un MRR de 0,704 ; α = 0,25 le porte à 0,778 sans
dégrader le rejet des requêtes hors-corpus.

### 6.2 Seuil de pertinence — le cœur du « RAG sélectif »

Si **aucun** chunk ne dépasse le seuil (`min_score`), le retriever ne
renvoie **rien** et l'agent n'injecte aucune source. **Pourquoi ?**
Un contexte hors-sujet dégrade la réponse davantage qu'un contexte
absent : mieux vaut laisser l'agent répondre qu'il ne sait pas (ou
basculer sur ses outils) que de le forcer à s'appuyer sur un passage
non pertinent. Le seuil (0,20) a été **calibré empiriquement** sur les
distributions de score des requêtes couvertes vs hors-corpus (le
rapport d'évaluation mesure le taux de rejet correct).

---

## 7. Génération : fournisseur LLM interchangeable

Implémentation : `apps/ai_agent/llm/providers.py`.

La génération est isolée derrière l'interface `LLMProvider` :

- `GroqProvider` — production (modèle Groq défini par `GROQ_MODEL`).
- `OfflineProvider` — générateur **déterministe sans réseau**, qui
  simule le streaming **et** le tool calling. Il permet de tester le
  pipeline complet de l'orchestrateur et d'exécuter les benchmarks de
  façon reproductible, sans mock fragile du SDK.

Changer de fournisseur (OpenAI, vLLM auto-hébergé, Ollama…) = écrire
une classe implémentant `LLMProvider`, **sans toucher à
l'orchestrateur**. C'est ce qui rend l'affirmation « la génération est
un composant remplaçable » vérifiable plutôt que déclarative.

### 7.1 Repli gracieux — ce que devient une démo sans secret

`get_provider()` vérifie que Groq est réellement utilisable (SDK
importable **et** clé configurée — deux conditions distinctes). S'il ne
l'est pas et que `LLM_FALLBACK_OFFLINE` est actif, on sert
`OfflineProvider` au lieu de lever une exception.

Ce n'est pas un contournement, c'est une décision de conception rendue
possible par l'abstraction : une instance de démonstration déployée
sans secret continue d'exposer **tout ce que ce dépôt implémente
réellement** — retrieval, seuil de rejet, sélection d'outils, contrôle
RBAC, streaming SSE. Seule la fluidité rédactionnelle, qui est
précisément la partie déléguée, est dégradée.

En production réelle, `LLM_FALLBACK_OFFLINE=False` fait échouer
bruyamment : un agent qui sert du déterministe sans que personne ne
s'en aperçoive serait pire qu'une erreur visible.

---

## 8. Reproduire les mesures

```bash
# Construire / reconstruire l'index (après modif du corpus)
python manage.py build_rag_index

# Évaluer le retrieval : métriques IR + ablations A1..A5
python manage.py run_rag_eval          # → reports/rag_evaluation.{md,json}

# Benchmarker l'agent complet (20 requêtes), avant/après V1 vs V2
python manage.py run_benchmarks        # → reports/benchmark_results_offline.json
python manage.py run_benchmarks --live # avec le vrai LLM (GROQ_API_KEY)
```

Toutes les commandes offline s'exécutent en moins d'une minute, sans
appel réseau, et sont rejouées en intégration continue (voir le job
`rag-eval` de `.github/workflows/ci.yml`).

---

## 9. Portabilité : un moteur, n'importe quel domaine

Le moteur RAG ne contient **aucune logique spécifique à une faculté**.
Le domaine vit dans deux endroits remplaçables : le corpus `.md`
(`rag/corpus/`) et le schéma d'outils (`TOOLS`). Pour faire tourner le
même moteur sur un autre domaine (support client, RH, juridique…), il
suffit de pointer la variable `RAG_CORPUS_DIR` vers un autre dossier de
documents — **aucun changement de code**.

```bash
# Exemple : indexer le corpus d'un autre domaine
export RAG_CORPUS_DIR=/chemin/vers/mes_documents_md
python manage.py build_rag_index
```

Cette propriété est **verrouillée par un test**
(`tests/test_rag_retrieval.py::DomainPortabilityTest`) qui construit un
index sur un corpus de support e-commerce et vérifie retrieval et rejet
hors-domaine. Voir [`IMPACT.md`](../IMPACT.md) pour la portée complète et
les chemins de généralisation — c'est la réponse à la critique
« domaine interne → impact limité » : le cas d'usage est une faculté,
mais l'architecture livrée est une brique réutilisable.
