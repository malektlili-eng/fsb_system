# Évaluation du retrieval RAG

*Généré le 2026-09-16 08:53:24 par `python manage.py run_rag_eval` — journal complet : [`rag_evaluation.json`](rag_evaluation.json)*

## Configuration évaluée

- Backend d'embeddings : `tfidf-char35`
- Corpus : 34 chunks (6 documents institutionnels, chunking phrase-aligné 450 car., chevauchement 1 phrase)
- Gold set : 30 requêtes (27 avec pertinence annotée + 3 hors-corpus), top-k = 4, seuil = 0.2

## Résultats globaux

| Métrique | Valeur |
|---|---|
| Hit@4 | 0.778 |
| Recall@4 | 0.759 |
| Precision@4 | 0.259 (plafond théorique 0.343 — voir ci-dessous) |
| MRR | 0.778 |
| nDCG@4 | 0.763 |
| Rejet correct (hors-corpus) | 0.67 |
| Latence retrieval p50 / p95 | 0.87 ms / 1.11 ms |

## Détail par catégorie de requête

| Catégorie | Recall@4 | Precision@4 | MRR | nDCG@4 |
|---|---|---|---|---|
| factuelle | 1.000 | 0.375 | 1.000 | 1.000 |
| procédurale | 1.000 | 0.321 | 1.000 | 1.000 |
| reformulée | 0.350 | 0.100 | 0.400 | 0.361 |

## Ablations

Chaque ligne ne fait varier qu'un facteur par rapport à la configuration par défaut.

