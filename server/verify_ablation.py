"""Harness ablation checks for the Ablation mission; run outside the learner workspace.

Nothing here calls a model. The scripted runner below is a labeled test tool: it answers from a
planted truth that is deterministic from the active component set and the case id, and it logs
every call so Verify can see which cases each row really ran. Every expected number is recomputed
with fractions.Fraction from that planted truth, never from the learner's output.
"""
import importlib.util
import json
import math
import os
import random
import sys
from fractions import Fraction
from statistics import NormalDist

MISSION, WORKSPACE = sys.argv[1:3]
CHECKS = []
TOLERANCE = 1e-9
GUARD_REASONS = ("permission", "safety", "cost")


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def check(name, operation, optional=False):
    # An optional check is the hidden bonus of a mission: it can only add, it never fails the run.
    flag = {"optional": True} if optional else {}
    try:
        detail = operation()
        CHECKS.append({"name": name, "passed": True, "detail": detail or "Ablation table and decision record verified against the planted truth.", **flag})
    except Exception as error:
        CHECKS.append({"name": name, "passed": False, "detail": f"{type(error).__name__}: {error}"[:1500], **flag})


COMPONENTS = [
    {"name": "retrieval", "kind": "quality"},
    {"name": "reranker", "kind": "quality"},
    {"name": "few_shot", "kind": "quality"},
    {"name": "query_rewrite", "kind": "quality"},
    {"name": "authorization", "kind": "guard", "reason": "permission"},
    {"name": "cost_router", "kind": "guard", "reason": "cost"},
]
NAMES = [component["name"] for component in COMPONENTS]
GUARDS = [component["name"] for component in COMPONENTS if component["kind"] == "guard"]


