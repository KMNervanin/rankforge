"""Approximate index: multi-probe LSH over one global table with an iterative, filter-aware scan.

`lists` buckets come from ceil(log2(lists)) random hyperplanes; a query's buckets are ordered by how
little its projections would have to move to land in them (multi-probe). The scan reads `probes`
buckets, applies the outpost filter inside the scan and keeps opening buckets until k matches are
found or every bucket has been read, so a filtered query never silently loses results.
"""
import math
import operator
import random
import time
from itertools import combinations


def unit(vector):
    length = math.sqrt(sum(value * value for value in vector))
    return [value / length for value in vector] if length else list(vector)


def dot(a, b):
    return sum(map(operator.mul, a, b))


def percentile(values, fraction):
    ordered = sorted(values)
    return ordered[max(0, math.ceil(fraction * len(ordered)) - 1)] if ordered else 0.0


class Row:
    __slots__ = ("identifier", "outpost", "unit")

    def __init__(self, identifier, outpost, vector):
        self.identifier, self.outpost, self.unit = str(identifier), outpost, unit(vector)


class ExactIndex:
    def __init__(self, dim):
        self.dim = dim
        self.rows = []
        self.build_seconds = 0.0

    def build(self, items):
        started = time.perf_counter()
        self.rows = [Row(item["id"], item["outpost"], item["vector"]) for item in items]
        self.build_seconds = time.perf_counter() - started
        return self

    def count(self, outpost=None):
        return sum(1 for row in self.rows if outpost is None or row.outpost == outpost)

    def search(self, query, k, *, outpost=None):
        q = unit(query)
        candidates = [row for row in self.rows if outpost is None or row.outpost == outpost]
        results = sorted(((row.identifier, dot(q, row.unit)) for row in candidates), key=lambda pair: (-pair[1], pair[0]))[:k]
        return {"results": results, "truncated": len(results) < k, "scanned": len(candidates)}


class ApproxIndex:
    def __init__(self, dim, *, seed, lists=16, probes=1):
        self.dim, self.seed, self.lists, self.probes = dim, seed, int(lists), int(probes)
        self.bits = max(1, min(12, math.ceil(math.log2(max(2, self.lists)))))
        rng = random.Random(seed)
        self.planes = [unit([rng.gauss(0, 1) for _ in range(dim)]) for _ in range(self.bits)]
        self.buckets = {}
        self.sizes = {}
        self.build_seconds = 0.0

    @property
    def params(self):
        return {"lists": self.lists, "probes": self.probes}

    def key(self, u):
        return sum(1 << bit for bit, plane in enumerate(self.planes) if dot(u, plane) >= 0)

    def build(self, items):
        started = time.perf_counter()
        self.buckets, self.sizes = {}, {}
        for item in items:
            row = Row(item["id"], item["outpost"], item["vector"])
            self.buckets.setdefault(self.key(row.unit), []).append(row)
            self.sizes[row.outpost] = self.sizes.get(row.outpost, 0) + 1
        self.build_seconds = time.perf_counter() - started
        return self

    def count(self, outpost=None):
        return sum(self.sizes.values()) if outpost is None else self.sizes.get(outpost, 0)

    def probe_order(self, q):
        """Every bucket key, cheapest flips first: the cost of a bucket is the projection margin of the bits it flips."""
        margins = [dot(q, plane) for plane in self.planes]
        base = sum(1 << bit for bit, margin in enumerate(margins) if margin >= 0)
        order = []
        for flipped in range(self.bits + 1):
            for bits in combinations(range(self.bits), flipped):
                order.append((sum(abs(margins[bit]) for bit in bits), base ^ sum(1 << bit for bit in bits)))
        order.sort()
        return [key for _, key in order]

    def search(self, query, k, *, outpost=None):
        q = unit(query)
        found, scanned, opened = [], 0, 0
        for key in self.probe_order(q):
            if opened >= self.probes and len(found) >= k:
                break
            opened += 1
            for row in self.buckets.get(key, ()):
                if outpost is None or row.outpost == outpost:
                    found.append((row.identifier, dot(q, row.unit)))
                    scanned += 1
        found.sort(key=lambda pair: (-pair[1], pair[0]))
        results = found[:k]
        return {"results": results, "truncated": len(results) < k, "scanned": scanned}


def measure(exact, approx, queries, k):
    per_query = []
    for query in queries:
        outpost = query.get("outpost")
        tick = time.perf_counter()
        truth = exact.search(query["vector"], k, outpost=outpost)
        exact_ms = (time.perf_counter() - tick) * 1000
        tick = time.perf_counter()
        got = approx.search(query["vector"], k, outpost=outpost)
        approx_ms = (time.perf_counter() - tick) * 1000
        truth_ids = {identifier for identifier, _ in truth["results"]}
        ids = [identifier for identifier, _ in got["results"]]
        recall = len(truth_ids.intersection(ids)) / len(truth_ids) if truth_ids else 1.0
        per_query.append({"outpost": outpost, "ids": ids, "returned": len(ids), "truncated": got["truncated"], "recall": recall,
                          "scanned": got["scanned"], "exact_scanned": truth["scanned"], "approx_ms": approx_ms, "exact_ms": exact_ms})
    count = max(1, len(per_query))
    recalls = [entry["recall"] for entry in per_query] or [1.0]
    grouped = {}
    for entry in per_query:
        if entry["outpost"] is not None:
            grouped.setdefault(entry["outpost"], []).append(entry["recall"])
    report = {"k": k, "queries": len(per_query), "params": approx.params, "build_seconds": approx.build_seconds, "per_query": per_query,
              "recall_mean": sum(recalls) / len(recalls), "recall_min": min(recalls),
              "scanned_mean": sum(entry["scanned"] for entry in per_query) / count,
              "exact_scanned_mean": sum(entry["exact_scanned"] for entry in per_query) / count,
              "per_outpost": {outpost: sum(values) / len(values) for outpost, values in grouped.items()}}
    for prefix in ("approx", "exact"):
        values = [entry[f"{prefix}_ms"] for entry in per_query]
        report[f"{prefix}_p50_ms"], report[f"{prefix}_p95_ms"] = percentile(values, 0.5), percentile(values, 0.95)
    return report


def tune(exact, items, queries, k, *, grid, bound, seed):
    candidates, chosen = [], None
    for params in grid:
        report = measure(exact, ApproxIndex(exact.dim, seed=seed, **params).build(items), queries, k)
        meets = report["recall_mean"] >= bound
        candidates.append({"params": dict(params), "recall_mean": report["recall_mean"], "scanned_mean": report["scanned_mean"],
                           "approx_p50_ms": report["approx_p50_ms"], "build_seconds": report["build_seconds"], "meets": meets})
        if meets and (chosen is None or report["scanned_mean"] < chosen["report"]["scanned_mean"]):
            chosen = {"params": dict(params), "report": report}
    return {"params": chosen["params"] if chosen else None, "report": chosen["report"] if chosen else None, "candidates": candidates, "bound": bound}
