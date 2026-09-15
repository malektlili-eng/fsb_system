"""
apps/ai_agent/evaluation/scaling.py
─────────────────────────────────────────────────────────────────────
Étude de PASSAGE À L'ÉCHELLE du retrieval.

Motivation (critique de revue) : « votre latence de 0.79 ms p50 n'est
pas une performance — c'est la conséquence d'un corpus assez petit pour
que n'importe quelle méthode soit rapide. Le retriever tient-il à
10 000 chunks ? »

Réponse : ce module mesure la latence ET la qualité du retrieval en
faisant croître le corpus de 34 à ~20 000 chunks, en gardant les
requêtes du gold set et leurs jugements de pertinence.

Méthode de croissance du corpus (« distracteurs synthétiques ») :
    Le corpus réel FSB (34 chunks) est conservé tel quel — les chunks
    pertinents restent EXACTEMENT les mêmes. On y ajoute N chunks
    DISTRACTEURS générés par recombinaison markovienne du vocabulaire
    administratif du corpus. Ces distracteurs sont plausibles
    (même registre lexical, même longueur) mais ne répondent à aucune
    requête du gold set.

Pourquoi des distracteurs plutôt qu'une duplication ?
    Dupliquer les vrais chunks fausserait la mesure : les copies
    seraient pertinentes et gonfleraient artificiellement le rappel.
    Les distracteurs mesurent ce qui compte réellement : la capacité du
    retriever à retrouver l'aiguille quand la botte de foin grandit.

Ce que l'étude produit :
    • latence p50/p95 en fonction de la taille du corpus
    • Recall@4 / MRR en fonction de la taille (dégradation de qualité)
    • empreinte mémoire de l'index
    • le point de rupture éventuel de la recherche exacte numpy
─────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import random
import time

from apps.ai_agent.rag.chunking import Chunk
from apps.ai_agent.rag.embeddings import TfidfBackend
from apps.ai_agent.rag.knowledge import load_corpus_chunks
from apps.ai_agent.rag.retriever import Retriever

from .gold_set import GOLD_QUERIES, is_relevant
from .metrics import aggregate, hit_at_k, ndcg_at_k, precision_at_k, recall_at_k
from .metrics import reciprocal_rank

TOP_K = 4
DEFAULT_SIZES = (34, 500, 2_000, 5_000, 10_000, 20_000)


def _build_markov_model(texts: list[str], order: int = 2) -> dict:
    """Modèle de Markov d'ordre `order` sur les mots du corpus réel."""
    model: dict[tuple, list[str]] = {}
    for text in texts:
        words = text.split()
        for i in range(len(words) - order):
            key = tuple(words[i: i + order])
            model.setdefault(key, []).append(words[i + order])
    return model


def generate_distractors(
    real_chunks: list[Chunk],
    n: int,
    seed: int = 42,
    words_per_chunk: int = 60,
) -> list[Chunk]:
    """
    Génère `n` chunks distracteurs plausibles par chaîne de Markov sur le
    vocabulaire du corpus réel. Aucun n'est pertinent pour le gold set.
    """
    rng = random.Random(seed)
    texts = [chunk.content for chunk in real_chunks]
    model = _build_markov_model(texts, order=2)
    keys = list(model.keys())
    if not keys:
        raise RuntimeError("Corpus réel trop petit pour le modèle de Markov.")

    distractors: list[Chunk] = []
    for i in range(n):
        key = rng.choice(keys)
        words = list(key)
        for _ in range(words_per_chunk):
            candidates = model.get(tuple(words[-2:]))
            if not candidates:
                key = rng.choice(keys)
                words.extend(key)
                continue
            words.append(rng.choice(candidates))
        content = " ".join(words)
        section = f"Document synthétique {i // 10:04d} > Section {i % 10}"
        distractors.append(
            Chunk(
                chunk_id=f"synth::{i:06d}",
                text=f"[{section}] {content}",
                content=content,
                source_doc=f"synthetique_{i // 10:04d}",
                section=section,
                position=i % 10,
                metadata={"synthetic": True},
            )
        )
    return distractors


