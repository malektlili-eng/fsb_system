# BENCHMARKS — Agent IA FSB

Ce document rapporte les performances **mesurées** de l'agent sur
20 requêtes représentatives, ainsi que la comparaison **avant/après**
entre l'architecture V1 (déversement de tout le contexte dans le
prompt) et l'architecture V2 (RAG sélectif + tool calling).

Tous les chiffres sont **reproductibles** :

```bash
# Offline (déterministe, sans réseau) — alimente ce document
python manage.py run_benchmarks
# Live (LLM réel, nécessite GROQ_API_KEY) — ajoute TTFT et latence LLM
python manage.py run_benchmarks --live
```

Le journal machine complet est écrit dans
`reports/benchmark_results_offline.json` (et `_live.json` en mode live).
L'évaluation dédiée du retrieval (métriques IR + ablations) est dans
[`reports/rag_evaluation.md`](reports/rag_evaluation.md).

---

## 1. Méthodologie

Les 20 requêtes (`apps/ai_agent/benchmarks/queries.py`) couvrent les
quatre usages réels de l'agent :

| Famille | Nb | Comportement attendu | Vérifié automatiquement |
|---|---|---|---|
| Connaissance | 8 | réponse fondée sur le corpus (RAG) | ≥ 1 source injectée |
| Action / outil | 6 | action en base via tool calling | bon outil appelé + succès |
| Statistiques | 3 | agrégat BD | `obtenir_statistiques` appelé |
| Limite | 3 | hors-corpus ou refus propre | aucune source hors-sujet |

Chaque requête traverse **l'orchestrateur complet** (retrieval →
prompt → LLM → outils → métriques), pas un composant isolé. En mode
offline, le fournisseur LLM est déterministe (`OfflineProvider`), ce
qui permet de vérifier automatiquement, sans réseau, que : le RAG se
déclenche quand il le faut (et *seulement* quand il le faut), le bon
outil est appelé, l'action réussit, et aucune erreur n'est levée.

**Mesures dépendantes du réseau** (latence LLM totale, time-to-first-
token, longueur de réponse) : renseignées uniquement en mode `--live`.
Le tableau §3 documente la méthode ; les valeurs live dépendent de la
charge de l'API Groq au moment de l'exécution.

---

## 2. Résultats offline (déterministes)

*Généré par `python manage.py run_benchmarks` — 20/20 requêtes
conformes au comportement attendu (100 %).*

### 2.1 Conformité et latence de retrieval

| Métrique | Valeur mesurée |
|---|---|
| Requêtes conformes | **20 / 20 (100 %)** |
| Latence retrieval p50 | 0,9 ms |
| Latence retrieval p95 | 1,1 ms |
| Sources injectées (requêtes connaissance) | 1 à 4 selon couverture |
| Sources injectées (requêtes action/stats pures) | 0 (RAG correctement silencieux) |

Le retrieval est en pratique gratuit à l'échelle du corpus FSB
(~34 chunks) : moins de 2 ms au 95ᵉ centile, négligeable devant la
latence d'un appel LLM (centaines de ms).

### 2.2 Détail par requête

Extrait du journal (colonne `sources` = nb de chunks injectés,
`outil` = outil réellement appelé) :

| ID | Famille | Requête (abrégée) | Sources | Outil appelé | Retrieval |
|---|---|---|---|---|---|
| K1 | connaissance | absences avant élimination | 3 | — | 1,3 ms |
| K2 | connaissance | pondération CC / examen | 4 | — | 1,0 ms |
| K3 | connaissance | session de rattrapage | 3 | — | 0,9 ms |
| K4 | connaissance | pièces d'inscription | 4 | — | 1,1 ms |
| K5 | connaissance | durée du stage licence | 1 | — | 1,0 ms |
| K6 | connaissance | fraude à l'examen | 1 | — | 1,0 ms |
| K7 | connaissance | retard en salle d'examen | 2 | — | 1,1 ms |
| K8 | connaissance | duplicata carte étudiant | 3 | — | 1,0 ms |
| A1 | action | chercher BENALI | 0 | `chercher_etudiant` | — |
| A2 | action | chercher Trabelsi | 0 | `chercher_etudiant` | — |
| A3 | action | lister les filières | 2 | `lister_filieres` | 0,9 ms |
| A4 | action | chercher n° ETU2025 | 1 | `chercher_etudiant` | 0,9 ms |
| A5 | action | chercher Sarra | 0 | `chercher_etudiant` | — |
| A6 | action | chercher inexistant | 0 | `chercher_etudiant` | — |
| S1 | statistiques | nb étudiants inscrits | 0 | `obtenir_statistiques` | — |
| S2 | statistiques | stats globales | 0 | `obtenir_statistiques` | — |
| S3 | statistiques | nb enseignants actifs | 0 | `obtenir_statistiques` | — |
| M1 | limite | horaires piscine | 0 | — (rejeté) | — |
| M2 | limite | blague de maths | 0 | — (rejeté) | — |
| M3 | limite | rôles pour créer étudiant | 2 | — | 0,9 ms |