class Plant:
    """A planted truth: per case a base verdict, per component the cases it fixes or breaks, plus flat token and latency costs."""

    def __init__(self, rng, *, label, shares):
        self.label = label
        n = rng.randint(36, 48)
        stamp = rng.randint(100, 999)
        self.ids = [f"case-{stamp}-{index:02d}" for index in range(n)]
        self.cases = [{"id": case_id, "request": f"Request {index + 1} for the {label} relay"} for index, case_id in enumerate(self.ids)]
        shuffled = self.ids[:]
        rng.shuffle(shuffled)
        base_right = shuffled[: round(shares["base"] * n)]
        base_wrong = shuffled[len(base_right):]
        self.base = {case_id: case_id in set(base_right) for case_id in self.ids}
        self.helps, self.hurts = {}, {}
        wrong_cursor, right_cursor = 0, 0
        for name in NAMES:
            count = shares[name]
            size = count if isinstance(count, int) else round(count * n)
            if shares["direction"][name] == "help":
                self.helps[name], self.hurts[name] = set(base_wrong[wrong_cursor:wrong_cursor + size]), set()
                wrong_cursor += size
            else:
                self.helps[name], self.hurts[name] = set(), set(base_right[right_cursor:right_cursor + size])
                right_cursor += size
        require(wrong_cursor <= len(base_wrong) and right_cursor <= len(base_right), "verifier bug: planted sets overlap")
        self.base_tokens = {case_id: rng.randint(300, 900) for case_id in self.ids}
        self.base_latency = {case_id: rng.randint(400, 1800) for case_id in self.ids}
        self.tokens = {"retrieval": rng.randint(700, 1300), "reranker": rng.randint(150, 350), "few_shot": rng.randint(500, 900), "query_rewrite": rng.randint(60, 140), "authorization": rng.randint(20, 60), "cost_router": -rng.randint(250, 450)}
        self.latency = {"retrieval": rng.randint(120, 260), "reranker": rng.randint(200, 400), "few_shot": rng.randint(30, 90), "query_rewrite": rng.randint(300, 500), "authorization": rng.randint(5, 20), "cost_router": -rng.randint(150, 300)}
        self.calls = []

    def correct(self, active, case_id):
        right = self.base[case_id] or any(case_id in self.helps[name] for name in active)
        broken = any(case_id in self.hurts[name] for name in active)
        return 1 if right and not broken else 0

    def outcome(self, active, case_id):
        return {"correct": self.correct(active, case_id), "tokens": self.base_tokens[case_id] + sum(self.tokens[name] for name in active), "latency_ms": self.base_latency[case_id] + sum(self.latency[name] for name in active)}

    def runner(self):
        def run(active, case):
            require(isinstance(active, (list, tuple, set, frozenset)) and all(isinstance(name, str) for name in active), f"run(active, case): active must be a list or set of component names, got {active!r}")
            unknown = set(active) - set(NAMES)
            require(not unknown, f"run was called with components that are not in the harness: {sorted(unknown)}")
            require(len(set(active)) == len(list(active)), f"run was called with a repeated component: {active!r}")
            require(isinstance(case, dict) and case.get("id") in self.base, f"run(active, case): case must be one of the given case dicts, got {case!r}")
            self.calls.append((frozenset(active), case["id"]))
            return dict(self.outcome(frozenset(active), case["id"]))
        return run

    # The oracle: exact statistics of the per-case differences between two component sets.
    def stats(self, with_set, without_set, z):
        diffs = [Fraction(self.correct(with_set, case_id) - self.correct(without_set, case_id)) for case_id in self.ids]
        n = len(diffs)
        mean = sum(diffs) / n
        variance = sum((diff - mean) ** 2 for diff in diffs) / (n - 1)
        se = math.sqrt(variance / n)
        tokens = sum(Fraction(self.outcome(with_set, case_id)["tokens"] - self.outcome(without_set, case_id)["tokens"]) for case_id in self.ids) / n
        latency = sum(Fraction(self.outcome(with_set, case_id)["latency_ms"] - self.outcome(without_set, case_id)["latency_ms"]) for case_id in self.ids) / n
        return {"n": n, "mean_delta": mean, "se": se, "low": float(mean) - z * se, "high": float(mean) + z * se, "tokens_delta": tokens, "latency_delta_ms": latency,
                "accuracy_with": sum(Fraction(self.correct(with_set, case_id)) for case_id in self.ids) / n, "accuracy_without": sum(Fraction(self.correct(without_set, case_id)) for case_id in self.ids) / n}

    def arms(self, name, strategy):
        pool = NAMES if strategy == "leave-one-out" else GUARDS
        without = [other for other in pool if other != name]
        with_ = [other for other in NAMES if other in without or other == name]
        return with_, without

    def classify(self, name, strategy, z):
        with_, without = self.arms(name, strategy)
        row = self.stats(frozenset(with_), frozenset(without), z)
        return "helps" if row["low"] > 0 else "hurts" if row["high"] < 0 else "inconclusive"


WEAK = {"base": 0.5, "direction": {"retrieval": "help", "reranker": "help", "few_shot": "help", "query_rewrite": "hurt", "authorization": "hurt", "cost_router": "hurt"},
        "retrieval": 0.3, "reranker": 0.125, "few_shot": 1, "query_rewrite": 0.22, "authorization": 0.15, "cost_router": 1}
STRONG = {"base": 0.55, "direction": {"retrieval": "help", "reranker": "help", "few_shot": "hurt", "query_rewrite": "help", "authorization": "hurt", "cost_router": "hurt"},
          "retrieval": 0.2, "reranker": 1, "few_shot": 0.2, "query_rewrite": 0.2, "authorization": 0.15, "cost_router": 1}
WEAK_TRUTH = {"retrieval": "helps", "reranker": "helps", "few_shot": "inconclusive", "query_rewrite": "hurts", "authorization": "hurts", "cost_router": "inconclusive"}
STRONG_TRUTH = {"retrieval": "helps", "reranker": "inconclusive", "few_shot": "hurts", "query_rewrite": "helps"}
TRANSFER_Z = 2.326


