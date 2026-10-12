"""Hybrid retriever: plain dicts and tuples, float arithmetic, sorted() for every ranking."""
import math


def _order(scores):
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))


def rrf(rankings, k=60, weights=None):
    if k <= 0:
        raise ValueError("k must be positive")
    if weights is None:
        weights = [1.0] * len(rankings)
    if len(weights) != len(rankings):
        raise ValueError("one weight per ranking")
    scores = {}
    for ranking, weight in zip(rankings, weights):
        for rank, (doc_id, _score) in enumerate(ranking, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + weight / (k + rank)
    return _order(scores)


def _normalized(ranking):
    if not ranking:
        return {}
    values = [float(score) for _doc_id, score in ranking]
    low, high = min(values), max(values)
    if high == low:
        return {doc_id: 1.0 for doc_id, _score in ranking}
    return {doc_id: (float(score) - low) / (high - low) for doc_id, score in ranking}


def weighted(rankings, weights):
    if len(weights) != len(rankings):
        raise ValueError("one weight per ranking")
    scores = {}
    for ranking, weight in zip(rankings, weights):
        for doc_id, value in _normalized(ranking).items():
            scores[doc_id] = scores.get(doc_id, 0.0) + weight * value
    return _order(scores)


def rerank(candidates, query, score_fn, top_n):
    if top_n < 0:
        raise ValueError("top_n must be non-negative")
    head = list(candidates[:top_n])
    tail = list(candidates[top_n:])
    scored = {doc_id: float(score_fn(query, doc_id)) for doc_id, _score in head}
    return _order(scored) + tail


def hit_rank(ids, expected):
    for rank, doc_id in enumerate(ids, start=1):
        if doc_id == expected:
            return rank
    return None


def mrr(ranks):
    if not ranks:
        return 0.0
    return sum(1.0 / rank for rank in ranks if rank) / len(ranks)


def percentile(samples, p):
    if not samples:
        raise ValueError("no samples")
    ordered = sorted(samples)
    position = max(1, math.ceil(p / 100 * len(ordered)))
    return ordered[position - 1]


def measure(queries, retrievers, *, clock, score_fn, top_n, k=60):
    rows = []
    for query in queries:
        started = clock()
        rankings = [retriever(query["text"]) for retriever in retrievers]
        fused = rrf(rankings, k)
        fused_at = clock()
        reranked = rerank(fused, query["text"], score_fn, top_n)
        reranked_at = clock()
        fused_ids = [doc_id for doc_id, _score in fused]
        reranked_ids = [doc_id for doc_id, _score in reranked]
        rows.append({
            "id": query["id"],
            "fused": fused_ids,
            "reranked": reranked_ids,
            "hit": {"fused": hit_rank(fused_ids, query["expected"]), "reranked": hit_rank(reranked_ids, query["expected"])},
            "latency_ms": {"fused": (fused_at - started) * 1000, "reranked": (reranked_at - started) * 1000},
        })
    samples = {stage: [row["latency_ms"][stage] for row in rows] for stage in ("fused", "reranked")}
    return {
        "k": k, "top_n": top_n, "queries": rows, "samples": samples,
        "mrr": {stage: mrr([row["hit"][stage] for row in rows]) for stage in ("fused", "reranked")},
        "p50_ms": {stage: percentile(samples[stage], 50) for stage in ("fused", "reranked")},
        "p95_ms": {stage: percentile(samples[stage], 95) for stage in ("fused", "reranked")},
    }


def decide(report, budget):
    samples = report.get("samples") or {}
    if not samples.get("reranked") or not samples.get("fused"):
        raise ValueError("the report carries no latency samples: a reranker whose cost was not measured is never adopted")
    rows = report["queries"]
    gain = mrr([row["hit"]["reranked"] for row in rows]) - mrr([row["hit"]["fused"] for row in rows])
    p95_fused = percentile(samples["fused"], 95)
    p95_reranked = percentile(samples["reranked"], 95)
    min_gain, limit = float(budget["min_mrr_gain"]), float(budget["p95_ms"])
    keep = gain >= min_gain and p95_reranked <= limit
    return {
        "rerank": keep,
        "mrr_gain": gain, "p95_ms": p95_reranked, "p95_added_ms": p95_reranked - p95_fused,
        "min_mrr_gain": min_gain, "p95_budget_ms": limit,
        "rule": f"keep the reranker only when mrr_gain {gain:+.4f} >= {min_gain} and p95 latency {p95_reranked:.3f} ms <= {limit} ms budget",
        "reason": ("kept: the gain pays for the added latency" if keep else "dropped: " + ("the MRR gain is below the declared minimum" if gain < min_gain else "p95 latency is over the budget")),
    }
