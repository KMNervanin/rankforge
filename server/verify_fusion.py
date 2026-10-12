"""Hybrid retriever checks for the Fusion mission; run outside the learner workspace.

Nothing here calls a model or opens a socket. The lexical and dense rankings are canned per query,
the reranker is a scripted scorer that counts its calls and advances an injected clock per pair, and
every expected number (RRF scores, weighted fusion, hit ranks, MRR, nearest-rank percentiles,
latencies) is recomputed in this file with exact arithmetic. The scripted scorer is a labeled test
tool: it decides nothing about relevance, it only makes the reranker's cost deterministic.
"""
import importlib.util
import json
import math
import re
import os
import random
import sys
from fractions import Fraction

MISSION, WORKSPACE = sys.argv[1:3]
CHECKS = []
STAGES = ("fused", "reranked")


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def check(name, operation, optional=False):
    # An optional check is the hidden bonus of a mission: it can only add, it never fails the run.
    flag = {"optional": True} if optional else {}
    try:
        detail = operation()
        CHECKS.append({"name": name, "passed": True, "detail": detail or "Fused rankings and the measurement report verified.", **flag})
    except Exception as error:
        CHECKS.append({"name": name, "passed": False, "detail": f"{type(error).__name__}: {error}"[:1500], **flag})


# ---- Verify's own oracle: exact arithmetic, independent of the learner module ----

def exact_rrf(rankings, k, weights=None):
    weights = weights or [1] * len(rankings)
    scores = {}
    for ranking, weight in zip(rankings, weights):
        for rank, (doc_id, _score) in enumerate(ranking, start=1):
            scores[doc_id] = scores.get(doc_id, Fraction(0)) + Fraction(str(weight)) / (k + rank)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))


def exact_weighted(rankings, weights):
    scores = {}
    for ranking, weight in zip(rankings, weights):
        values = [Fraction(str(score)) for _doc_id, score in ranking]
        low, high = min(values), max(values)
        for (doc_id, _score), value in zip(ranking, values):
            normalized = Fraction(1) if high == low else (value - low) / (high - low)
            scores[doc_id] = scores.get(doc_id, Fraction(0)) + Fraction(str(weight)) * normalized
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))


def exact_hit(ids, expected):
    return ids.index(expected) + 1 if expected in ids else None


def exact_mrr(ranks):
    return sum((Fraction(1, rank) for rank in ranks if rank), Fraction(0)) / len(ranks)


def nearest_rank(samples, p):
    ordered = sorted(samples)
    return ordered[max(1, math.ceil(Fraction(p, 100) * len(ordered))) - 1]


def same_ranking(actual, expected, tolerance, label):
    require(isinstance(actual, list), f"{label}: expected a list of (id, score) pairs, got {type(actual).__name__}")
    require(len(actual) == len(expected), f"{label}: expected {len(expected)} entries, got {len(actual)}")
    for position, (got, want) in enumerate(zip(actual, expected), start=1):
        require(isinstance(got, (tuple, list)) and len(got) == 2, f"{label}: entry {position} must be an (id, score) pair, got {got!r}")
        doc_id, score = got
        require(doc_id == want[0], f"{label}: position {position} is {doc_id!r}, expected {want[0]!r} (expected order {[item[0] for item in expected]})")
        require(isinstance(score, (int, float)) and not isinstance(score, bool) and math.isfinite(score), f"{label}: score of {doc_id!r} must be a finite number, got {score!r}")
        require(abs(Fraction(str(score)) - want[1]) <= tolerance, f"{label}: score of {doc_id!r} is {score!r}, expected {float(want[1])!r}")


class Clock:
    """Injected clock in seconds: it only moves when a scripted retriever or scorer advances it."""

    def __init__(self, start):
        self.now = float(start)

    def __call__(self):
        return self.now

    def advance_ms(self, milliseconds):
        self.now += milliseconds / 1000


