"""
apps/ai_agent/evaluation/gold_set.py
─────────────────────────────────────────────────────────────────────
Jeu d'évaluation GOLD du retrieval : 30 requêtes françaises
représentatives, chacune annotée avec les documents/sections
pertinents du corpus.

Méthodologie d'annotation :
 - Un chunk est PERTINENT s'il provient du document `doc` ET que sa
   section contient l'un des motifs `sections` (insensible à la
   casse). Juger au niveau (document, section) rend le gold set
   robuste aux changements de frontières de chunks — on ré-évalue
   les ablations de chunking sans ré-annoter.
 - Les requêtes couvrent 4 familles :
     factuelle directe   (la réponse est une phrase du corpus)
     reformulée          (synonymes/paraphrases, pas les mots du texte)
     procédurale         ("comment faire X ?")
     hors-corpus         (aucun chunk pertinent — teste le seuil)
─────────────────────────────────────────────────────────────────────
"""

# Chaque entrée : query, relevant=[{"doc": ..., "sections": [...]}],
# category ∈ {factuelle, reformulée, procédurale, hors-corpus}
GOLD_QUERIES = [
    # ── Factuelles directes ──────────────────────────────────────────
    {
        "query": "Combien d'absences non justifiées entraînent la défaillance ?",
        "relevant": [
            {"doc": "reglement_etudes", "sections": ["Article 4"]},
            {"doc": "faq_scolarite", "sections": ["Absences"]},
        ],
        "category": "factuelle",
    },
    {
        "query": "Quelle est la pondération entre contrôle continu et examen final ?",
        "relevant": [
            {"doc": "reglement_etudes", "sections": ["Article 2"]},
            {"doc": "faq_scolarite", "sections": ["Notes"]},
        ],
        "category": "factuelle",
    },
    {
        "query": "Quelle est la durée minimale du stage de licence ?",
        "relevant": [
            {"doc": "stages_diplomes", "sections": ["Stage obligatoire"]},
        ],
        "category": "factuelle",
    },
    {
        "query": "Quel est le délai pour justifier une absence ?",
        "relevant": [
            {"doc": "reglement_etudes", "sections": ["Article 4"]},
            {"doc": "faq_scolarite", "sections": ["Absences"]},
        ],
        "category": "factuelle",
    },
    {
        "query": "Combien de crédits faut-il pour valider un semestre ?",
        "relevant": [
            {"doc": "reglement_etudes", "sections": ["Article 1"]},
        ],
        "category": "factuelle",
    },
    {
        "query": "Quelles sont les mentions du diplôme et leurs seuils ?",
        "relevant": [
            {"doc": "stages_diplomes", "sections": ["Conditions de délivrance"]},
        ],
        "category": "factuelle",
    },
    {
        "query": "Quel est le format du numéro étudiant ?",
        "relevant": [
            {"doc": "procedures_inscription", "sections": ["Numéro étudiant"]},
        ],
        "category": "factuelle",
    },
    {
        "query": "Quand se déroulent les examens de la session principale ?",
        "relevant": [
            {"doc": "organisation_examens", "sections": ["Calendrier"]},
        ],
        "category": "factuelle",
    },
    {
        "query": "Combien de surveillants par salle d'examen ?",
        "relevant": [
            {"doc": "organisation_examens", "sections": ["Surveillance"]},
        ],
        "category": "factuelle",
    },
    {
        "query": "Quels rôles peuvent planifier un examen via l'agent IA ?",
        "relevant": [
            {"doc": "roles_permissions", "sections": ["Permissions de l'agent"]},
        ],
        "category": "factuelle",
    },
    # ── Reformulées (synonymes / paraphrases) ────────────────────────
    {
        "query": "Un étudiant recalé peut-il repasser ses épreuves ratées ?",
        "relevant": [
            {"doc": "reglement_etudes", "sections": ["Article 3"]},
        ],
        "category": "reformulée",
    },
    {
        "query": "Que risque un tricheur pendant une épreuve ?",
        "relevant": [
            {"doc": "reglement_etudes", "sections": ["Article 5"]},
        ],
        "category": "reformulée",
    },
    {
        "query": "Peut-on refaire deux fois la même année d'études ?",
        "relevant": [
            {"doc": "procedures_inscription", "sections": ["Réinscription", "redoublement"]},
        ],
        "category": "reformulée",
    },
    {
        "query": "Arriver en retard le jour d'une épreuve, c'est encore possible d'entrer ?",
        "relevant": [
            {"doc": "organisation_examens", "sections": ["Déroulement"]},
        ],
        "category": "reformulée",
    },
    {
        "query": "Je ne suis pas d'accord avec ma note, quels sont mes recours ?",
        "relevant": [
            {"doc": "organisation_examens", "sections": ["réclamations", "Consultation"]},
            {"doc": "faq_scolarite", "sections": ["Notes"]},
        ],
        "category": "reformulée",
    },
    {
        "query": "Qui supervise le stagiaire pendant son projet en entreprise ?",
        "relevant": [
            {"doc": "stages_diplomes", "sections": ["Encadrement"]},
        ],
        "category": "reformulée",
    },
    {
        "query": "Le doyen a-t-il accès à toutes les données ?",
        "relevant": [
            {"doc": "roles_permissions", "sections": ["Hiérarchie"]},
        ],
        "category": "reformulée",
    },
    {
        "query": "Perdre sa carte d'étudiant, ça coûte combien ?",
        "relevant": [
            {"doc": "procedures_inscription", "sections": ["Numéro étudiant"]},
        ],
        "category": "reformulée",
    },
    {
        "query": "Mes coordonnées personnelles sont-elles visibles par le chatbot ?",
        "relevant": [
            {"doc": "roles_permissions", "sections": ["Protection des données"]},
        ],
        "category": "reformulée",
    },
    {
        "query": "Le jury peut-il arrondir ma moyenne ?",
        "relevant": [
            {"doc": "reglement_etudes", "sections": ["Article 6"]},
        ],
        "category": "reformulée",
    },
    # ── Procédurales ─────────────────────────────────────────────────
    {
        "query": "Comment déposer une demande de stage ?",
        "relevant": [
            {"doc": "stages_diplomes", "sections": ["Demande de stage"]},
        ],
        "category": "procédurale",
    },
    {
        "query": "Comment s'inscrire administrativement et quelles pièces fournir ?",
        "relevant": [
            {"doc": "procedures_inscription", "sections": ["Inscription administrative"]},
        ],
        "category": "procédurale",
    },
    {
        "query": "Comment obtenir une attestation de réussite ?",
        "relevant": [
            {"doc": "stages_diplomes", "sections": ["Attestations"]},
            {"doc": "faq_scolarite", "sections": ["Documents"]},
        ],
        "category": "procédurale",
    },
    {
        "query": "Comment retirer son diplôme officiel ?",
        "relevant": [
            {"doc": "stages_diplomes", "sections": ["Attestations", "retrait"]},
        ],
        "category": "procédurale",
    },
    {
        "query": "Comment demander une bourse d'études ?",
        "relevant": [
            {"doc": "faq_scolarite", "sections": ["Bourses"]},
        ],
        "category": "procédurale",
    },
    {
        "query": "Comment changer ses matières optionnelles après la rentrée ?",
        "relevant": [
            {"doc": "procedures_inscription", "sections": ["Inscription pédagogique"]},
        ],
        "category": "procédurale",
    },
    {
        "query": "Comment se passe la soutenance du rapport de stage ?",
        "relevant": [
            {"doc": "stages_diplomes", "sections": ["Encadrement", "soutenance"]},
        ],
        "category": "procédurale",
    },
    # ── Hors-corpus (aucun chunk pertinent attendu) ──────────────────
    {
        "query": "Quel est le menu du restaurant universitaire cette semaine ?",
        "relevant": [],
        "category": "hors-corpus",
    },
    {
        "query": "Quels sont les horaires de la piscine du campus ?",
        "relevant": [],
        "category": "hors-corpus",
    },
    {
        "query": "Comment configurer un serveur Minecraft ?",
        "relevant": [],
        "category": "hors-corpus",
    },
]


def is_relevant(chunk, judgments: list[dict]) -> bool:
    """Vrai si le chunk correspond à l'un des jugements de pertinence."""
    for judgment in judgments:
        if chunk.source_doc != judgment["doc"]:
            continue
        section_lower = chunk.section.lower()
        if any(pat.lower() in section_lower for pat in judgment["sections"]):
            return True
    return False
