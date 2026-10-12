"""Hybrid retriever for the archive: lexical and dense results into one ranking, then a reranker.

Starter: it fuses by adding the raw scores of both lists, reranks every candidate it has, and keeps
the reranker because the MRR went up. See LEARN.md for the complete contract that Verify checks.
"""
import time


def rrf(rankings, k=60):
    scores = {}
    for ranking in rankings:
        for doc_id, score in ranking:
            scores[doc_id] = scores.get(doc_id, 0.0) + float(score)
    return sorted(scores.items(), key=lambda item: -item[1])


def weighted(rankings, weights):
    scores = {}
    for ranking, weight in zip(rankings, weights):
        for doc_id, score in ranking:
            scores[doc_id] = scores.get(doc_id, 0.0) + weight * float(score)
    return sorted(scores.items(), key=lambda item: -item[1])


def rerank(candidates, query, score_fn, top_n):
    scored = [(doc_id, float(score_fn(query, doc_id))) for doc_id, _score in candidates]
    return sorted(scored, key=lambda item: -item[1])


def hit_rank(ids, expected):
    return ids.index(expected) + 1 if expected in ids else None


def mrr(ranks):
    return sum(1.0 / rank for rank in ranks if rank) / max(1, len(ranks))


def measure(queries, retrievers, *, clock, score_fn, top_n, k=60):
    rows = []
    for query in queries:
        started = time.perf_counter()
        fused = rrf([retriever(query["text"]) for retriever in retrievers], k)
        fused_ms = (time.perf_counter() - started) * 1000
        reranked = rerank(fused, query["text"], score_fn, top_n)
        reranked_ms = (time.perf_counter() - started) * 1000
        fused_ids = [doc_id for doc_id, _score in fused]
        reranked_ids = [doc_id for doc_id, _score in reranked]
        rows.append({
            "id": query["id"], "fused": fused_ids, "reranked": reranked_ids,
            "hit": {"fused": hit_rank(fused_ids, query["expected"]), "reranked": hit_rank(reranked_ids, query["expected"])},
            "latency_ms": {"fused": fused_ms, "reranked": reranked_ms},
        })
    samples = {stage: [row["latency_ms"][stage] for row in rows] for stage in ("fused", "reranked")}
    return {
        "k": k, "top_n": top_n, "queries": rows, "samples": samples,
        "mrr": {stage: mrr([row["hit"][stage] for row in rows]) for stage in ("fused", "reranked")},
        "p50_ms": {stage: sum(samples[stage]) / len(samples[stage]) for stage in ("fused", "reranked")},
        "p95_ms": {stage: max(samples[stage]) for stage in ("fused", "reranked")},
    }


def decide(report, budget):
    gain = report["mrr"]["reranked"] - report["mrr"]["fused"]
    return {
        "rerank": gain > 0,
        "mrr_gain": gain, "p95_ms": report.get("p95_ms", {}).get("reranked", 0.0), "p95_added_ms": 0.0,
        "min_mrr_gain": budget.get("min_mrr_gain", 0.0), "p95_budget_ms": budget.get("p95_ms", 0.0),
        "rule": "keep the reranker when MRR rose",
    }
