"""Approximate index: IVF partitions (spherical k-means) with one partial index per outpost.

A filtered query searches only its outpost's partition (filter, then search). An unfiltered query
pools the lists of every partition. Either way the scan starts with `probes` lists and keeps
widening to the next-best list until k matches are in hand or the candidates are exhausted.
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


def nearest_rank(values, fraction):
    ordered = sorted(values)
    return ordered[max(0, math.ceil(fraction * len(ordered)) - 1)] if ordered else 0.0


class ExactIndex:
    def __init__(self, dim):
        self.dim = dim
        self.rows = []
        self.by_outpost = {}
        self.build_seconds = 0.0

    def build(self, items):
        started = time.perf_counter()
        self.rows = [(str(item["id"]), item["outpost"], unit(item["vector"])) for item in items]
        self.by_outpost = {}
        for row in self.rows:
            self.by_outpost.setdefault(row[1], []).append(row)
        self.build_seconds = time.perf_counter() - started
        return self

    def count(self, outpost=None):
        return len(self.rows) if outpost is None else len(self.by_outpost.get(outpost, []))

    def search(self, query, k, *, outpost=None):
        q = unit(query)
        rows = self.rows if outpost is None else self.by_outpost.get(outpost, [])
        results = top([(identifier, dot(q, u)) for identifier, _, u in rows], k)
        return {"results": results, "truncated": len(results) < k, "scanned": len(rows)}


class Partition:
    """IVF over the rows of one outpost: k-means centroids on unit vectors, one list per centroid."""

    def __init__(self, rows, lists, rng, iterations=4, sample=1024):
        self.rows = rows
        count = min(lists, len(rows))
        training = rows if len(rows) <= sample else rng.sample(rows, sample)
        centroids = [row[2] for row in rng.sample(rows, count)]
        for _ in range(iterations):
            sums = [[0.0] * len(rows[0][2]) for _ in centroids]
            members = [0] * count
            for _, _, u in training:
                best = max(range(count), key=lambda index: dot(u, centroids[index]))
                members[best] += 1
                sums[best] = list(map(operator.add, sums[best], u))
            centroids = [unit(sums[index]) if members[index] else centroids[index] for index in range(count)]
        self.centroids = centroids
        self.lists = [[] for _ in centroids]
        for row in rows:
            self.lists[max(range(count), key=lambda index: dot(row[2], centroids[index]))].append(row)


class ApproxIndex:
    def __init__(self, dim, *, seed, lists=16, probes=1):
        self.dim, self.seed, self.lists, self.probes = dim, seed, int(lists), int(probes)
        self.partitions = {}
        self.build_seconds = 0.0

    @property
    def params(self):
        return {"lists": self.lists, "probes": self.probes}

    def build(self, items):
        started = time.perf_counter()
        rng = random.Random(self.seed)
        grouped = {}
        for item in items:
            grouped.setdefault(item["outpost"], []).append((str(item["id"]), item["outpost"], unit(item["vector"])))
        self.partitions = {outpost: Partition(rows, self.lists, rng) for outpost, rows in sorted(grouped.items())}
        self.build_seconds = time.perf_counter() - started
        return self

    def count(self, outpost=None):
        return sum(len(partition.rows) for name, partition in self.partitions.items() if outpost is None or name == outpost)

    def search(self, query, k, *, outpost=None):
        q = unit(query)
        partitions = list(self.partitions.values()) if outpost is None else [self.partitions[outpost]] if outpost in self.partitions else []
        order = []
        for partition in partitions:
            order.extend((dot(q, centroid), partition, index) for index, centroid in enumerate(partition.centroids))
        order.sort(key=lambda entry: -entry[0])
        found, scanned, position = [], 0, 0
        # Iterative scan: the first `probes` lists always, then one more list at a time until k matches or nothing is left.
        while position < len(order) and (position < self.probes or len(found) < k):
            _, partition, index = order[position]
            for identifier, _, u in partition.lists[index]:
                found.append((identifier, dot(q, u)))
            scanned += len(partition.lists[index])
            position += 1
        results = top(found, k)
        return {"results": results, "truncated": len(results) < k, "scanned": scanned}


def measure(exact, approx, queries, k):
    per_query = []
    for query in queries:
        outpost = query.get("outpost")
        started = time.perf_counter()
        wanted = exact.search(query["vector"], k, outpost=outpost)
        exact_ms = (time.perf_counter() - started) * 1000
        started = time.perf_counter()
        got = approx.search(query["vector"], k, outpost=outpost)
        approx_ms = (time.perf_counter() - started) * 1000
        wanted_ids = [identifier for identifier, _ in wanted["results"]]
        ids = [identifier for identifier, _ in got["results"]]
        recall = len(set(ids) & set(wanted_ids)) / len(wanted_ids) if wanted_ids else 1.0
        per_query.append({"outpost": outpost, "ids": ids, "returned": len(ids), "truncated": got["truncated"], "recall": recall,
                          "scanned": got["scanned"], "exact_scanned": wanted["scanned"], "approx_ms": approx_ms, "exact_ms": exact_ms})
    recalls = [entry["recall"] for entry in per_query]
    per_outpost = {}
    for entry in per_query:
        if entry["outpost"] is not None:
            per_outpost.setdefault(entry["outpost"], []).append(entry["recall"])
    return {
        "k": k, "queries": len(per_query), "params": approx.params, "build_seconds": approx.build_seconds, "per_query": per_query,
        "recall_mean": sum(recalls) / len(recalls) if recalls else 1.0, "recall_min": min(recalls) if recalls else 1.0,
        "scanned_mean": sum(entry["scanned"] for entry in per_query) / max(1, len(per_query)),
        "exact_scanned_mean": sum(entry["exact_scanned"] for entry in per_query) / max(1, len(per_query)),
        "approx_p50_ms": nearest_rank([entry["approx_ms"] for entry in per_query], 0.5), "approx_p95_ms": nearest_rank([entry["approx_ms"] for entry in per_query], 0.95),
        "exact_p50_ms": nearest_rank([entry["exact_ms"] for entry in per_query], 0.5), "exact_p95_ms": nearest_rank([entry["exact_ms"] for entry in per_query], 0.95),
        "per_outpost": {outpost: sum(values) / len(values) for outpost, values in per_outpost.items()},
    }


def tune(exact, items, queries, k, *, grid, bound, seed):
    candidates, best = [], None
    for params in grid:
        approx = ApproxIndex(exact.dim, seed=seed, **params).build(items)
        report = measure(exact, approx, queries, k)
        meets = report["recall_mean"] >= bound
        candidates.append({"params": dict(params), "recall_mean": report["recall_mean"], "scanned_mean": report["scanned_mean"],
                           "approx_p50_ms": report["approx_p50_ms"], "build_seconds": report["build_seconds"], "meets": meets})
        if meets and (best is None or report["scanned_mean"] < best[1]["scanned_mean"]):
            best = (dict(params), report)
    return {"params": best[0] if best else None, "report": best[1] if best else None, "candidates": candidates, "bound": bound}