# Sujets périphériques d'une faculté, absents du corpus de règlements.
# Ils produisent des distracteurs RÉALISTES : même contexte
# institutionnel, mais vocabulaire distinct de celui des requêtes.
_REALISTIC_TOPICS = (
    "bibliothèque universitaire prêt ouvrage retour livre lecteur rayon",
    "restaurant universitaire menu repas ticket self service plateau",
    "association étudiante club sportif tournoi adhésion cotisation",
    "laboratoire recherche publication article revue congrès doctorant",
    "informatique réseau wifi identifiant messagerie compte accès serveur",
    "infrastructure bâtiment amphithéâtre parking maintenance travaux",
)


def generate_realistic_distractors(
    n: int, seed: int = 7, words_per_chunk: int = 50
) -> list[Chunk]:
    """
    Génère `n` chunks distracteurs d'un AUTRE domaine documentaire
    (bibliothèque, restauration, associations…), donc non pertinents.

    C'est le régime réaliste : dans une vraie faculté, faire grossir le
    corpus signifie ajouter des documents sur d'AUTRES sujets, pas
    dupliquer des variantes du règlement des examens.
    """
    rng = random.Random(seed)
    chunks: list[Chunk] = []
    for i in range(n):
        vocabulary = rng.choice(_REALISTIC_TOPICS).split()
        content = " ".join(rng.choice(vocabulary) for _ in range(words_per_chunk))
        section = f"Document annexe {i // 10:04d} > Section {i % 10}"
        chunks.append(
            Chunk(
                chunk_id=f"annexe::{i:06d}",
                text=f"[{section}] {content}",
                content=content,
                source_doc=f"annexe_{i // 10:04d}",
                section=section,
                position=i % 10,
                metadata={"synthetic": True},
            )
        )
    return chunks


def _evaluate_quality(retriever: Retriever) -> dict:
    """Recall/MRR/nDCG sur les requêtes du gold set couvertes."""
    per_query = []
    for item in GOLD_QUERIES:
        if item["category"] == "hors-corpus":
            continue
        result = retriever.retrieve(item["query"], top_k=TOP_K)
        flags = [is_relevant(chunk, item["relevant"]) for chunk, _ in result.chunks]
        total_relevant = sum(
            1 for chunk in retriever.store.chunks if is_relevant(chunk, item["relevant"])
        )
        per_query.append(
            {
                f"hit@{TOP_K}": hit_at_k(flags, TOP_K),
                f"recall@{TOP_K}": recall_at_k(flags, TOP_K, total_relevant),
                f"precision@{TOP_K}": precision_at_k(flags, TOP_K),
                "mrr": reciprocal_rank(flags),
                f"ndcg@{TOP_K}": ndcg_at_k(flags, TOP_K, total_relevant),
            }
        )
    return aggregate(per_query)