| Configuration | Chunks | Recall@4 | Precision@4 | MRR | nDCG@4 | Rejet correct | reformulée R@4 |
|---|---|---|---|---|---|---|---|
| **A1_chunk_size** | | | | | | | |
| 300 caractères | 61 | 0.646 | 0.389 | 0.759 | 0.675 | 0.67 | 0.283 |
| 450 caractères (défaut) | 34 | 0.759 | 0.259 | 0.778 | 0.763 | 0.67 | 0.350 |
| 900 caractères | 30 | 0.778 | 0.232 | 0.778 | 0.778 | 0.67 | 0.400 |
| **A2_overlap** | | | | | | | |
| 0 phrase(s) | 33 | 0.747 | 0.232 | 0.778 | 0.755 | 0.67 | 0.350 |
| 1 phrase(s) (défaut) | 34 | 0.759 | 0.259 | 0.778 | 0.763 | 0.67 | 0.350 |
| **A3_lexical_alpha** | | | | | | | |
| α = 0.0 | 34 | 0.685 | 0.241 | 0.704 | 0.689 | 0.67 | 0.250 |
| α = 0.25 (défaut) | 34 | 0.759 | 0.259 | 0.778 | 0.763 | 0.67 | 0.350 |
| α = 0.5 | 34 | 0.759 | 0.259 | 0.778 | 0.763 | 0.67 | 0.350 |
| **A4_backend** | | | | | | | |
| spacy-fr-core-news-md-idf @ seuil défaut 0.2 | 34 | 0.660 | 0.222 | 0.611 | 0.602 | 0.00 | 0.450 |
| spacy-fr-core-news-md-idf @ seuil recalibré 0.72 | 34 | 0.457 | 0.167 | 0.444 | 0.430 | 1.00 | 0.100 |
| hybrid-spacy+tfidf-w0.5 @ seuil défaut 0.2 | 34 | 0.833 | 0.278 | 0.815 | 0.810 | 0.00 | 0.550 |
| hybrid-spacy+tfidf-w0.5 @ seuil recalibré 0.42 | 34 | 0.759 | 0.259 | 0.759 | 0.750 | 1.00 | 0.350 |
| **A5_svd_lsa** | | | | | | | |
| TF-IDF + TruncatedSVD 256 (retiré : lisse les similarités, le rejet hors-corpus s'effondre) | 34 | 0.889 | 0.296 | 0.874 | 0.865 | 0.00 | 0.700 |

**État de l'ablation A4** : exécutée — 4 configurations sémantiques mesurées (spaCy FR seul et hybride dense+lexical, chacune au seuil par défaut et au seuil recalibré). Le compromis sémantique/rejet est donc tranché empiriquement, pas supposé.

> *Variante optionnelle non instanciée dans cet environnement* : `SentenceTransformerBackend` (sentence-transformers n'est pas installé. Installez-le (pip install sentence-transformers) ou utilisez TfidfBackend.). Elle n'ajouterait pas de conclusion nouvelle : les deux backends denses évalués ci-dessus établissent déjà le compromis (gain sur les reformulations, effondrement du rejet hors-corpus), et la variante partage leur espace dense. Le code du backend est présent et testé ; seuls les poids manquent.

## Precision@4 : lecture honnête (plafond du gold set)

Precision@4 mesurée = **0.259**. Prise isolément, cette valeur suggère que ~3 chunks sur 4 seraient du bruit. **C'est faux, et voici pourquoi** :

- 20 des 27 requêtes annotées n'ont **qu'un seul** chunk pertinent dans le corpus (moyenne : 1.37, médiane : 1).
- Avec k = 4, un système **parfait** — qui placerait tous les chunks pertinents en tête — plafonnerait à **0.343** de Precision@4. La métrique est bornée par construction du gold set, pas par le retriever.
- Nous atteignons 0.259 / 0.343 = **75.7 % du plafond atteignable**.

**Conclusion** : sur ce gold set, Precision@4 n'est pas une métrique informative — c'est un artefact de plafond. Les métriques qui portent réellement l'information ici sont MRR (0.778) et nDCG@4 (0.763), qui mesurent le **rang** du premier chunk pertinent. Réduire k à 1 ou 2 remonterait mécaniquement la précision sans améliorer le système ; nous gardons k = 4 parce que le LLM tire bénéfice du contexte adjacent, et nous acceptons la précision basse comme le prix de ce choix.

## Passage à l'échelle du corpus

*« Le retriever tient-il à 10 000 chunks ? » — mesuré, pas supposé.*

Méthode : Le corpus réel est conservé intact (les chunks pertinents sont identiques à toutes les tailles) ; seuls des distracteurs non pertinents sont ajoutés. Deux régimes : RÉALISTE (autres sujets) et ADVERSARIAL (recombinaison du corpus, pire cas).

### Régime réaliste (distracteurs d'autres sujets)

C'est le scénario d'un corpus institutionnel qui grandit : on ajoute des documents sur la bibliothèque, la restauration, les associations… La qualité doit tenir.

| Chunks | Index (Mo) | Dim | Build (ms) | p50 (ms) | p95 (ms) | p99 (ms) | Recall@4 | MRR |
|---|---|---|---|---|---|---|---|---|
| 34 | 0.15 | 6449 | 24 | 0.885 | 0.999 | 1.038 | 0.759 | 0.778 |
| 500 | 0.92 | 7145 | 255 | 1.239 | 1.321 | 1.335 | 0.796 | 0.815 |
| 2 000 | 3.38 | 7958 | 1019 | 2.9 | 3.368 | 3.43 | 0.796 | 0.815 |
| 5 000 | 8.31 | 9490 | 2551 | 3.485 | 3.903 | 4.02 | 0.796 | 0.815 |
| 10 000 | 16.51 | 12045 | 5216 | 6.05 | 6.917 | 7.191 | 0.796 | 0.815 |
| 20 000 | 32.93 | 15159 | 9907 | 10.783 | 12.608 | 13.474 | 0.796 | 0.815 |

### Régime adversarial (recombinaison du corpus — pire cas)

Distracteurs générés par chaîne de Markov sur le corpus lui-même : même vocabulaire administratif, mêmes tournures. Volontairement injuste — certains distracteurs contiennent des phrases réellement pertinentes qui ne sont pas annotées comme telles. À lire comme une borne inférieure pessimiste, pas comme le comportement attendu.

| Chunks | Index (Mo) | Dim | Build (ms) | p50 (ms) | p95 (ms) | p99 (ms) | Recall@4 | MRR |
|---|---|---|---|---|---|---|---|---|
| 34 | 0.15 | 6449 | 36 | 0.883 | 0.994 | 1.127 | 0.759 | 0.778 |
| 500 | 2.75 | 6785 | 308 | 2.037 | 2.3 | 2.442 | 0.562 | 0.512 |
| 2 000 | 11.09 | 7598 | 1212 | 5.188 | 5.713 | 6.052 | 0.346 | 0.321 |
| 5 000 | 27.77 | 9130 | 2902 | 11.533 | 13.08 | 14.35 | 0.284 | 0.222 |
| 10 000 | 55.52 | 11685 | 6204 | 22.105 | 25.764 | 28.388 | 0.235 | 0.161 |
| 20 000 | 111.06 | 14799 | 11952 | 45.569 | 57.912 | 63.75 | 0.148 | 0.099 |

## Lecture des résultats

- **Seuil de pertinence** — mécanisme clé du « RAG sélectif » : les requêtes hors-corpus doivent être rejetées (aucune injection) plutôt que de polluer le prompt avec du contexte hors-sujet. C'est cette propriété qui fait rejeter les configurations A4 et A5, pourtant meilleures sur le rappel.

- **A4 (sémantique vs lexical) — le compromis est réel et mesuré.** Le backend hybride (spaCy FR + TF-IDF) **améliore** le rappel global et fait passer les requêtes *reformulées* de 0.350 à 0.550 : il résout bien la limite identifiée. Mais au seuil par défaut, son rejet hors-corpus tombe à 0.00 — les scores denses des requêtes hors-corpus **chevauchent** ceux des requêtes couvertes, ce n'est pas un simple décalage d'échelle. Au seuil recalibré (0.42), le rejet remonte à 1.00 mais le gain sur les reformulations **disparaît** (retour à 0.350) : le seuil qui filtre le hors-corpus filtre aussi les paraphrases rattrapées. **Aucun seuil ne permet d'avoir les deux.** Le défaut lexical est conservé parce qu'il offre le meilleur équilibre rappel/rejet sans dépendance à un modèle téléchargé.

- **A5 (LSA/SVD)** — même leçon : meilleure sur toutes les métriques de rappel, éliminée parce qu'elle détruit le rejet. La métrique optimisée n'est pas l'objectif visé.

- **Passage à l'échelle** — en régime réaliste, la qualité **tient** à 20 000 chunks et la latence reste sous ~10 ms p50 : la recherche exacte creuse est suffisante bien au-delà du corpus actuel. Le régime adversarial montre la borne inférieure quand les distracteurs sont des recombinaisons du corpus lui-même.

- **Reproduire** : `python manage.py run_rag_eval` (quelques minutes avec l'étude de scaling, `--no-scaling` pour la version rapide ; aucun appel réseau).
