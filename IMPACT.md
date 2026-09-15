# IMPACT & portée du projet

> Réponse directe à la critique : *« le projet est aussi domaine-interne
> (un système de gestion de faculté), ce qui limite l'impact perçu ».*

La critique est fondée sur le **cas d'usage** (une faculté), mais la
**valeur d'ingénierie** du projet — le pipeline RAG et l'agent — est
générique et réutilisable. Ce document le démontre plutôt que de
l'affirmer.

---

## 1. Le moteur est domaine-agnostique (prouvé, pas affirmé)

Le sous-système RAG ne contient **aucune logique spécifique à une
faculté**. Le domaine vit entièrement dans deux endroits remplaçables :

- les documents `.md` du corpus (`apps/ai_agent/rag/corpus/`) ;
- le schéma d'outils métier (`TOOLS` dans `orchestrator.py`).

Changer de domaine = pointer `RAG_CORPUS_DIR` vers un autre dossier de
documents. **Aucune ligne de code du moteur ne change.**

Cette propriété est **verrouillée par un test automatisé**
(`tests/test_rag_retrieval.py::DomainPortabilityTest`) qui construit un
index sur un corpus de **support e-commerce** (politique de retour,
livraison) et vérifie que :

- la question « Combien de temps pour me faire rembourser ? » retrouve
  bien le passage sur le remboursement sous 14 jours ;
- une question hors-domaine est correctement **rejetée** par le seuil.

```bash
python manage.py test tests.test_rag_retrieval.DomainPortabilityTest
```

Autrement dit : le même moteur sert aussi bien un règlement
universitaire qu'une base de connaissances RH, un corpus juridique, une
documentation produit ou un support client. La faculté n'est qu'un
**corpus de démonstration**, pas une contrainte d'architecture.

---

## 2. Ce qui constitue la valeur transférable

| Composant | Réutilisable tel quel ? | Ce qu'il apporte à n'importe quel domaine |
|---|---|---|
| Chunking phrase-aligné (`chunking.py`) | ✅ | Découpage robuste de tout document texte |
| Embeddings pluggables (`embeddings.py`) | ✅ | Vectorisation locale, backend interchangeable |
| Vector store cosinus (`vector_store.py`) | ✅ | Recherche par similarité + persistance |
| Ranking hybride + seuil (`retriever.py`) | ✅ | Pertinence + rejet du hors-sujet |
| Harnais d'évaluation (`evaluation/`) | ✅ | Mesure IR sur n'importe quel gold set |
| Fournisseur LLM abstrait (`llm/providers.py`) | ✅ | Générateur interchangeable (Groq, OpenAI, local) |
| Orchestrateur streaming + RBAC | ✅ | Boucle agentique réutilisable |
| Corpus FSB + schéma d'outils | ❌ (spécifique) | La seule partie à réécrire par domaine |

**~90 % du code livré est indépendant du domaine.** C'est la définition
d'une brique d'infrastructure réutilisable, pas d'un one-shot métier.

---

## 3. Impact quantifié sur le cas d'usage démontré

Même en restant sur la faculté, l'agent produit une valeur mesurable
(chiffres issus de `BENCHMARKS.md`, mode offline déterministe) :

- **Réduction de contexte de ~96 %** vs l'approche naïve V1 (2 663 →
  ~96 tokens injectés par requête) → coût par requête et latence de
  pré-remplissage réduits d'autant.
- **Retrieval < 2 ms** au 95ᵉ centile → l'ajout du RAG est
  imperceptible dans la latence perçue.
- **Actions réelles en base** (création d'étudiant, planification
  d'examen) au lieu de simple texte : l'agent remplace des séquences de
  navigation manuelle dans plusieurs écrans par une requête en langage
  naturel, sous contrôle de permissions par rôle.

Sur un cas d'usage réel, cela se traduit par : moins de temps agent par
tâche administrative, une porte d'entrée unique en langage naturel, et
une base de connaissances interrogeable au lieu de PDF de règlements que
personne ne lit.

---

## 4. Chemins de généralisation (au-delà de la démonstration)

Le même socle se décline directement en produits à plus large portée :

1. **Assistant de support client** — remplacer le corpus par la FAQ et
   la doc produit d'une entreprise ; les outils deviennent
   `créer_ticket`, `vérifier_commande`.
2. **Copilote de conformité / juridique** — corpus = textes
   réglementaires ; le seuil de pertinence et la citation de sources
   sont exactement ce qu'exige ce domaine.
3. **Assistant RH interne** — corpus = conventions, procédures RH ;
   RBAC déjà en place pour cloisonner l'accès aux données sensibles.

Aucun de ces pivots ne demande de retoucher le moteur : corpus + schéma
d'outils, et l'évaluation IR se rejoue sur le nouveau gold set.

---

## 5. En résumé

Le **cas d'usage** présenté est interne (une faculté), mais
l'**architecture** livrée est une brique RAG + agent générique,
évaluée, testée et prouvée transférable. La faculté sert de terrain de
démonstration concret et vérifiable ; la valeur d'ingénierie, elle, est
réutilisable sur n'importe quel domaine documentaire.
