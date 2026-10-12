"""Hybrid retriever: dataclasses, exact Fraction arithmetic, heapq for the ordering, statistics-free percentiles."""
import heapq
import math
from collections import defaultdict
from dataclasses import dataclass, field
from fractions import Fraction


@dataclass(order=True)
class Entry:
    key: tuple
    doc_id: str = field(compare=False)
    score: Fraction = field(compare=False)

    @classmethod
    def of(cls, doc_id, score):
        return cls((-score, doc_id), doc_id, score)


def _ranked(scores):
    entries = [Entry.of(doc_id, score) for doc_id, score in scores.items()]
    return [(entry.doc_id, float(entry.score)) for entry in heapq.nsmallest(len(entries), entries)]


def rrf(rankings, k=60, weights=None):
    k = Fraction(str(k))
    if k <= 0:
        raise ValueError("k must be positive")
    weights = [Fraction(1)] * len(rankings) if weights is None else [Fraction(str(w)) for w in weights]
    if len(weights) != len(rankings):
        raise ValueError("one weight per ranking")
    scores = defaultdict(Fraction)
    for ranking, weight in zip(rankings, weights):
        for position, (doc_id, _score) in enumerate(ranking, start=1):
            scores[doc_id] += weight / (k + position)
    return _ranked(scores)


def weighted(rankings, weights):
    if len(weights) != len(rankings):
        raise ValueError("one weight per ranking")
    scores = defaultdict(Fraction)
    for ranking, weight in zip(rankings, weights):
        if not ranking:
            continue
        values = [Fraction(str(score)) for _doc_id, score in ranking]
        low, high = min(values), max(values)
        for (doc_id, _score), value in zip(ranking, values):
            scaled = Fraction(1) if high == low else (value - low) / (high - low)
            scores[doc_id] += Fraction(str(weight)) * scaled
    return _ranked(scores)


def rerank(candidates, query, score_fn, top_n):
    if top_n < 0:
        raise ValueError("top_n must be non-negative")
    head = candidates[:top_n]
    scored = {doc_id: Fraction(str(score_fn(query, doc_id))) for doc_id, _score in head}
    return _ranked(scored) + [(doc_id, score) for doc_id, score in candidates[len(head):]]


@dataclass
class Outcome:
    id: str
    fused: list
    reranked: list
    expected: str
    fused_ms: float
    reranked_ms: float

    def rank(self, ids):
        return ids.index(self.expected) + 1 if self.expected in ids else None

    def row(self):
        return {"id": self.id, "fused": self.fused, "reranked": self.reranked,
                "hit": {"fused": self.rank(self.fused), "reranked": self.rank(self.reranked)},
                "latency_ms": {"fused": self.fused_ms, "reranked": self.reranked_ms}}


def reciprocal_mean(ranks):
    total = sum((Fraction(1, rank) for rank in ranks if rank), Fraction(0))
    return float(total / len(ranks)) if ranks else 0.0


def nearest_rank(samples, p):
    if not samples:
        raise ValueError("no samples")
    ordered = sorted(samples)
    return ordered[max(1, math.ceil(Fraction(p, 100) * len(ordered))) - 1]


def measure(queries, retrievers, *, clock, score_fn, top_n, k=60):
    outcomes = []
    for query in queries:
        t0 = clock()
        fused = rrf([retriever(query["text"]) for retriever in retrievers], k)
        t1 = clock()
        reranked = rerank(fused, query["text"], score_fn, top_n)
        t2 = clock()
        outcomes.append(Outcome(query["id"], [d for d, _ in fused], [d for d, _ in reranked], query["expected"], (t1 - t0) * 1000, (t2 - t0) * 1000))
    rows = [outcome.row() for outcome in outcomes]
    samples = {"fused": [o.fused_ms for o in outcomes], "reranked": [o.reranked_ms for o in outcomes]}
    report = {"k": k, "top_n": top_n, "queries": rows, "samples": samples, "mrr": {}, "p50_ms": {}, "p95_ms": {}}
    for stage in ("fused", "reranked"):
        report["mrr"][stage] = reciprocal_mean([row["hit"][stage] for row in rows])
        report["p50_ms"][stage] = nearest_rank(samples[stage], 50)
        report["p95_ms"][stage] = nearest_rank(samples[stage], 95)
    return report


def decide(report, budget):
    samples = report.get("samples") or {}
    for stage in ("fused", "reranked"):
        if not samples.get(stage):
            raise ValueError(f"no {stage} latency samples in the report; an unmeasured reranker is never adopted")
    ranks = {stage: [row["hit"][stage] for row in report["queries"]] for stage in ("fused", "reranked")}
    gain = reciprocal_mean(ranks["reranked"]) - reciprocal_mean(ranks["fused"])
    p95 = {stage: nearest_rank(samples[stage], 95) for stage in ("fused", "reranked")}
    minimum, limit = float(budget["min_mrr_gain"]), float(budget["p95_ms"])
    keep = gain >= minimum and p95["reranked"] <= limit
    verdict = "keep" if keep else "drop"
    return {
        "rerank": keep, "mrr_gain": gain, "p95_ms": p95["reranked"], "p95_added_ms": p95["reranked"] - p95["fused"],
        "min_mrr_gain": minimum, "p95_budget_ms": limit,
        "rule": f"{verdict}: MRR gain {gain:.4f} vs minimum {minimum}; p95 {p95['reranked']:.3f} ms vs budget {limit} ms; keep only when both hold",
    }
