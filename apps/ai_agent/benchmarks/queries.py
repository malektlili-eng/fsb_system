"""
apps/ai_agent/benchmarks/queries.py
─────────────────────────────────────────────────────────────────────
Les 20 requêtes représentatives du benchmark (BENCHMARKS.md).

Répartition par famille d'usage réel de l'agent :
  8  connaissance   → réponse attendue depuis le corpus RAG
  6  action/outil   → réponse attendue via tool calling (BD)
  3  statistiques   → agrégats BD via obtenir_statistiques
  3  mixte/limite   → hors-périmètre ou nécessitant un refus propre

Chaque entrée déclare son COMPORTEMENT ATTENDU vérifiable
automatiquement en mode offline :
  expect_rag       : le retrieval doit injecter ≥ 1 source
  expect_no_rag    : le retrieval ne doit RIEN injecter (seuil)
  expect_tool      : nom de l'outil qui doit être appelé
  expect_success   : l'outil doit réussir (permissions, données)
─────────────────────────────────────────────────────────────────────
"""

BENCHMARK_QUERIES = [
    # ── Connaissance (RAG) ───────────────────────────────────────────
    {
        "id": "K1",
        "category": "connaissance",
        "query": "Combien d'absences non justifiées avant d'être éliminé ?",
        "expect_rag": True,
    },
    {
        "id": "K2",
        "category": "connaissance",
        "query": "Quelle est la pondération contrôle continu / examen final ?",
        "expect_rag": True,
    },
    {
        "id": "K3",
        "category": "connaissance",
        "query": "Comment se déroule la session de rattrapage ?",
        "expect_rag": True,
    },
    {
        "id": "K4",
        "category": "connaissance",
        "query": "Quelles pièces fournir pour l'inscription administrative ?",
        "expect_rag": True,
    },
    {
        "id": "K5",
        "category": "connaissance",
        "query": "Quelle est la durée minimale du stage de fin d'études ?",
        "expect_rag": True,
    },
    {
        "id": "K6",
        "category": "connaissance",
        "query": "Que se passe-t-il en cas de fraude à un examen ?",
        "expect_rag": True,
    },
    {
        "id": "K7",
        "category": "connaissance",
        "query": "Un retardataire peut-il entrer en salle d'examen ?",
        "expect_rag": True,
    },
    {
        "id": "K8",
        "category": "connaissance",
        "query": "Comment obtenir un duplicata de carte étudiant et à quel prix ?",
        "expect_rag": True,
    },
    # ── Actions / outils (BD) ────────────────────────────────────────
    {
        "id": "A1",
        "category": "action",
        "query": "Cherche l'étudiant BENALI",
        "expect_tool": "chercher_etudiant",
        "expect_success": True,
    },
    {
        "id": "A2",
        "category": "action",
        "query": "Trouve les étudiants nommés Trabelsi",
        "expect_tool": "chercher_etudiant",
        "expect_success": True,
    },
    {
        "id": "A3",
        "category": "action",
        "query": "Donne-moi la liste des filières",
        "expect_tool": "lister_filieres",
        "expect_success": True,
    },
    {
        "id": "A4",
        "category": "action",
        "query": "Cherche l'étudiant numéro ETU2025",
        "expect_tool": "chercher_etudiant",
        "expect_success": True,
    },
    {
        "id": "A5",
        "category": "action",
        "query": "Trouve l'étudiante Sarra",
        "expect_tool": "chercher_etudiant",
        "expect_success": True,
    },
    {
        "id": "A6",
        "category": "action",
        "query": "Cherche INEXISTANT_XYZ",
        "expect_tool": "chercher_etudiant",
        "expect_success": True,  # succès = requête exécutée (0 résultat)
    },
    # ── Statistiques ─────────────────────────────────────────────────
    {
        "id": "S1",
        "category": "statistiques",
        "query": "Combien d'étudiants sont inscrits actuellement ?",
        "expect_tool": "obtenir_statistiques",
        "expect_success": True,
    },
    {
        "id": "S2",
        "category": "statistiques",
        "query": "Donne-moi les statistiques globales de la faculté",
        "expect_tool": "obtenir_statistiques",
        "expect_success": True,
    },
    {
        "id": "S3",
        "category": "statistiques",
        "query": "Combien d'enseignants actifs avons-nous ?",
        "expect_tool": "obtenir_statistiques",
        "expect_success": True,
    },
    # ── Mixte / limites ──────────────────────────────────────────────
    {
        "id": "M1",
        "category": "limite",
        "query": "Quels sont les horaires de la piscine du campus ?",
        "expect_no_rag": True,  # hors corpus → aucune source injectée
    },
    {
        "id": "M2",
        "category": "limite",
        "query": "Raconte-moi une blague sur les mathématiciens",
        "expect_no_rag": True,
    },
    {
        "id": "M3",
        "category": "limite",
        "query": "Quels rôles peuvent créer un étudiant via l'agent ?",
        "expect_rag": True,  # documenté dans roles_permissions.md
    },
]