class Scorer:
    """Scripted cross-encoder stand-in: counts every (query, id) pair and charges the clock per pair."""

    def __init__(self, clock, table, pair_ms):
        self.clock, self.table, self.pair_ms, self.calls = clock, table, pair_ms, []

    def __call__(self, query, doc_id):
        self.calls.append((query, doc_id))
        self.clock.advance_ms(self.pair_ms)
        return self.table.get((query, doc_id), 0.0)


def canned_retriever(clock, table, cost_ms, calls):
    def retrieve(text):
        require(text in table, f"a retriever received {text!r}, which is not a query text")
        calls.append(text)
        clock.advance_ms(cost_ms[text])
        return list(table[text])
    return retrieve


def trial():
    require(MISSION == "fusion", "Unknown mission")
    sys.path.insert(0, WORKSPACE)
    spec = importlib.util.spec_from_file_location("candidate_fusion", os.path.join(WORKSPACE, "fusion.py"))
    if spec is None or spec.loader is None:
        raise ImportError("Cannot load fusion.py")
    candidate = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = candidate
    spec.loader.exec_module(candidate)
    for name in ("rrf", "weighted", "rerank", "measure", "decide"):
        require(callable(getattr(candidate, name, None)), f"fusion.py must define {name}(...)")
    rng = random.Random()
    tag = f"{rng.randint(100, 999)}"
    ids = {letter: f"rb-{tag}-{letter}" for letter in "abcdefgh"}

    def fixture_rankings():
        # Three overlapping ranked lists with scores Verify never uses for RRF: ranks alone decide.
        lexical = [(ids["a"], 12.4), (ids["b"], 9.1), (ids["c"], 7.7), (ids["d"], 2.0)]
        dense = [(ids["c"], 0.91), (ids["a"], 0.88), (ids["e"], 0.63)]
        titles = [(ids["b"], 3.0), (ids["e"], 2.0), (ids["a"], 1.5), (ids["f"], 1.0)]
        return [lexical, dense, titles]

    def rrf_fixtures():
        rankings = fixture_rankings()
        fresh_k = rng.choice([7, 11, 17, 23, 31, 45, 90, 120])
        for k, label in ((60, "k=60"), (fresh_k, f"k={fresh_k}")):
            actual = candidate.rrf(rankings, k) if k != 60 else candidate.rrf(rankings)
            same_ranking(actual, exact_rrf(rankings, k), Fraction(1, 10**12), f"rrf {label}")
        require([doc_id for doc_id, _score in candidate.rrf(rankings)][:3] == [ids["a"], ids["b"], ids["c"]], "rrf at k=60 must rank the ids that appear in more lists first")
        single = candidate.rrf([[(ids["g"], 1.0), (ids["h"], 0.5)]])
        same_ranking(single, [(ids["g"], Fraction(1, 61)), (ids["h"], Fraction(1, 62))], Fraction(1, 10**12), "rrf with one list")
        return f"RRF of three overlapping lists matched the exact 1/(k+rank) sums at k=60 and k={fresh_k} within 1e-12."
    check("RRF matches hand-computed fixtures at k=60 and a fresh k", rrf_fixtures)

    def ties():
        first, second, third = sorted(rng.sample([ids["c"], ids["e"], ids["g"], ids["h"]], 3))
        lexical = [(second, 5.0), (first, 4.0), (third, 1.0)]
        dense = [(first, 0.9), (second, 0.8), (ids["a"], 0.1)]
        fused = candidate.rrf([lexical, dense])
        require(isinstance(fused, list) and len(fused) == 4, f"four distinct ids fused into {len(fused) if isinstance(fused, list) else fused!r} entries")
        order = [doc_id for doc_id, _score in fused]
        require(order[:2] == [first, second], f"{first!r} and {second!r} tie at 1/61 + 1/62 and must break by id ascending, got {order[:2]}")
        require(order[2:] == sorted([third, ids["a"]]), f"{third!r} and {ids['a']!r} tie at 1/63 and must break by id ascending, got {order[2:]}")
        weighted_order = [doc_id for doc_id, _score in candidate.weighted([[(second, 1.0), (first, 1.0)], [(first, 2.0), (second, 2.0)]], [0.5, 0.5])]
        require(weighted_order == [first, second], f"weighted fusion ties must break by id ascending too, got {weighted_order}")
        return "Equal scores ordered by id ascending in rrf and weighted."
    check("Ties break by score descending then id ascending", ties)

    def weighted_fusion():
        lexical = [(ids["a"], 12.0), (ids["b"], 9.0), (ids["c"], 3.0)]
        dense = [(ids["c"], 0.9), (ids["a"], 0.8), (ids["d"], 0.5)]
        w_lex = rng.choice([0.3, 0.4, 0.45])
        weights = [w_lex, round(1 - w_lex, 2)]
        same_ranking(candidate.weighted([lexical, dense], weights), exact_weighted([lexical, dense], weights), Fraction(1, 10**9), f"weighted {weights}")
        flat = [(ids["e"], 2.5), (ids["f"], 2.5)]
        same_ranking(candidate.weighted([flat, dense], [1.0, 1.0]), exact_weighted([flat, dense], [1.0, 1.0]), Fraction(1, 10**9), "weighted with a flat list")
        raw = sorted({ids["a"]: 12.0 * w_lex + 0.8 * weights[1], ids["b"]: 9.0 * w_lex, ids["c"]: 3.0 * w_lex + 0.9 * weights[1], ids["d"]: 0.5 * weights[1]}.items(), key=lambda item: (-item[1], item[0]))
        got = candidate.weighted([lexical, dense], weights)
        require(abs(got[0][1] - raw[0][1]) > 1e-6, "weighted must normalize each list to [0, 1] before mixing, not sum raw scores")
        return f"Min-max normalized weighted fusion matched at weights {weights} within 1e-9; a flat list normalizes to 1.0."
    check("Weighted fusion normalizes each list before mixing", weighted_fusion)

    def rerank_scope():
        clock = Clock(500)
        fused = exact_rrf(fixture_rankings(), 60)
        candidates = [(doc_id, float(score)) for doc_id, score in fused]
        top_n = rng.choice([3, 4])
        query = f"relay brownout {tag}"
        table = {(query, ids["c"]): 0.95, (query, ids["a"]): 0.40, (query, ids["b"]): 0.40, (query, ids["e"]): 0.75}
        scorer = Scorer(clock, table, 1.0)
        result = candidate.rerank(candidates, query, scorer, top_n)
        require(len(scorer.calls) == top_n, f"rerank must score exactly top_n={top_n} candidates, the scorer was called {len(scorer.calls)} times")
        require(sorted(scorer.calls) == sorted((query, doc_id) for doc_id, _score in candidates[:top_n]), f"the scorer must see (query, id) for each of the top {top_n} candidates once; saw {scorer.calls}")
        head = sorted(((doc_id, Fraction(str(table.get((query, doc_id), 0.0)))) for doc_id, _score in candidates[:top_n]), key=lambda item: (-item[1], item[0]))
        tail = [(doc_id, Fraction(str(score))) for doc_id, score in candidates[top_n:]]
        same_ranking(result, head + tail, Fraction(1, 10**9), "rerank")
        scorer = Scorer(clock, table, 1.0)
        everything = candidate.rerank(candidates, query, scorer, 100)
        require(len(scorer.calls) == len(candidates) and len(everything) == len(candidates), "top_n above the candidate count reranks every candidate once")
        scorer = Scorer(clock, table, 1.0)
        untouched = candidate.rerank(candidates, query, scorer, 0)
        require(not scorer.calls and [tuple(item) for item in untouched] == candidates, "top_n = 0 reranks nothing and returns the candidates unchanged")
        raised = False
        try:
            candidate.rerank(candidates, query, scorer, -1)
        except ValueError:
            raised = True
        require(raised and not scorer.calls, "a negative top_n raises ValueError before any scoring")
        return f"Scorer called exactly {top_n} times for {len(candidates)} candidates; head reordered, tail untouched."
    check("Rerank touches exactly the top_n candidates", rerank_scope)

    # Measurement fixture: 20 queries over 12 passages, canned rankings per query, fresh costs.
    corpus = [f"ps-{tag}-{index:02d}" for index in range(12)]
    queries, lexical_table, dense_table, score_table = [], {}, {}, {}
    cost_lexical, cost_dense = {}, {}
    base_lex, base_dense, pair_ms = rng.choice([2.0, 2.5, 3.0]), rng.choice([3.5, 4.0, 4.5]), rng.choice([1.5, 2.0, 2.5])
    top_n = 4
    for index in range(20):
        text = f"query {index} about {rng.choice(['fuses', 'filters', 'the relay', 'reservations'])} {tag}"
        expected = corpus[index % len(corpus)]
        others = [doc_id for doc_id in corpus if doc_id != expected]
        rng.shuffle(others)
        pattern = index % 4
        if pattern == 0:      # expected at rank 2-3 in both lists: the scorer lifts it to the top
            lexical = [others[0], expected] + others[1:6]
            dense = [others[1], others[0], expected] + others[6:10]
        elif pattern == 1:    # a short lexical list; expected comes from dense alone and lands inside top_n (one tie by id)
            lexical = others[:3]
            dense = [others[3], expected, others[0], others[4]]
        elif pattern == 2 and index % 8 == 2:   # expected in neither list: a miss before and after
            lexical = others[:7]
            dense = others[2:9]
        elif pattern == 2:    # expected far down both lists: outside top_n, the reranker cannot reach it
            lexical = others[:5] + [expected] + others[5:7]
            dense = others[2:7] + [expected, others[0]]
        else:                 # expected first in both lists: the scorer prefers a distractor (a loss)
            lexical = [expected] + others[:6]
            dense = [expected] + others[3:9]
        lexical_table[text] = [(doc_id, round(10.0 - 0.7 * rank, 3)) for rank, doc_id in enumerate(lexical)]
        dense_table[text] = [(doc_id, round(0.95 - 0.05 * rank, 3)) for rank, doc_id in enumerate(dense)]
        cost_lexical[text] = base_lex + 0.25 * (index % 7)
        cost_dense[text] = base_dense + 0.5 * (index % 5)
        for doc_id in corpus:
            score_table[(text, doc_id)] = 0.3 if pattern != 3 else 0.5
        score_table[(text, expected)] = 0.9 if pattern != 3 else 0.2
        queries.append({"id": f"q{index + 1:02d}", "text": text, "expected": expected})

    def expected_report():
        rows = []
        for index, query in enumerate(queries):
            text = query["text"]
            fused = exact_rrf([lexical_table[text], dense_table[text]], 60)
            fused_ids = [doc_id for doc_id, _score in fused]
            head = sorted(((doc_id, Fraction(str(score_table[(text, doc_id)]))) for doc_id in fused_ids[:top_n]), key=lambda item: (-item[1], item[0]))
            reranked_ids = [doc_id for doc_id, _score in head] + fused_ids[top_n:]
            fused_ms = cost_lexical[text] + cost_dense[text]
            rows.append({
                "fused": fused_ids, "reranked": reranked_ids,
                "hit": {"fused": exact_hit(fused_ids, query["expected"]), "reranked": exact_hit(reranked_ids, query["expected"])},
                "latency_ms": {"fused": fused_ms, "reranked": fused_ms + min(top_n, len(fused_ids)) * pair_ms},
                "calls": min(top_n, len(fused_ids)),
            })
        return rows

    def run_measure():
        clock = Clock(1000)
        lexical_calls, dense_calls = [], []
        retrievers = [canned_retriever(clock, lexical_table, cost_lexical, lexical_calls), canned_retriever(clock, dense_table, cost_dense, dense_calls)]
        scorer = Scorer(clock, score_table, pair_ms)
        report = candidate.measure(queries, retrievers, clock=clock, score_fn=scorer, top_n=top_n, k=60)
        require(isinstance(report, dict), "measure must return a dict report")
        return report, lexical_calls, dense_calls, scorer

    def measure_rows():
        report, lexical_calls, dense_calls, scorer = run_measure()
        rows = report.get("queries")
        require(isinstance(rows, list) and len(rows) == len(queries), f"report['queries'] must hold one entry per query ({len(queries)}), got {rows if not isinstance(rows, list) else len(rows)}")
        require(report.get("k") == 60 and report.get("top_n") == top_n, f"report must record k=60 and top_n={top_n}, got k={report.get('k')!r} top_n={report.get('top_n')!r}")
        require(lexical_calls == [query["text"] for query in queries] and dense_calls == lexical_calls, "each retriever is called exactly once per query, in query order, with the query text")
        wanted = expected_report()
        require(len(scorer.calls) == sum(row["calls"] for row in wanted), f"the scorer must be called {sum(row['calls'] for row in wanted)} times in total (top_n per query), was called {len(scorer.calls)}")
        for query, row, want in zip(queries, rows, wanted):
            require(isinstance(row, dict) and row.get("id") == query["id"], f"each query entry carries the query id, got {row!r}"[:300])
            require(row.get("fused") == want["fused"], f"{query['id']}: fused ids {row.get('fused')} differ from the RRF order {want['fused']}")
            require(row.get("reranked") == want["reranked"], f"{query['id']}: reranked ids {row.get('reranked')} differ from the expected {want['reranked']} (top {top_n} by scorer score, then the fused tail)")
            hit = row.get("hit")
            require(isinstance(hit, dict) and hit.get("fused") == want["hit"]["fused"] and hit.get("reranked") == want["hit"]["reranked"], f"{query['id']}: hit ranks {hit!r} must be {want['hit']} (1-based, None when absent)")
            latency = row.get("latency_ms")
            require(isinstance(latency, dict), f"{query['id']}: latency_ms must be a dict with fused and reranked")
            for stage in STAGES:
                got = latency.get(stage)
                require(isinstance(got, (int, float)) and not isinstance(got, bool) and abs(got - want["latency_ms"][stage]) <= 1e-6, f"{query['id']}: latency_ms[{stage!r}] is {got!r}, the injected clock advanced {want['latency_ms'][stage]} ms (retrievers {want['latency_ms']['fused']} ms, {want['calls']} scorer pairs at {pair_ms} ms)")
        samples = report.get("samples")
        require(isinstance(samples, dict), "report['samples'] must map fused and reranked to the raw latency lists")
        for stage in STAGES:
            got = samples.get(stage)
            require(isinstance(got, list) and len(got) == len(queries) and all(abs(a - b["latency_ms"][stage]) <= 1e-6 for a, b in zip(got, wanted)), f"samples[{stage!r}] must list the per-query latencies in query order")
        return f"20 queries: {sum(1 for row in wanted if row['hit']['reranked'] == 1)} expected ids at rank 1 after rerank; {len(scorer.calls)} scorer calls at {pair_ms} ms per pair on the injected clock."
    check("Measure records rankings, hit ranks and clock latencies per query", measure_rows)

    def aggregates():
        report, _lex, _dense, _scorer = run_measure()
        wanted = expected_report()
        for stage in STAGES:
            mrr = exact_mrr([row["hit"][stage] for row in wanted])
            got = (report.get("mrr") or {}).get(stage)
            require(isinstance(got, (int, float)) and abs(Fraction(str(got)) - mrr) <= Fraction(1, 10**9), f"mrr[{stage!r}] is {got!r}, the mean of 1/rank over 20 queries (0 for a miss) is {float(mrr)!r}")
            samples = [row["latency_ms"][stage] for row in wanted]
            for key, p in (("p50_ms", 50), ("p95_ms", 95)):
                got = (report.get(key) or {}).get(stage)
                want = nearest_rank(samples, p)
                require(isinstance(got, (int, float)) and abs(got - want) <= 1e-6, f"{key}[{stage!r}] is {got!r}; nearest-rank over the 20 samples gives {want!r} (sorted sample number ceil({p}/100 × 20))")
        fused_mrr, reranked_mrr = (exact_mrr([row["hit"][stage] for row in wanted]) for stage in STAGES)
        return f"MRR {float(fused_mrr):.4f} → {float(reranked_mrr):.4f}; p95 {nearest_rank([r['latency_ms']['fused'] for r in wanted], 95)} → {nearest_rank([r['latency_ms']['reranked'] for r in wanted], 95)} ms, both recomputed from the raw samples."
    check("MRR gain and p95 recompute from the raw samples", aggregates)

    def hand_report(fused_hits, reranked_hits, fused_ms, reranked_ms, aggregates=True):
        rows = [{"id": f"h{i:02d}", "fused": [], "reranked": [], "hit": {"fused": f, "reranked": r}, "latency_ms": {"fused": a, "reranked": b}} for i, (f, r, a, b) in enumerate(zip(fused_hits, reranked_hits, fused_ms, reranked_ms), start=1)]
        report = {"k": 60, "top_n": 5, "queries": rows, "samples": {"fused": list(fused_ms), "reranked": list(reranked_ms)}}
        if aggregates:
            # Deliberately stale summaries: a decision that trusts them instead of the raw samples is wrong.
            report["mrr"] = {"fused": 0.1, "reranked": 0.9}
            report["p50_ms"] = {"fused": 1.0, "reranked": 1.0}
            report["p95_ms"] = {"fused": 1.0, "reranked": 1.0}
        return report

    fused_hits = [2, 3, None, 1, 2, 4, 1, None, 3, 2, 5, 1, 2, 3, None, 2, 1, 4, 2, 3]
    reranked_hits = [1, 1, None, 1, 1, 2, 1, None, 1, 1, 2, 2, 1, 1, None, 1, 1, 2, 1, 1]
    fused_ms = [5.0 + 0.5 * (i % 6) for i in range(20)]
    jitter = rng.choice([6.0, 8.0, 10.0])
    reranked_ms = [f + jitter + (0.1 * i) for i, f in enumerate(fused_ms)]  # p95 is the 19th of 20, not the maximum
    gain = exact_mrr(reranked_hits) - exact_mrr(fused_hits)
    p95_after = nearest_rank(reranked_ms, 95)

    def read_decision(decision, label):
        require(isinstance(decision, dict), f"{label}: decide must return a dict")
        require(isinstance(decision.get("rerank"), bool), f"{label}: decision['rerank'] must be a bool")
        for key, want in (("mrr_gain", gain), ("p95_ms", Fraction(str(p95_after)))):
            got = decision.get(key)
            require(isinstance(got, (int, float)) and abs(Fraction(str(got)) - want) <= Fraction(1, 10**9), f"{label}: decision[{key!r}] is {got!r}, recomputed from the raw rows it is {float(want)!r}")
        rule = decision.get("rule")
        cited = isinstance(rule, str) and all(re.search(word + r"\D{0,24}\d", rule, re.IGNORECASE) for word in ("mrr", "p95"))
        require(cited, f"{label}: decision['rule'] must be a sentence containing the words MRR and p95 each followed by its number, got {rule!r}")
        return decision

    def decisions():
        report = hand_report(fused_hits, reranked_hits, fused_ms, reranked_ms)
        generous = {"min_mrr_gain": 0.05, "p95_ms": float(math.ceil(p95_after) + 5)}
        keep = read_decision(candidate.decide(report, generous), "generous budget")
        require(keep["rerank"] is True, f"gain {float(gain):.4f} ≥ 0.05 and p95 {p95_after} ms ≤ {generous['p95_ms']} ms: the reranker pays and must be kept, decision said {keep['rerank']}")
        demanding = {"min_mrr_gain": float(math.ceil(float(gain) * 100 + 5) / 100), "p95_ms": generous["p95_ms"]}
        drop = read_decision(candidate.decide(report, demanding), "demanding gain")
        require(drop["rerank"] is False, f"gain {float(gain):.4f} is below the declared minimum {demanding['min_mrr_gain']}: the reranker must be dropped even though latency fits")
        added = keep.get("p95_added_ms")
        require(isinstance(added, (int, float)) and abs(added - (p95_after - nearest_rank(fused_ms, 95))) <= 1e-9, f"decision['p95_added_ms'] must be the reranked p95 minus the fused p95 ({p95_after - nearest_rank(fused_ms, 95)!r}), got {added!r}")
        return f"Kept at gain {float(gain):.4f} within {generous['p95_ms']} ms; dropped when the minimum gain rose to {demanding['min_mrr_gain']}. Stale summaries in the report were ignored."
    check("Decision keeps a reranker that pays and drops one that does not", decisions)

    def unmeasured():
        report = hand_report(fused_hits, reranked_hits, fused_ms, reranked_ms)
        del report["samples"]
        report["mrr"] = {"fused": float(exact_mrr(fused_hits)), "reranked": float(exact_mrr(reranked_hits))}
        budget = {"min_mrr_gain": 0.05, "p95_ms": 1000.0}
        raised, decision = False, None
        try:
            decision = candidate.decide(report, budget)
        except ValueError:
            raised = True
        except Exception as error:
            raise AssertionError(f"a report without latency samples must raise ValueError, got {type(error).__name__}: {error}")
        require(raised, f"the MRR rose but no latency was measured: decide must raise ValueError instead of returning {decision!r}"[:600])
        half = hand_report(fused_hits, reranked_hits, fused_ms, reranked_ms)
        half["samples"]["reranked"] = []
        raised = False
        try:
            candidate.decide(half, budget)
        except ValueError:
            raised = True
        require(raised, "an empty reranked sample list is no measurement either: ValueError")
        return "A report with an MRR gain and no latency samples raised ValueError twice."
    check("A reranker without a latency measurement is never adopted", unmeasured)

    def tighter():
        report = hand_report(fused_hits, reranked_hits, fused_ms, reranked_ms)
        loose = {"min_mrr_gain": 0.05, "p95_ms": float(math.ceil(p95_after) + 5)}
        tight = {"min_mrr_gain": 0.05, "p95_ms": float(math.floor(p95_after) - 1)}
        require(read_decision(candidate.decide(report, loose), "loose")["rerank"] is True, "with the loose budget the reranker is kept")
        decision = read_decision(candidate.decide(report, tight), "tight")
        require(decision["rerank"] is False, f"p95 {p95_after} ms is over the tighter budget of {tight['p95_ms']} ms: the same report must now drop the reranker")
        require(decision.get("p95_budget_ms") == tight["p95_ms"] and abs(float(decision.get("min_mrr_gain", -1)) - 0.05) <= 1e-9, "the decision records the budget it was judged against (p95_budget_ms, min_mrr_gain)")
        return f"Same report: kept within {loose['p95_ms']} ms, dropped within {tight['p95_ms']} ms."
    check("A tighter latency budget flips the decision to drop", tighter)

    def weighted_rrf():
        rankings = fixture_rankings()
        weights = [rng.choice([2, 3]), 1, rng.choice([0.5, 1.5])]
        actual = candidate.rrf(rankings, 60, weights=weights)
        same_ranking(actual, exact_rrf(rankings, 60, weights), Fraction(1, 10**12), f"rrf weights={weights}")
        return f"RRF with per-list weights {weights} matched Σ w/(k+rank) within 1e-12."
    check("bonus: RRF accepts per-list weights", weighted_rrf, optional=True)


try:
    trial()
except Exception as error:
    CHECKS.append({"name": "Load hybrid retriever", "passed": False, "detail": f"{type(error).__name__}: {error}"[:1500]})
print(json.dumps({"checks": CHECKS}))
sys.exit(0 if CHECKS and all(item["passed"] for item in CHECKS if not item.get("optional")) else 1)
