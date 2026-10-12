"""Approximate index for the archive with an access filter per outpost.

Starter: a list-based approximate index that probes a few lists, takes its best candidates and
filters them by outpost afterwards; its report times the searches but never measures what the
index loses, and the params come from the first row of the grid. See LEARN.md for the contract.
"""
import math
import operator
import random
import time


def unit(vector):
    length = math.sqrt(sum(value * value for value in vector))
    return [value / length for value in vector] if length else list(vector)


def dot(a, b):
    return sum(map(operator.mul, a, b))


def top(scored, k):
    scored.sort(key=lambda pair: (-pair[1], pair[0]))
    return scored[:k]


class ExactIndex:
    def __init__(self, dim):
        self.dim = dim
        self.rows = []
        self.build_seconds = 0.0

    def build(self, items):
        self.rows = [(str(item["id"]), item["outpost"], unit(item["vector"])) for item in items]
        return self

    def count(self, outpost=None):
        return sum(1 for row in self.rows if outpost is None or row[1] == outpost)

    def search(self, query, k, *, outpost=None):
        q = unit(query)
        rows = [row for row in self.rows if outpost is None or row[1] == outpost]
        results = top([(identifier, dot(q, u)) for identifier, _, u in rows], k)
        return {"results": results, "truncated": False, "scanned": len(rows)}


class ApproxIndex:
    def __init__(self, dim, *, seed, lists=16, probes=1):
        self.dim, self.seed, self.lists, self.probes = dim, seed, int(lists), int(probes)
        self.centroids, self.buckets = [], []
        self.build_seconds = 0.0

    @property
    def params(self):
        return {"lists": self.lists, "probes": self.probes}

    def build(self, items):
        rng = random.Random(self.seed)
        rows = [(str(item["id"]), item["outpost"], unit(item["vector"])) for item in items]
        self.centroids = [row[2] for row in rng.sample(rows, min(self.lists, len(rows)))]
        self.buckets = [[] for _ in self.centroids]
        for row in rows:
            self.buckets[max(range(len(self.centroids)), key=lambda index: dot(row[2], self.centroids[index]))].append(row)
        return self

    def count(self, outpost=None):
        return sum(1 for bucket in self.buckets for row in bucket if outpost is None or row[1] == outpost)

    def search(self, query, k, *, outpost=None):
        q = unit(query)
        order = sorted(range(len(self.centroids)), key=lambda index: -dot(q, self.centroids[index]))
        candidates, scanned = [], 0
        for index in order[: self.probes]:
            candidates.extend((identifier, home, dot(q, u)) for identifier, home, u in self.buckets[index])
            scanned += len(self.buckets[index])
        best = top([(identifier, score) for identifier, _, score in candidates], k)
        if outpost is not None:
            allowed = {identifier for identifier, home, _ in candidates if home == outpost}
            best = [(identifier, score) for identifier, score in best if identifier in allowed]
        return {"results": best, "truncated": False, "scanned": scanned}


def measure(exact, approx, queries, k):
    per_query = []
    for query in queries:
        started = time.perf_counter()
        exact.search(query["vector"], k, outpost=query.get("outpost"))
        exact_ms = (time.perf_counter() - started) * 1000
        started = time.perf_counter()
        got = approx.search(query["vector"], k, outpost=query.get("outpost"))
        approx_ms = (time.perf_counter() - started) * 1000
        per_query.append({"outpost": query.get("outpost"), "returned": len(got["results"]), "scanned": got["scanned"], "approx_ms": approx_ms, "exact_ms": exact_ms})
    approx_ms = sorted(entry["approx_ms"] for entry in per_query)
    exact_ms = sorted(entry["exact_ms"] for entry in per_query)
    return {"k": k, "queries": len(per_query), "params": approx.params, "per_query": per_query,
            "approx_p50_ms": approx_ms[len(approx_ms) // 2], "exact_p50_ms": exact_ms[len(exact_ms) // 2]}


def tune(exact, items, queries, k, *, grid, bound, seed):
    # The grid is ordered cheapest first; the first entry is the one to ship.
    return {"params": dict(grid[0]), "report": None, "candidates": [], "bound": bound}