def _measure_latency(retriever: Retriever, repeats: int = 3) -> dict:
    """Latence de retrieval sur toutes les requêtes du gold set."""
    latencies = []
    for _ in range(repeats):
        for item in GOLD_QUERIES:
            start = time.perf_counter()
            retriever.retrieve(item["query"], top_k=TOP_K)
            latencies.append((time.perf_counter() - start) * 1000)
    latencies.sort()
    return {
        "p50": round(latencies[len(latencies) // 2], 3),
        "p95": round(latencies[int(len(latencies) * 0.95) - 1], 3),
        "p99": round(latencies[int(len(latencies) * 0.99) - 1], 3),
        "max": round(latencies[-1], 3),
    }


def run_scaling_study(sizes=DEFAULT_SIZES, seed: int = 42) -> dict:
    """
    Exécute l'étude sur DEUX régimes de distracteurs, car ils répondent à
    deux questions différentes :

     • RÉALISTE  — les nouveaux documents portent sur d'autres sujets
       (bibliothèque, restauration…). C'est ce qui se passe quand un
       corpus institutionnel grandit. Mesure : le retriever tient-il ?

     • ADVERSARIAL — les distracteurs sont des recombinaisons
       markoviennes du corpus lui-même : même vocabulaire, mêmes
       tournures. C'est un pire cas volontairement injuste (certains
       distracteurs contiennent des phrases réellement pertinentes, non
       annotées comme telles). Mesure : borne inférieure pessimiste.
    """
    real_chunks = load_corpus_chunks()
    n_real = len(real_chunks)
    regimes = {}

    for regime in ("realistic", "adversarial"):
        rows = []
        for size in sizes:
            if size < n_real:
                continue
            n_distractors = size - n_real
            chunks = list(real_chunks)
            if n_distractors:
                if regime == "realistic":
                    chunks += generate_realistic_distractors(n_distractors, seed=seed)
                else:
                    chunks += generate_distractors(real_chunks, n_distractors, seed=seed)

            build_start = time.perf_counter()
            retriever = Retriever.build(backend=TfidfBackend(), chunks=chunks)
            build_ms = (time.perf_counter() - build_start) * 1000

            rows.append(
                {
                    "n_chunks": len(chunks),
                    "n_distractors": n_distractors,
                    "build_ms": round(build_ms, 1),
                    "index_mb": round(retriever.store.nbytes() / (1024 * 1024), 2),
                    "index_dim": int(retriever.store._vectors.shape[1]),
                    "sparse": retriever.store.is_sparse,
                    "latency_ms": _measure_latency(retriever),
                    "quality": _evaluate_quality(retriever),
                }
            )
        regimes[regime] = rows

    return {
        "n_real_chunks": n_real,
        "method": (
            "Le corpus réel est conservé intact (les chunks pertinents sont "
            "identiques à toutes les tailles) ; seuls des distracteurs non "
            "pertinents sont ajoutés. Deux régimes : RÉALISTE (autres sujets) "
            "et ADVERSARIAL (recombinaison du corpus, pire cas)."
        ),
        "regimes": regimes,
    }


def format_scaling_markdown(study: dict) -> list[str]:
    """Rend l'étude en tableaux Markdown pour le rapport."""
    lines = [
        "## Passage à l'échelle du corpus",
        "",
        "*« Le retriever tient-il à 10 000 chunks ? » — mesuré, pas supposé.*",
        "",
        f"Méthode : {study['method']}",
        "",
    ]
    titles = {
        "realistic": (
            "### Régime réaliste (distracteurs d'autres sujets)",
            "C'est le scénario d'un corpus institutionnel qui grandit : on "
            "ajoute des documents sur la bibliothèque, la restauration, les "
            "associations… La qualité doit tenir.",
        ),
        "adversarial": (
            "### Régime adversarial (recombinaison du corpus — pire cas)",
            "Distracteurs générés par chaîne de Markov sur le corpus lui-même : "
            "même vocabulaire administratif, mêmes tournures. Volontairement "
            "injuste — certains distracteurs contiennent des phrases réellement "
            "pertinentes qui ne sont pas annotées comme telles. À lire comme une "
            "borne inférieure pessimiste, pas comme le comportement attendu.",
        ),
    }
    for regime, rows in study["regimes"].items():
        title, blurb = titles[regime]
        lines += [
            title,
            "",
            blurb,
            "",
            "| Chunks | Index (Mo) | Dim | Build (ms) | p50 (ms) | p95 (ms) "
            f"| p99 (ms) | Recall@{TOP_K} | MRR |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        for row in rows:
            lat = row["latency_ms"]
            q = row["quality"]
            n = f"{row['n_chunks']:,}".replace(",", " ")
            lines.append(
                f"| {n} | {row['index_mb']} | {row['index_dim']} "
                f"| {row['build_ms']:.0f} | {lat['p50']} | {lat['p95']} "
                f"| {lat['p99']} | {q[f'recall@{TOP_K}']:.3f} | {q['mrr']:.3f} |"
            )
        lines.append("")
    return lines
