"""Harness ablation for the operator assistant.

Starter: it removes components one at a time, but each removal runs a different random
half of the cases, the comparison is two means with no interval, and anything whose
absence raised accuracy is dropped, the authorization check included. See LEARN.md for
the complete contract that Verify checks.
"""
import random


def ablate(components, cases, run, *, strategy="leave-one-out", z=1.96):
    names = [component["name"] for component in components]
    sample = random.sample(cases, max(2, len(cases) // 2))
    reference_results = [run(names, case) for case in sample]
    reference = {"active": names, "n": len(sample), "accuracy": sum(r["correct"] for r in reference_results) / len(sample)}
    rows = []
    for component in components:
        without = [other for other in names if other != component["name"]]
        sample = random.sample(cases, max(2, len(cases) // 2))
        results = [run(without, case) for case in sample]
        accuracy = sum(r["correct"] for r in results) / len(sample)
        rows.append({
            "component": component["name"], "kind": component["kind"], "with": names, "without": without,
            "cases": [case["id"] for case in sample], "n": len(sample),
            "accuracy_with": reference["accuracy"], "accuracy_without": accuracy,
            "mean_delta": reference["accuracy"] - accuracy,
            "tokens_delta": sum(r["tokens"] for r in reference_results) / len(reference_results) - sum(r["tokens"] for r in results) / len(results),
            "latency_delta_ms": sum(r["latency_ms"] for r in reference_results) / len(reference_results) - sum(r["latency_ms"] for r in results) / len(results),
        })
    return {"strategy": strategy, "z": z, "cases": [case["id"] for case in cases], "reference": reference, "rows": rows}


def decide(table, components):
    decisions, keep, drop = [], [], []
    for row in table["rows"]:
        if row["mean_delta"] > 0:
            verdict, reason = "keep", f"accuracy fell by {row['mean_delta']:.3f} without it"
        else:
            verdict, reason = "drop", f"accuracy rose by {-row['mean_delta']:.3f} without it"
        (keep if verdict == "keep" else drop).append(row["component"])
        decisions.append({"component": row["component"], "kind": row["kind"], "decision": verdict, "reason": reason,
                          "n": row["n"], "mean_delta": row["mean_delta"], "low": None, "high": None,
                          "tokens_delta": row["tokens_delta"], "latency_delta_ms": row["latency_delta_ms"]})
    return {"strategy": table["strategy"], "z": table["z"], "n": len(table["cases"]), "keep": keep, "drop": drop, "decisions": decisions}
