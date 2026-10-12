"""Approximate index checks for the Annindex mission; run outside the learner workspace.

Nothing here calls a model. Verify generates seeded vectors across three outposts, computes every
exact top-k itself with cosine on its own unit vectors, plants near-duplicates in the wrong outpost,
recomputes recall from the ids the learner's index returned, and grows the fixture tenfold at the end.
"""
import importlib.util
import json
import math
import operator
import os
import random
import sys
import time

MISSION, WORKSPACE = sys.argv[1:3]
CHECKS = []
DIM, K, BOUND = 32, 10, 0.9
OUTPOSTS = {"alpha": 1500, "beta": 1400, "gamma": 7}
CENTERS = 24
NOISE = 0.12
GRID = [{"lists": 32, "probes": probes} for probes in (1, 2, 4, 8, 16)]
TRANSFER_GRID = [{"lists": 64, "probes": probes} for probes in (4, 16, 32, 48)]
TRANSFER_BUDGET = 28.0


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def check(name, operation, optional=False):
    # An optional check is the hidden bonus of a mission: it can only add, it never fails the run.
    flag = {"optional": True} if optional else {}
    try:
        detail = operation()
        CHECKS.append({"name": name, "passed": True, "detail": detail or "Index results and the recall report verified.", **flag})
    except Exception as error:
        CHECKS.append({"name": name, "passed": False, "detail": f"{type(error).__name__}: {error}"[:1500], **flag})


def unit(vector):
    length = math.sqrt(sum(value * value for value in vector))
    return [value / length for value in vector] if length else list(vector)


def dot(a, b):
    return sum(map(operator.mul, a, b))


def near(a, b, tolerance=1e-9):
    return abs(float(a) - float(b)) <= tolerance


def generate(seed, scale=1):
    """Clustered vectors of varied length: cosine and a bare dot product disagree on purpose."""
    rng = random.Random(seed)
    centers = [unit([rng.gauss(0, 1) for _ in range(DIM)]) for _ in range(CENTERS)]

    def vector():
        center = rng.choice(centers)
        length = rng.uniform(0.4, 2.5)
        return [length * (value + rng.gauss(0, NOISE)) for value in center]

    items = []
    for outpost, count in OUTPOSTS.items():
        for number in range(count * scale):
            items.append({"id": f"{outpost}-{number:05d}", "outpost": outpost, "vector": vector()})
    return rng, items, vector


def plant(rng, items, vector, outpost, count=8):
    """Near-duplicates of a query vector stored in a large outpost other than the one the query filters on."""
    others = [name for name in ("alpha", "beta") if name != outpost] or ["alpha", "beta"]
    planted = []
    for number in range(count):
        home = others[number % len(others)]
        item = {"id": f"dup-{outpost}-{number}", "outpost": home, "vector": [value + rng.gauss(0, 0.004) for value in vector]}
        items.append(item)
        planted.append(item["id"])
    return planted


class Reference:
    def __init__(self, items):
        self.rows = [(item["id"], item["outpost"], unit(item["vector"])) for item in items]
        self.outpost_of = {item["id"]: item["outpost"] for item in items}

    def count(self, outpost=None):
        return sum(1 for row in self.rows if outpost is None or row[1] == outpost)

    def top(self, vector, k, outpost=None):
        q = unit(vector)
        scored = [(identifier, dot(q, u)) for identifier, home, u in self.rows if outpost is None or home == outpost]
        scored.sort(key=lambda pair: (-pair[1], pair[0]))
        return scored[:k]


def results_of(result):
    require(isinstance(result, dict), f"search must return a dict, got {type(result).__name__}")
    for key in ("results", "truncated", "scanned"):
        require(key in result, f"search result is missing {key!r}")
    pairs = result["results"]
    require(isinstance(pairs, list) and all(isinstance(pair, (list, tuple)) and len(pair) == 2 for pair in pairs), "results must be a list of (id, score) pairs")
    require(isinstance(result["truncated"], bool), "truncated must be a bool")
    require(type(result["scanned"]) is int and result["scanned"] >= 0, "scanned must be a non-negative integer")
    return [(str(identifier), float(score)) for identifier, score in pairs], result["truncated"], result["scanned"]


