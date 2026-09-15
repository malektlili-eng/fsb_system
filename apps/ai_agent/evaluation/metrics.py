"""
apps/ai_agent/evaluation/metrics.py
─────────────────────────────────────────────────────────────────────
Métriques standard de recherche d'information (IR), calculées par
requête puis moyennées (macro-average) sur le gold set.

 • Hit@k        : 1 si au moins un chunk pertinent dans le top-k
 • Recall@k     : |pertinents retrouvés ∩ top-k| / |pertinents corpus|
 • Precision@k  : |pertinents ∩ top-k| / k
 • MRR          : 1 / rang du premier pertinent (0 si absent)
 • nDCG@k       : DCG@k / IDCG@k (gains binaires, log2 discount)

Cas particulier hors-corpus : pour une requête sans chunk pertinent,
la "bonne réponse" du système est de NE RIEN retourner au-dessus du
seuil. On mesure alors le "rejet correct" (correct_rejection = 1 si
aucun chunk retenu), reporté séparément.
─────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import math


def hit_at_k(relevance_flags: list[bool], k: int) -> float:
    return 1.0 if any(relevance_flags[:k]) else 0.0


def recall_at_k(relevance_flags: list[bool], k: int, total_relevant: int) -> float:
    if total_relevant == 0:
        return 0.0
    found = sum(1 for flag in relevance_flags[:k] if flag)
    return min(found / total_relevant, 1.0)


def precision_at_k(relevance_flags: list[bool], k: int) -> float:
    if k == 0:
        return 0.0
    return sum(1 for flag in relevance_flags[:k] if flag) / k


def reciprocal_rank(relevance_flags: list[bool]) -> float:
    for rank, flag in enumerate(relevance_flags, start=1):
        if flag:
            return 1.0 / rank
    return 0.0


def dcg_at_k(relevance_flags: list[bool], k: int) -> float:
    return sum(
        (1.0 if flag else 0.0) / math.log2(rank + 1)
        for rank, flag in enumerate(relevance_flags[:k], start=1)
    )


def ndcg_at_k(relevance_flags: list[bool], k: int, total_relevant: int) -> float:
    if total_relevant == 0:
        return 0.0
    ideal_flags = [True] * min(total_relevant, k)
    ideal = dcg_at_k(ideal_flags, k)
    if ideal == 0:
        return 0.0
    return dcg_at_k(relevance_flags, k) / ideal


def aggregate(per_query: list[dict]) -> dict:
    """Macro-average d'une liste de dicts de métriques par requête."""
    if not per_query:
        return {}
    keys = per_query[0].keys()
    return {
        key: round(sum(row[key] for row in per_query) / len(per_query), 4)
        for key in keys
    }