def adjusted_z(z, comparisons):
    alpha = 2 * (1 - NormalDist().cdf(z))
    return NormalDist().inv_cdf(1 - alpha / (2 * comparisons))


def plant(seed, shares, truth, z):
    """Draws fresh sizes and ids until the planted truth classifies as intended at the given z (and, for the weak plant, the marginal reranker drops at the Bonferroni z)."""
    rng = random.Random(seed)
    for _ in range(200):
        candidate = Plant(rng, label="strong" if shares is STRONG else "weak", shares=shares)
        if all(candidate.classify(name, "leave-one-out", z) == wanted for name, wanted in truth.items()):
            if shares is STRONG:
                return candidate
            marginal = candidate.stats(frozenset(NAMES), frozenset(NAMES) - {"reranker"}, adjusted_z(z, len(NAMES)))
            if marginal["low"] <= 0:
                return candidate
    raise RuntimeError("verifier bug: no draw matched the planted truth")


def close(actual, expected, what):
    require(isinstance(actual, (int, float)) and not isinstance(actual, bool) and math.isfinite(actual), f"{what} must be a finite number, got {actual!r}")
    require(abs(Fraction(str(actual)) - Fraction(expected) if isinstance(expected, Fraction) else actual - expected) <= TOLERANCE, f"{what} is {actual!r}, expected {float(expected)!r}")