def recall_of(ids, exact):
    wanted = [identifier for identifier, _ in exact]
    return len(set(ids) & set(wanted)) / len(wanted) if wanted else 1.0


def nearest_rank(values, fraction):
    ordered = sorted(values)
    return ordered[max(0, math.ceil(fraction * len(ordered)) - 1)]


def trial():
    require(MISSION == "annindex", "Unknown mission")
    sys.path.insert(0, WORKSPACE)
    spec = importlib.util.spec_from_file_location("candidate_annindex", os.path.join(WORKSPACE, "annindex.py"))
    if spec is None or spec.loader is None:
        raise ImportError("Cannot load annindex.py")
    candidate = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = candidate
    spec.loader.exec_module(candidate)
    for name in ("ExactIndex", "ApproxIndex"):
        require(isinstance(getattr(candidate, name, None), type), f"annindex.py must define the class {name}")
    for name in ("measure", "tune"):
        require(callable(getattr(candidate, name, None)), f"annindex.py must define {name}(...)")

    seed = random.randrange(1, 1_000_000)
    rng, items, vector = generate(seed)
    leak_queries = []
    for outpost in ("alpha", "beta", "gamma", "alpha", "beta", "alpha"):
        query = vector()
        leak_queries.append((query, outpost, plant(rng, items, query, outpost)))
    rng.shuffle(items)
    reference = Reference(items)
    total = len(items)
    queries = [{"vector": vector(), "outpost": None} for _ in range(10)]
    queries += [{"vector": vector(), "outpost": "alpha"} for _ in range(10)]
    queries += [{"vector": vector(), "outpost": "beta"} for _ in range(8)]
    queries += [{"vector": vector(), "outpost": "gamma"} for _ in range(2)]
    rng.shuffle(queries)
    expected = [reference.top(query["vector"], K, query["outpost"]) for query in queries]

    def build_exact():
        started = time.perf_counter()
        exact = candidate.ExactIndex(DIM).build(items)
        return exact, time.perf_counter() - started

    def build_approx(params):
        started = time.perf_counter()
        approx = candidate.ApproxIndex(DIM, seed=seed, **params).build(items)
        return approx, time.perf_counter() - started

    def exact_search():
        exact, _ = build_exact()
        require(exact.count() == total, f"count() must be {total}, got {exact.count()!r}")
        require(exact.count("gamma") == reference.count("gamma"), f"count('gamma') must be {reference.count('gamma')}, got {exact.count('gamma')!r}")
        compared = 0
        for query, wanted in zip(queries, expected):
            if query["outpost"] == "gamma":
                continue
            pairs, truncated, scanned = results_of(exact.search(query["vector"], K, outpost=query["outpost"]))
            require([identifier for identifier, _ in pairs] == [identifier for identifier, _ in wanted], f"Exact top-{K} for outpost {query['outpost']!r} differs from the reference: {[i for i, _ in pairs][:4]}… vs {[i for i, _ in wanted][:4]}…")
            require(all(near(score, want) for (_, score), (_, want) in zip(pairs, wanted)), "Scores must be cosine similarity within 1e-9; a bare dot product on vectors of different length is not")
            require(truncated is False, "truncated must be False when the outpost holds at least k passages")
            require(scanned == reference.count(query["outpost"]), f"scanned must be the number of vectors compared ({reference.count(query['outpost'])}), got {scanned}")
            compared += 1
        for query, outpost, planted in leak_queries[:2]:
            pairs, _, _ = results_of(exact.search(query, K, outpost=outpost))
            require(all(reference.outpost_of[identifier] == outpost for identifier, _ in pairs), f"Exact search for outpost {outpost!r} returned another outpost's passage")
        return f"{compared} exact top-{K} results matched the reference on {total} vectors, filtered and unfiltered."
    check("Exact search matches the reference top-k with and without the access filter", exact_search)

    def leak():
        approx, _ = build_approx(GRID[0])
        for query, outpost, planted in leak_queries:
            pairs, truncated, _ = results_of(approx.search(query, K, outpost=outpost))
            foreign = [identifier for identifier, _ in pairs if reference.outpost_of.get(identifier) != outpost]
            require(not foreign, f"Filtered search for outpost {outpost!r} returned {foreign[:3]} from another outpost ({len(planted)} near-duplicates were planted there)")
        return f"{len(leak_queries)} filtered queries with {sum(len(p) for _, _, p in leak_queries)} planted cross-outpost duplicates returned only the requested outpost."
    check("A filtered approximate query never returns another outpost's passage", leak)

    def fewer():
        approx, _ = build_approx(GRID[0])
        exact, _ = build_exact()
        gamma = {identifier for identifier, home in reference.outpost_of.items() if home == "gamma"}
        for label, index in (("ApproxIndex", approx), ("ExactIndex", exact)):
            pairs, truncated, _ = results_of(index.search(vector(), K, outpost="gamma"))
            require(len(pairs) == len(gamma), f"{label}: outpost gamma holds {len(gamma)} passages, a query for {K} must return all {len(gamma)}, got {len(pairs)}")
            require({identifier for identifier, _ in pairs} == gamma, f"{label}: the {len(gamma)} gamma passages must all be returned")
            require(truncated is True, f"{label}: truncated must be True when fewer than k exist for the outpost")
            pairs, truncated, _ = results_of(index.search(vector(), 3, outpost="gamma"))
            require(len(pairs) == 3 and truncated is False, f"{label}: k=3 on gamma must return 3 with truncated False, got {len(pairs)} and {truncated}")
        for query, outpost, planted in leak_queries:
            for request in (K, 25):
                pairs, truncated, _ = results_of(approx.search(query, request, outpost=outpost))
                have = reference.count(outpost)
                wanted = min(request, have)
                require(len(pairs) == wanted, f"Outpost {outpost!r} holds {have} passages; a filtered query for {request} returned {len(pairs)} (the post-filter defect: candidates picked before the filter, the rest dropped silently)")
                require(truncated is (have < request), f"truncated must be {have < request} for k={request} on outpost {outpost!r}")
        pairs, truncated, _ = results_of(approx.search(vector(), total + 5, outpost=None))
        require(len(pairs) == total and truncated is True, f"k={total + 5} on {total} vectors must return all {total} with truncated True, got {len(pairs)} and {truncated}")
        return f"Every filtered query returned min(k, outpost size) with truncated set exactly when the outpost held fewer; gamma holds {len(gamma)}."
    check("A filtered query returns k results or says fewer exist", fewer)

    def recall():
        exact, _ = build_exact()
        started = time.perf_counter()
        choice = candidate.tune(exact, items, queries, K, grid=GRID, bound=BOUND, seed=seed)
        tune_seconds = time.perf_counter() - started
        require(isinstance(choice, dict) and "params" in choice and "candidates" in choice, "tune must return {params, report, candidates}")
        candidates = choice["candidates"]
        require(isinstance(candidates, list) and len(candidates) == len(GRID), f"candidates must list every grid entry in order ({len(GRID)}), got {len(candidates) if isinstance(candidates, list) else candidates!r}")
        measured = []
        for params, entry in zip(GRID, candidates):
            require(isinstance(entry, dict) and entry.get("params") == params, f"candidate {entry!r} does not match grid entry {params}")
            approx, _ = build_approx(params)
            recalls, scanned = [], []
            for query, wanted in zip(queries, expected):
                pairs, _, count = results_of(approx.search(query["vector"], K, outpost=query["outpost"]))
                recalls.append(recall_of([identifier for identifier, _ in pairs], wanted))
                scanned.append(count)
            mean_recall, mean_scanned = sum(recalls) / len(recalls), sum(scanned) / len(scanned)
            require(near(entry.get("recall_mean"), mean_recall, 1e-9), f"candidate {params}: recall_mean {entry.get('recall_mean')!r} differs from Verify's recomputation {mean_recall:.4f}")
            require(near(entry.get("scanned_mean"), mean_scanned, 1e-9), f"candidate {params}: scanned_mean {entry.get('scanned_mean')!r} differs from Verify's recomputation {mean_scanned:.2f}")
            require(entry.get("meets") is (mean_recall >= BOUND), f"candidate {params}: meets must be {mean_recall >= BOUND} for recall {mean_recall:.4f} against the bound {BOUND}")
            measured.append((params, mean_recall, mean_scanned))
        meeting = [(scanned, position, params) for position, (params, mean_recall, scanned) in enumerate(measured) if mean_recall >= BOUND]
        require(meeting, f"No grid entry reached recall@{K} {BOUND} on this fixture: {[(p, round(r, 3)) for p, r, _ in measured]}. The index must reach the bound somewhere in the grid.")
        cheapest = min(meeting)[2]
        require(choice["params"] == cheapest, f"tune must choose the cheapest params meeting the bound ({cheapest}), chose {choice['params']!r}; measured {[(p, round(r, 3), round(s)) for p, r, s in measured]}")
        approx, _ = build_approx(cheapest)
        report = candidate.measure(exact, approx, queries, K)
        require(isinstance(report, dict) and isinstance(report.get("per_query"), list) and len(report["per_query"]) == len(queries), f"measure must return a report with one per_query entry per query ({len(queries)})")
        require(report.get("k") == K and report.get("params") == cheapest, "The report must carry k and the index params")
        recalls = []
        for entry, query, wanted in zip(report["per_query"], queries, expected):
            for key in ("ids", "recall", "returned", "truncated", "scanned", "approx_ms", "exact_ms"):
                require(key in entry, f"per_query entry is missing {key!r}")
            require(entry.get("outpost") == query["outpost"], "per_query entries keep the query's outpost (None when unfiltered)")
            ids = [str(identifier) for identifier in entry["ids"]]
            require(len(ids) == entry["returned"] == len(wanted), f"returned must be the number of ids ({len(wanted)}), got {entry['returned']!r}")
            pairs, _, _ = results_of(approx.search(query["vector"], K, outpost=query["outpost"]))
            require([identifier for identifier, _ in pairs] == ids, "per_query ids must be what the index returns for that query (the same seed and params give the same results)")
            want = recall_of(ids, wanted)
            require(near(entry["recall"], want), f"per_query recall {entry['recall']!r} differs from Verify's {want:.4f} against the exact top-{K}")
            recalls.append(want)
        mean_recall = sum(recalls) / len(recalls)
        require(near(report.get("recall_mean"), mean_recall), f"recall_mean {report.get('recall_mean')!r} must be the mean of per_query recall ({mean_recall:.4f})")
        require(near(report.get("recall_min"), min(recalls)), f"recall_min {report.get('recall_min')!r} must be the smallest per_query recall ({min(recalls):.4f})")
        require(mean_recall >= BOUND, f"recall@{K} {mean_recall:.4f} is below the declared bound {BOUND}")
        again, _ = build_approx(cheapest)
        for query in queries[:6]:
            first, _, _ = results_of(approx.search(query["vector"], K, outpost=query["outpost"]))
            second, _, _ = results_of(again.search(query["vector"], K, outpost=query["outpost"]))
            require([identifier for identifier, _ in first] == [identifier for identifier, _ in second], "Two builds with the same seed and params must return the same results")
        return f"Grid {[(p['probes'], round(r, 3)) for p, r, _ in measured]} (probes, recall); chose {cheapest} with recall@{K} {mean_recall:.3f} ≥ {BOUND}, min {min(recalls):.2f}, tune took {tune_seconds:.1f} s."
    check("Recall@k meets the declared bound and the report recomputes from per-query results", recall)

    def timing():
        exact, exact_wall = build_exact()
        approx, wall = build_approx(GRID[2])
        build_seconds = getattr(approx, "build_seconds", None)
        require(isinstance(build_seconds, (int, float)) and 0 < build_seconds <= wall + 0.001, f"build_seconds must be measured around build(): got {build_seconds!r} for a build that took {wall:.3f} s")
        started = time.perf_counter()
        report = candidate.measure(exact, approx, queries, K)
        measure_ms = (time.perf_counter() - started) * 1000
        require(isinstance(report, dict), "measure must return a dict")
        require(near(report.get("build_seconds"), build_seconds), "The report carries the index's build_seconds")
        for key in ("approx_p50_ms", "approx_p95_ms", "exact_p50_ms", "exact_p95_ms", "scanned_mean", "exact_scanned_mean"):
            require(isinstance(report.get(key), (int, float)) and report[key] >= 0, f"report.{key} must be a non-negative number, got {report.get(key)!r}")
        per_query = report["per_query"]
        approx_ms = [float(entry["approx_ms"]) for entry in per_query]
        exact_ms = [float(entry["exact_ms"]) for entry in per_query]
        require(all(value >= 0 for value in approx_ms + exact_ms), "Per-query latencies cannot be negative")
        require(sum(approx_ms) + sum(exact_ms) <= measure_ms + 2, f"Per-query latencies add up to {sum(approx_ms) + sum(exact_ms):.1f} ms, more than the {measure_ms:.1f} ms measure() took")
        for prefix, values in (("approx", approx_ms), ("exact", exact_ms)):
            require(near(report[f"{prefix}_p50_ms"], nearest_rank(values, 0.5), 1e-6) and near(report[f"{prefix}_p95_ms"], nearest_rank(values, 0.95), 1e-6), f"{prefix}_p50_ms/{prefix}_p95_ms must be nearest-rank percentiles of the per-query values")
        scanned = sum(int(entry["scanned"]) for entry in per_query) / len(per_query)
        full = sum(reference.count(query["outpost"]) for query in queries) / len(queries)
        require(near(report["scanned_mean"], scanned, 1e-6) and near(report["exact_scanned_mean"], full, 1e-6), f"scanned_mean {report['scanned_mean']!r} and exact_scanned_mean {report['exact_scanned_mean']!r} must be the means of the per-query counts ({scanned:.1f}, {full:.1f})")
        require(scanned < full, f"The approximate index compared {scanned:.0f} vectors per query on average, no fewer than exact search ({full:.0f}): it is not skipping anything")
        return f"Build {build_seconds * 1000:.0f} ms (exact {exact_wall * 1000:.0f} ms); approx p50 {report['approx_p50_ms']:.3f} ms / p95 {report['approx_p95_ms']:.3f} ms scanning {scanned:.0f} of {full:.0f} vectors; exact p50 {report['exact_p50_ms']:.3f} ms."
    check("Build time and search latency are measured", timing)

    def transfer():
        started = time.perf_counter()
        big_rng, big_items, big_vector = generate(seed + 1, scale=10)
        big_rng.shuffle(big_items)
        big_reference = Reference(big_items)
        big_queries = [{"vector": big_vector(), "outpost": outpost} for outpost in (None, "alpha", "beta", None, "alpha", "beta", None, "alpha", "beta", None, "gamma", "alpha")]
        big_expected = [big_reference.top(query["vector"], K, query["outpost"]) for query in big_queries]
        exact = candidate.ExactIndex(DIM).build(big_items)
        choice = candidate.tune(exact, big_items, big_queries, K, grid=TRANSFER_GRID, bound=BOUND, seed=seed)
        require(isinstance(choice, dict) and isinstance(choice.get("candidates"), list) and len(choice["candidates"]) == len(TRANSFER_GRID), "tune must report every grid entry")

        def recompute(params):
            build_started = time.perf_counter()
            approx = candidate.ApproxIndex(DIM, seed=seed, **params).build(big_items)
            build_seconds = time.perf_counter() - build_started
            recalls, latencies = [], []
            for query, wanted in zip(big_queries, big_expected):
                query_started = time.perf_counter()
                pairs, _, _ = results_of(approx.search(query["vector"], K, outpost=query["outpost"]))
                latencies.append((time.perf_counter() - query_started) * 1000)
                foreign = [identifier for identifier, _ in pairs if query["outpost"] and big_reference.outpost_of[identifier] != query["outpost"]]
                require(not foreign, f"Filtered search returned another outpost's passage on the tenfold fixture: {foreign[:3]}")
                require(len(pairs) == len(wanted), f"Expected {len(wanted)} results, got {len(pairs)} on the tenfold fixture")
                recalls.append(recall_of([identifier for identifier, _ in pairs], wanted))
            return sum(recalls) / len(recalls), build_seconds, nearest_rank(latencies, 0.5)

        if choice.get("params") is not None:
            entry = next((item for item in choice["candidates"] if item.get("params") == choice["params"]), None)
            require(entry is not None and entry.get("meets") is True, f"The chosen params {choice['params']} must be a candidate reported as meeting the bound")
            mean_recall, build_seconds, p50 = recompute(choice["params"])
            require(near(entry.get("recall_mean"), mean_recall, 1e-9), f"Reported recall_mean {entry.get('recall_mean')!r} differs from Verify's recomputation {mean_recall:.4f}")
            require(mean_recall >= BOUND, f"The chosen params reach only recall@{K} {mean_recall:.4f} on the tenfold fixture, below {BOUND}")
            verdict = f"meets the bound with {choice['params']}: recall@{K} {mean_recall:.3f}"
        else:
            for entry in choice["candidates"]:
                require(entry.get("meets") is False and isinstance(entry.get("recall_mean"), (int, float)) and entry["recall_mean"] < BOUND, f"When no params are chosen every candidate must report meets False with its measured recall; got {entry!r}")
            mean_recall, build_seconds, p50 = recompute(TRANSFER_GRID[-1])
            require(mean_recall < BOUND, f"tune reported that no params meet the bound, but {TRANSFER_GRID[-1]} reaches recall@{K} {mean_recall:.4f} on recomputation")
            verdict = f"reports honestly that no grid entry reaches {BOUND} (best measured {mean_recall:.3f})"
        elapsed = time.perf_counter() - started
        require(elapsed <= TRANSFER_BUDGET, f"The tenfold fixture took {elapsed:.1f} s, over the {TRANSFER_BUDGET:.0f} s budget")
        return f"{len(big_items)} vectors: {verdict}; build {build_seconds:.2f} s, p50 search {p50:.2f} ms, whole check {elapsed:.1f} s."
    check("Tenfold data still meets the bound or the report says it does not", transfer)

    def per_outpost():
        exact, _ = build_exact()
        approx, _ = build_approx(GRID[2])
        report = candidate.measure(exact, approx, queries, K)
        breakdown = report.get("per_outpost")
        require(isinstance(breakdown, dict), "The report must carry per_outpost: mean recall of the filtered queries of each outpost")
        wanted = {}
        for query, wanted_top in zip(queries, expected):
            if query["outpost"] is None:
                continue
            pairs, _, _ = results_of(approx.search(query["vector"], K, outpost=query["outpost"]))
            wanted.setdefault(query["outpost"], []).append(recall_of([identifier for identifier, _ in pairs], wanted_top))
        require(set(breakdown) == set(wanted), f"per_outpost keys must be the filtered outposts {sorted(wanted)}, got {sorted(breakdown)}")
        for outpost, values in wanted.items():
            require(near(breakdown[outpost], sum(values) / len(values)), f"per_outpost[{outpost!r}] {breakdown[outpost]!r} differs from the mean of its {len(values)} queries ({sum(values) / len(values):.4f})")
        return "Recall per outpost recomputed from the filtered queries: " + ", ".join(f"{outpost} {sum(values) / len(values):.2f}" for outpost, values in sorted(wanted.items()))
    check("bonus: the recall report breaks down per outpost", per_outpost, optional=True)


try:
    trial()
except Exception as error:
    CHECKS.append({"name": "Load approximate index", "passed": False, "detail": f"{type(error).__name__}: {error}"[:1500]})
print(json.dumps({"checks": CHECKS}))
sys.exit(0 if CHECKS and all(item["passed"] for item in CHECKS if not item.get("optional")) else 1)
