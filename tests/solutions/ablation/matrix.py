"""Harness ablation: dataclasses and the statistics module; every distinct component set is run once into a matrix, rows are composed from it."""
from dataclasses import dataclass, field
from statistics import NormalDist, fmean, stdev
from math import sqrt

GUARD_REASONS = frozenset({"permission", "safety", "cost"})


@dataclass(frozen=True)
class Component:
    name: str
    kind: str
    reason: str | None = None

    @classmethod
    def parse(cls, raw):
        name, kind, reason = raw.get("name"), raw.get("kind"), raw.get("reason")
        if not isinstance(name, str) or not name:
            raise ValueError("every component needs a name")
        if kind not in ("quality", "guard"):
            raise ValueError(f"{name}: kind must be quality or guard")
        if kind == "guard" and reason not in GUARD_REASONS:
            raise ValueError(f"{name}: a guard needs a reason of permission, safety or cost")
        return cls(name, kind, reason)


@dataclass
class Arm:
    active: tuple
    correct: list = field(default_factory=list)
    tokens: list = field(default_factory=list)
    latency: list = field(default_factory=list)

    def means(self):
        return {"accuracy": fmean(self.correct), "tokens": fmean(self.tokens), "latency_ms": fmean(self.latency)}


class Matrix:
    def __init__(self, cases, run):
        self.cases, self.run, self.arms = cases, run, {}

    def arm(self, active):
        key = tuple(active)
        if key not in self.arms:
            arm = Arm(key)
            for case in self.cases:
                result = self.run(list(key), case)
                arm.correct.append(result["correct"])
                arm.tokens.append(result["tokens"])
                arm.latency.append(result["latency_ms"])
            self.arms[key] = arm
        return self.arms[key]


def paired(with_values, without_values, z):
    diffs = [a - b for a, b in zip(with_values, without_values)]
    mean = fmean(diffs)
    se = stdev(diffs) / sqrt(len(diffs))
    return mean, se, mean - z * se, mean + z * se


def ablate(components, cases, run, *, strategy="leave-one-out", z=1.96):
    if strategy not in ("leave-one-out", "add-one-in"):
        raise ValueError(f"unknown strategy {strategy!r}")
    parsed = [Component.parse(raw) for raw in components]
    names = [c.name for c in parsed]
    if len(set(names)) != len(names):
        raise ValueError("component names must be distinct")
    ids = [case["id"] for case in cases]
    if len(ids) < 2 or len(set(ids)) != len(ids):
        raise ValueError("at least two distinct cases are required")
    pool = names if strategy == "leave-one-out" else [c.name for c in parsed if c.kind == "guard"]
    matrix = Matrix(cases, run)
    reference = matrix.arm(pool)
    rows = []
    for component in parsed:
        without = [other for other in pool if other != component.name]
        with_ = [other for other in names if other in without or other == component.name]
        a, b = matrix.arm(with_), matrix.arm(without)
        mean, se, low, high = paired(a.correct, b.correct, z)
        rows.append({
            "component": component.name, "kind": component.kind, "with": with_, "without": without, "cases": list(ids), "n": len(ids),
            "accuracy_with": a.means()["accuracy"], "accuracy_without": b.means()["accuracy"],
            "mean_delta": mean, "se": se, "low": low, "high": high,
            "tokens_delta": fmean(x - y for x, y in zip(a.tokens, b.tokens)), "latency_delta_ms": fmean(x - y for x, y in zip(a.latency, b.latency)),
        })
    return {"strategy": strategy, "z": z, "cases": ids, "reference": {"active": list(pool), "n": len(ids), **reference.means()}, "rows": rows}


def decide(table, components):
    parsed = {c.name: c for c in (Component.parse(raw) for raw in components)}
    comparisons = len(table["rows"])
    alpha = 2 * NormalDist().cdf(-table["z"])
    z_adjusted = NormalDist().inv_cdf(1 - alpha / (2 * comparisons))
    decisions, keep_adjusted = [], []
    for row in table["rows"]:
        component = parsed[row["component"]]
        interval = f"[{row['low']:.3f}, {row['high']:.3f}]"
        numbers = f"delta {row['mean_delta']:+.3f} {interval}, n = {row['n']}, tokens {row['tokens_delta']:+.0f}, latency {row['latency_delta_ms']:+.0f} ms"
        if component.kind == "guard":
            decision, reason = "keep", f"kept for {component.reason} regardless of quality; {numbers}"
            keep_adjusted.append(component.name)
        elif row["low"] > 0:
            decision, reason = "keep", f"measurably helps; {numbers}"
            if row["mean_delta"] > z_adjusted * row["se"]:
                keep_adjusted.append(component.name)
        else:
            decision, reason = "drop", ("hurts; " if row["high"] < 0 else "inconclusive, not earned; ") + numbers
        decisions.append({"component": component.name, "kind": component.kind, "decision": decision, "reason": reason,
                          **{key: row[key] for key in ("n", "mean_delta", "low", "high", "tokens_delta", "latency_delta_ms")}})
    return {
        "strategy": table["strategy"], "z": table["z"], "n": len(table["cases"]),
        "keep": [d["component"] for d in decisions if d["decision"] == "keep"], "drop": [d["component"] for d in decisions if d["decision"] == "drop"],
        "decisions": decisions, "comparisons": comparisons, "z_adjusted": z_adjusted, "keep_adjusted": keep_adjusted,
    }