def trial():
    require(MISSION == "ablation", "Unknown mission")
    sys.path.insert(0, WORKSPACE)
    spec = importlib.util.spec_from_file_location("candidate_ablation", os.path.join(WORKSPACE, "ablation.py"))
    if spec is None or spec.loader is None:
        raise ImportError("Cannot load ablation.py")
    candidate = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = candidate
    spec.loader.exec_module(candidate)
    require(callable(getattr(candidate, "ablate", None)), "ablation.py must define ablate(components, cases, run, *, strategy='leave-one-out', z=1.96)")
    require(callable(getattr(candidate, "decide", None)), "ablation.py must define decide(table, components)")
    seed = random.SystemRandom().randint(1, 10**9)
    try:
        weak = plant(seed, WEAK, WEAK_TRUTH, 1.96)
        strong = plant(seed + 1, STRONG, STRONG_TRUTH, TRANSFER_Z)
    except RuntimeError as error:
        CHECKS.append({"name": "Verifier could not plant a truth", "passed": False, "detail": f"{error}; this is a verifier problem, not a workspace one. Verify again."})
        return

    def table_of(plant_, strategy, z=None):
        plant_.calls.clear()
        options = {"strategy": strategy} if z is None else {"strategy": strategy, "z": z}
        table = candidate.ablate([dict(component) for component in COMPONENTS], [dict(case) for case in plant_.cases], plant_.runner(), **options)
        require(isinstance(table, dict), "ablate must return a dict table")
        require(table.get("strategy") == strategy, f"table['strategy'] must be {strategy!r}, got {table.get('strategy')!r}")
        close(table.get("z"), 1.96 if z is None else z, "table['z']")
        require(table.get("cases") == plant_.ids, "table['cases'] must list every case id in input order")
        rows = table.get("rows")
        require(isinstance(rows, list) and [row.get("component") for row in rows] == NAMES, f"table['rows'] must hold one row per component in input order, got {[row.get('component') for row in rows] if isinstance(rows, list) else rows!r}")
        for row, component in zip(rows, COMPONENTS):
            require(row.get("kind") == component["kind"], f"row {component['name']}: kind must be {component['kind']!r}")
            with_, without = plant_.arms(component["name"], strategy)
            require(row.get("with") == with_ and row.get("without") == without, f"row {component['name']} under {strategy}: with must be {with_} and without {without}, got with {row.get('with')!r} and without {row.get('without')!r}")
        return table

    def reference_means(plant_, reference, active):
        n = len(plant_.ids)
        outcomes = [plant_.outcome(frozenset(active), case_id) for case_id in plant_.ids]
        for key in ("accuracy", "tokens", "latency_ms"):
            field = "correct" if key == "accuracy" else key
            close(reference.get(key), sum(Fraction(outcome[field]) for outcome in outcomes) / n, f"reference {key}")

    def full_set(plant_, table):
        for row in table["rows"]:
            require(row.get("cases") == plant_.ids, f"row {row['component']}: cases must be the full case set of {len(plant_.ids)} ids in input order; a row computed on a subset is rejected (got {len(row.get('cases') or [])})")
            require(row.get("n") == len(plant_.ids), f"row {row['component']}: n must be {len(plant_.ids)}")
            for arm in ("with", "without"):
                missing = [case_id for case_id in plant_.ids if (frozenset(row[arm]), case_id) not in plant_.calls]
                require(not missing, f"row {row['component']}: the {arm} arm {row[arm]} was never run on {len(missing)} of the cases (first {missing[:1]}); every arm reruns the whole set")

    def numbers(plant_, table, z):
        details = []
        for row in table["rows"]:
            expected = plant_.stats(frozenset(row["with"]), frozenset(row["without"]), z)
            for key in ("mean_delta", "se", "low", "high", "tokens_delta", "latency_delta_ms", "accuracy_with", "accuracy_without"):
                close(row.get(key), expected[key], f"row {row['component']}: {key}")
            details.append(f"{row['component']} {float(expected['mean_delta']):+.3f} [{expected['low']:+.3f}, {expected['high']:+.3f}]")
        return details

    def record_of(plant_, table):
        record = candidate.decide(table, [dict(component) for component in COMPONENTS])
        require(isinstance(record, dict), "decide must return a dict record")
        require(record.get("strategy") == table["strategy"], "record['strategy'] must repeat the table's strategy")
        close(record.get("z"), table["z"], "record['z']")
        require(record.get("n") == len(table["cases"]), f"record['n'] must be the case count {len(table['cases'])}, got {record.get('n')!r}")
        decisions = record.get("decisions")
        require(isinstance(decisions, list) and [entry.get("component") for entry in decisions] == NAMES, "record['decisions'] must hold one entry per component in input order")
        keep, drop = record.get("keep"), record.get("drop")
        require(isinstance(keep, list) and isinstance(drop, list) and sorted(keep + drop) == sorted(NAMES) and not set(keep) & set(drop), "record['keep'] and record['drop'] must partition the component names")
        for entry, row, component in zip(decisions, table["rows"], COMPONENTS):
            require(entry.get("decision") in ("keep", "drop"), f"{component['name']}: decision must be keep or drop")
            require((entry["decision"] == "keep") == (component["name"] in keep), f"{component['name']}: the decision entry and the keep list disagree")
            require(entry.get("kind") == component["kind"], f"{component['name']}: the decision entry carries the kind")
            for key in ("n", "mean_delta", "low", "high", "tokens_delta", "latency_delta_ms"):
                require(entry.get(key) == row.get(key), f"{component['name']}: the decision entry must cite the row's {key} ({row.get(key)!r}), got {entry.get(key)!r}")
            reason = entry.get("reason")
            require(all(isinstance(row.get(key), (int, float)) for key in ("low", "high")), f"{component['name']}: the row must carry low and high to cite, got low {row.get('low')!r} and high {row.get('high')!r}")
            cited = f"[{row['low']:.3f}, {row['high']:.3f}]"
            require(isinstance(reason, str) and cited in reason, f"{component['name']}: the reason must cite the interval as {cited}, got {reason!r}")
        return record

    def leave_one_out():
        table = table_of(weak, "leave-one-out")
        full_set(weak, table)
        reference = table.get("reference")
        require(isinstance(reference, dict) and reference.get("active") == NAMES and reference.get("n") == len(weak.ids), "table['reference'] must describe the full harness: active = every component, n = the case count")
        reference_means(weak, reference, NAMES)
        distinct = len({active for active, _ in weak.calls})
        return f"{len(NAMES)} rows, each arm run on all {len(weak.ids)} cases; {distinct} distinct component sets were run."
    check("Leave-one-out: every row reruns the full case set against the same reference harness", leave_one_out)

    def intervals():
        table = table_of(weak, "leave-one-out")
        details = numbers(weak, table, 1.96)
        return "Paired deltas with a sample standard error and z = 1.96 agreed within 1e-9: " + "; ".join(details) + "."
    check("Deltas carry a paired standard error and an interval from the per-case differences", intervals)

    def decision():
        table = table_of(weak, "leave-one-out")
        record = record_of(weak, table)
        require("retrieval" in record["keep"], "retrieval: its interval lies entirely above zero (removing it hurts), so it must be kept")
        require("few_shot" in record["drop"], "few_shot: its interval includes zero, so it has not earned its place and must be dropped")
        require("query_rewrite" in record["drop"], "query_rewrite: its interval lies entirely below zero (it hurts), so it must be dropped")
        require("reranker" in record["keep"], "reranker: its interval lies above zero at z = 1.96, so the published rule keeps it")
        return "retrieval and reranker kept, few_shot (inconclusive) and query_rewrite (harmful) dropped; every reason cites its interval."
    check("The decision keeps what measurably helps and drops what does not or what hurts", decision)

    def guards():
        table = table_of(weak, "leave-one-out")
        record = record_of(weak, table)
        rows = {name: weak.stats(*map(frozenset, weak.arms(name, "leave-one-out")), 1.96) for name in GUARDS}
        require(rows["authorization"]["high"] < 0, "verifier bug: the planted authorization guard must look harmful to accuracy")
        entries = {entry["component"]: entry for entry in record["decisions"]}
        for name, reason in (("authorization", "permission"), ("cost_router", "cost")):
            require(name in record["keep"], f"{name}: a guard is kept whatever its quality delta; accuracy rising without it is not a reason to remove an authorization boundary")
            require(f"kept for {reason}" in entries[name]["reason"], f"{name}: the reason must carry the label 'kept for {reason}', got {entries[name]['reason']!r}")
        require("kept for" not in entries["retrieval"]["reason"], "retrieval is a quality component: it is kept for its numbers, not labeled as a guard")
        return f"authorization kept for permission although accuracy without it rises by {-float(rows['authorization']['mean_delta']):.3f}; cost_router kept for cost with {float(rows['cost_router']['tokens_delta']):+.0f} tokens per case."
    check("Guards stay regardless of the quality delta and are labeled with their non-quality reason", guards)

    def add_one_in():
        table = table_of(weak, "add-one-in")
        full_set(weak, table)
        reference = table.get("reference")
        require(isinstance(reference, dict) and reference.get("active") == GUARDS, f"table['reference'] under add-one-in must be the guards only: {GUARDS}")
        reference_means(weak, reference, GUARDS)
        numbers(weak, table, 1.96)
        record = record_of(weak, table)
        loo = candidate.decide(table_of(weak, "leave-one-out"), [dict(component) for component in COMPONENTS])
        require(sorted(record["keep"]) == sorted(loo["keep"]), f"Add-one-in must reach the same decision as leave-one-out on this planted truth: {sorted(record['keep'])} vs {sorted(loo['keep'])}")
        return f"Add-one-in from the guards-only base reached the same keep list: {record['keep']}."
    check("Add-one-in reaches the same decision on the same planted truth", add_one_in)

    def transfer():
        table = table_of(strong, "leave-one-out", z=TRANSFER_Z)
        full_set(strong, table)
        numbers(strong, table, TRANSFER_Z)
        record = record_of(strong, table)
        require("query_rewrite" in record["keep"], "On the stronger model query_rewrite helps: its interval lies above zero and it must be kept")
        require("reranker" in record["drop"], "On the stronger model the reranker no longer helps: its interval includes zero and it must be dropped")
        require("few_shot" in record["drop"], "On the stronger model few_shot hurts and must be dropped")
        require("retrieval" in record["keep"] and "authorization" in record["keep"] and "cost_router" in record["keep"], "retrieval still helps and the guards stay")
        return f"Stronger model at z = {TRANSFER_Z}: query_rewrite now kept, reranker now dropped; keep = {record['keep']}."
    check("Transfer: a stronger model changes which components help and the decision follows the numbers", transfer)

    def refusals():
        run = weak.runner()
        cases = [dict(case) for case in weak.cases]
        attempts = [
            ("an unknown strategy", lambda: candidate.ablate([dict(c) for c in COMPONENTS], cases, run, strategy="drop-all")),
            ("a guard without a reason", lambda: candidate.ablate([dict(c) for c in COMPONENTS[:4]] + [{"name": "authorization", "kind": "guard"}], cases, run)),
            ("an unknown kind", lambda: candidate.ablate([dict(c) for c in COMPONENTS[:4]] + [{"name": "logger", "kind": "nice"}], cases, run)),
            ("a repeated component name", lambda: candidate.ablate([dict(c) for c in COMPONENTS] + [{"name": "retrieval", "kind": "quality"}], cases, run)),
            ("fewer than two cases", lambda: candidate.ablate([dict(c) for c in COMPONENTS], cases[:1], run)),
            ("a repeated case id", lambda: candidate.ablate([dict(c) for c in COMPONENTS], cases + [dict(cases[0])], run)),
            ("a missing name", lambda: candidate.ablate([dict(c) for c in COMPONENTS] + [{"kind": "quality"}], cases, run)),
        ]
        for label, attempt in attempts:
            weak.calls.clear()
            raised = False
            try:
                attempt()
            except ValueError:
                raised = True
            require(raised, f"ablate must raise ValueError for {label}")
            require(not weak.calls, f"ablate must refuse {label} before running anything")
        return "Unknown strategy, a guard without a reason, an unknown kind, a repeated name, a single case, a repeated case id and a missing name were refused with ValueError before any run."
    check("Invalid input is refused with ValueError before any run", refusals)

    def bonus():
        table = table_of(weak, "leave-one-out")
        record = record_of(weak, table)
        require(record.get("comparisons") == len(NAMES), f"record['comparisons'] must count the {len(NAMES)} components tested")
        wanted = adjusted_z(1.96, len(NAMES))
        require(isinstance(record.get("z_adjusted"), float) and abs(record["z_adjusted"] - wanted) <= 1e-6, f"record['z_adjusted'] must be the Bonferroni z for {len(NAMES)} two-sided comparisons at the same alpha: {wanted:.6f}")
        kept = record.get("keep_adjusted")
        require(isinstance(kept, list) and "reranker" not in kept and "retrieval" in kept and all(guard in kept for guard in GUARDS), f"keep_adjusted at z = {wanted:.3f} must drop the marginal reranker and keep retrieval and the guards, got {kept!r}")
        require("few_shot" not in kept and "query_rewrite" not in kept, "keep_adjusted never keeps what the unadjusted rule dropped")
        return f"{len(NAMES)} comparisons: z adjusted from 1.96 to {wanted:.3f}; the marginal reranker no longer clears zero."
    check("bonus: the record counts its comparisons and recomputes the keep list at a Bonferroni-adjusted z", bonus, optional=True)


try:
    trial()
except Exception as error:
    CHECKS.append({"name": "Load ablation module", "passed": False, "detail": f"{type(error).__name__}: {error}"[:1500]})
print(json.dumps({"checks": CHECKS}))
sys.exit(0 if CHECKS and all(item["passed"] for item in CHECKS if not item.get("optional")) else 1)
