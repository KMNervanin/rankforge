"""Harness ablation: plain dicts, math, a memo of runs keyed by the active set and the case id."""
import math
from statistics import NormalDist

STRATEGIES = ("leave-one-out", "add-one-in")
GUARD_REASONS = ("permission", "safety", "cost")


def _validate(components, cases, strategy):
    if strategy not in STRATEGIES:
        raise ValueError(f"strategy must be one of {STRATEGIES}, got {strategy!r}")
    names = []
    for component in components:
        name, kind = component.get("name"), component.get("kind")
        if not isinstance(name, str) or not name or name in names:
            raise ValueError(f"component names must be distinct non-empty strings: {name!r}")
        if kind not in ("quality", "guard"):
            raise ValueError(f"component {name}: kind must be quality or guard, got {kind!r}")
        if kind == "guard" and component.get("reason") not in GUARD_REASONS:
            raise ValueError(f"guard {name}: reason must be one of {GUARD_REASONS}")
        names.append(name)
    if len(cases) < 2:
        raise ValueError("an ablation needs at least two cases")
    if len({case["id"] for case in cases}) != len(cases):
        raise ValueError("case ids must be distinct")
    return names


def _paired(diffs, z):
    n = len(diffs)
    mean = sum(diffs) / n
    variance = sum((d - mean) ** 2 for d in diffs) / (n - 1)
    se = math.sqrt(variance / n)
    return mean, se, mean - z * se, mean + z * se


def ablate(components, cases, run, *, strategy="leave-one-out", z=1.96):
    names = _validate(components, cases, strategy)
    guards = [c["name"] for c in components if c["kind"] == "guard"]
    memo = {}

    def outcome(active, case):
        key = (frozenset(active), case["id"])
        if key not in memo:
            memo[key] = run(list(active), case)
        return memo[key]

    def arm_means(active):
        results = [outcome(active, case) for case in cases]
        n = len(results)
        return {"accuracy": sum(r["correct"] for r in results) / n, "tokens": sum(r["tokens"] for r in results) / n, "latency_ms": sum(r["latency_ms"] for r in results) / n}

    pool = names if strategy == "leave-one-out" else guards
    reference = {"active": list(pool), "n": len(cases), **arm_means(pool)}
    rows = []
    for component in components:
        name = component["name"]
        without = [other for other in pool if other != name]
        with_ = [other for other in names if other in without or other == name]
        ran = cases  # both arms, the whole set, every row
        diffs = [outcome(with_, case)["correct"] - outcome(without, case)["correct"] for case in ran]
        mean, se, low, high = _paired(diffs, z)
        tokens = [outcome(with_, case)["tokens"] - outcome(without, case)["tokens"] for case in ran]
        latency = [outcome(with_, case)["latency_ms"] - outcome(without, case)["latency_ms"] for case in ran]
        rows.append({
            "component": name, "kind": component["kind"], "with": with_, "without": without,
            "cases": [case["id"] for case in ran], "n": len(ran),
            "accuracy_with": arm_means(with_)["accuracy"], "accuracy_without": arm_means(without)["accuracy"],
            "mean_delta": mean, "se": se, "low": low, "high": high,
            "tokens_delta": sum(tokens) / len(tokens), "latency_delta_ms": sum(latency) / len(latency),
        })
    return {"strategy": strategy, "z": z, "cases": [case["id"] for case in cases], "reference": reference, "rows": rows}


def _bonferroni(z, comparisons):
    alpha = 2 * (1 - NormalDist().cdf(z))
    return NormalDist().inv_cdf(1 - alpha / (2 * comparisons))


def decide(table, components):
    kinds = {c["name"]: c for c in components}
    z_adjusted = _bonferroni(table["z"], len(table["rows"]))
    decisions, keep, drop, keep_adjusted = [], [], [], []
    for row in table["rows"]:
        component = kinds[row["component"]]
        interval = f"[{row['low']:.3f}, {row['high']:.3f}]"
        cited = f"mean delta {row['mean_delta']:+.3f}, interval {interval} on {row['n']} cases, {row['tokens_delta']:+.0f} tokens and {row['latency_delta_ms']:+.0f} ms per case"
        if component["kind"] == "guard":
            verdict, reason = "keep", f"kept for {component['reason']}: a guard stays whatever its quality delta ({cited})"
            keep_adjusted.append(row["component"])
        elif row["low"] > 0:
            verdict, reason = "keep", f"earns its place: the interval lies above zero ({cited})"
            if row["mean_delta"] - z_adjusted * row["se"] > 0:
                keep_adjusted.append(row["component"])
        elif row["high"] < 0:
            verdict, reason = "drop", f"hurts: the interval lies below zero ({cited})"
        else:
            verdict, reason = "drop", f"not earned: the interval includes zero ({cited})"
        (keep if verdict == "keep" else drop).append(row["component"])
        decisions.append({"component": row["component"], "kind": component["kind"], "decision": verdict, "reason": reason,
                          "n": row["n"], "mean_delta": row["mean_delta"], "low": row["low"], "high": row["high"],
                          "tokens_delta": row["tokens_delta"], "latency_delta_ms": row["latency_delta_ms"]})
    return {"strategy": table["strategy"], "z": table["z"], "n": len(table["cases"]), "keep": keep, "drop": drop, "decisions": decisions,
            "comparisons": len(table["rows"]), "z_adjusted": z_adjusted, "keep_adjusted": keep_adjusted}
