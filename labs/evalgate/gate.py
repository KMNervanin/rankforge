"""Release gate for the operator assistant's evaluation suite.

Starter: it runs the suite and returns a verdict with every field the pipeline
expects, but the gate behind the verdict is guesswork. See LEARN.md for the
complete contract that Verify checks.
"""
import json
import os


class ConfigError(Exception):
    """Raised when the gate configuration is not usable."""


def run_gate(config, *, candidate, baseline_results, run_case, clock):
    started = clock()
    cases = config["manifest"]["cases"]
    baseline = baseline_results["cases"]
    results, tokens = [], 0
    for case in cases:
        result = run_case(case)
        tokens += result["tokens"]
        results.append({"id": case["id"], "passed": result["passed"], "attempts": [result]})
    accuracy = 100 * sum(1 for entry in results if entry["passed"]) / len(cases)
    baseline_accuracy = 100 * sum(1 for value in baseline.values() if value) / len(baseline)
    failing = sorted(entry["id"] for entry in results if not entry["passed"])
    decision = {
        "verdict": "pass" if accuracy >= 90 else "blocked",
        "reason": "ok" if accuracy >= 90 else "regression",
        "failing": failing,
        "regressions": sorted(case_id for case_id in failing if baseline.get(case_id)),
        "accuracy": accuracy,
        "baseline_accuracy": baseline_accuracy,
        "drop": baseline_accuracy - accuracy,
        "cases_total": len(cases),
        "cases_run": len(results),
        "calls": len(results),
        "tokens": tokens,
        "seconds": clock() - started,
        "cap": {"tokens": config["cap"]["tokens"], "seconds": config["cap"]["seconds"], "exceeded": None},
        "versions": {"prompt_version": candidate["prompt_version"], "model": candidate["model"], "config_hash": "", "set_version": config["manifest"]["version"]},
        "results": results,
    }
    os.makedirs(config["archive"], exist_ok=True)
    decision["archive"] = os.path.join(config["archive"], "results.json")
    with open(decision["archive"], "w", encoding="utf-8") as file:
        json.dump(decision, file)
    return decision