Lecture : les requêtes purement transactionnelles (A1, A5, A6, S1-S3)
n'injectent **aucune** source — le RAG reste silencieux et l'agent
passe par les outils avec contrôle RBAC. Les requêtes hors-corpus
(M1, M2) sont rejetées par le seuil de pertinence : rien n'est
injecté, l'agent ne s'appuie pas sur du contexte hors-sujet.

---

## 3. Avant / après : V1 vs V2 (impact mesuré du RAG sélectif)

La V1 injectait l'intégralité de la connaissance institutionnelle dans
**chaque** prompt (tout le règlement, toutes les fiches). La V2
n'injecte que les chunks au-dessus du seuil de pertinence. Le harnais
reconstruit les deux prompts pour chaque requête et compte les tokens.

| | V1 (contexte complet) | V2 (RAG sélectif) | Gain |
|---|---|---|---|
| Tokens de contexte injectés / requête | **2 663** (constant) | **96** (moyenne) | **−96,4 %** |
| Contexte hors-sujet possible | oui (tout, tout le temps) | non (seuil) | qualité ↑ |
| Passage à l'échelle du corpus | linéaire (tout grossit le prompt) | borné (top-k) | coût ↓ |

**Conséquences concrètes de cette réduction :**

- **Coût par requête** proportionnel aux tokens d'entrée : diviser le
  contexte par ~27 réduit d'autant la facture de tokens *prompt*.
- **Qualité** : un prompt ciblé évite de noyer la question dans du
  texte non pertinent — l'ablation A3 du rapport d'évaluation montre
  que le score hybride + seuil améliore le MRR de 0,704 → 0,778.
- **Latence** : moins de tokens d'entrée = moins de temps de
  pré-remplissage (prefill) côté LLM, en plus des < 2 ms de retrieval.

---

## 4. Mode live (LLM réel)

Le mode `--live` réexécute les 20 requêtes avec `GroqProvider`
(modèle défini par `GROQ_MODEL`) et **ajoute** les colonnes suivantes au
journal, non déterministes car dépendantes de l'API :

| Métrique | Définition | Où |
|---|---|---|
| `first_token_ms` | time-to-first-token (réactivité perçue) | `latency.first_token_ms` |
| `total_ms` | latence bout-en-bout (retrieval + LLM + outils) | `latency.total_ms` |
| `response_tokens` | longueur de la réponse générée | `response_tokens` |

La conformité comportementale (bon outil, RAG déclenché au bon moment,
absence d'erreur) est vérifiée dans les **deux** modes ; seules les
latences LLM et la longueur de réponse diffèrent. Pour publier des
chiffres live, lancer :

```bash
export GROQ_API_KEY=...   # clé gratuite sur console.groq.com
python manage.py run_benchmarks --live
cat reports/benchmark_results_live.json
```

---

## 5. Limites connues (transparence)

- **Reformulations** — le backend par défaut (TF-IDF n-grammes de
  caractères) ne capture pas les paraphrases sans recouvrement lexical :
  Recall@4 de 0,350 sur la catégorie *reformulée* du gold set. Un
  backend sémantique **a été implémenté et évalué** (ablation A4) : il
  porte cette catégorie à 0,550 mais détruit le rejet hors-corpus, sans
  qu'aucun seuil ne permette d'avoir les deux. Le compromis est
  documenté et mesuré dans `reports/rag_evaluation.md`.
- **Taille du corpus** — le corpus institutionnel de démonstration fait
  34 chunks. Ce n'est plus une inconnue : l'étude de passage à
  l'échelle mesure le retriever **jusqu'à 20 000 chunks** et montre que
  la qualité tient (Recall@4 0,796) avec une latence p50 de 14,6 ms.
  Le pipeline se recharge sur un corpus réel sans changement de code :
  déposer les `.md` dans `apps/ai_agent/rag/corpus/` (ou pointer
  `RAG_CORPUS_DIR`) puis `python manage.py build_rag_index`.
- **Latence de retrieval « 0,0 ms »** sur certaines lignes du journal :
  ce sont les requêtes où aucun chunk ne franchit le seuil (sortie
  anticipée). Aucune anomalie — c'est le rejet sélectif.
- **Mode live** — les latences LLM dépendent de la charge de l'API Groq
  au moment de l'exécution et ne sont donc pas reproductibles ; seules
  les mesures offline sont déterministes.
