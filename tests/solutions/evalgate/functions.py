"""Release gate: plain functions over dicts, os.path and hashlib."""
import hashlib
import json
import math
import os

TOLERANCE = 1e-9


class ConfigError(Exception):
    """Raised when the gate configuration is not usable."""


def config_hash(config):
    canonical = json.dumps(config, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate(config, baseline_results):
    manifest = config["manifest"]
    by_id = {case["id"]: case for case in manifest["cases"]}
    subset = list(config["subset"])
    if not subset:
        raise ConfigError("the subset is empty")
    if len(set(subset)) != len(subset):
        raise ConfigError("the subset repeats a case id")
    for case_id in subset:
        case = by_id.get(case_id)
        if case is None:
            raise ConfigError(f"{case_id} is not in manifest {manifest['version']}")
        if case.get("split") != "dev":
            raise ConfigError(f"{case_id} is in the {case.get('split')!r} split; the gate runs dev cases only")
        if case_id not in baseline_results["cases"]:
            raise ConfigError(f"{case_id} has no baseline outcome")
    runs, pass_min = int(config["repeat"]["runs"]), int(config["repeat"]["pass_min"])
    if not 1 <= pass_min <= runs:
        raise ConfigError(f"repeat policy needs 1 <= pass_min <= runs, got pass_min={pass_min}, runs={runs}")
    return [by_id[case_id] for case_id in subset], runs, pass_min


def paired_summary(subset_ids, outcomes, baseline, z):
    diffs = [int(outcomes[case_id]) - int(bool(baseline[case_id])) for case_id in subset_ids]
    n = len(diffs)
    mean = sum(diffs) / n
    variance = sum((d - mean) ** 2 for d in diffs) / (n - 1) if n > 1 else 0.0
    se = math.sqrt(variance / n)
    return {"n": n, "mean": mean, "se": se, "z": z, "upper": mean + z * se}


def run_gate(config, *, candidate, baseline_results, run_case, clock):
    cases, runs, pass_min = validate(config, baseline_results)
    cap_tokens, cap_seconds = config["cap"]["tokens"], config["cap"]["seconds"]
    thresholds = config["thresholds"]
    baseline = baseline_results["cases"]
    started = clock()
    results, outcomes, tokens, calls, exceeded = [], {}, 0, 0, None

    for case in cases:
        entry = {"id": case["id"], "passed": None, "attempts": []}
        results.append(entry)
        passes = fails = 0
        while True:
            result = run_case(case)
            entry["attempts"].append(result)
            calls += 1
            tokens += int(result["tokens"])
            passes += 1 if result["passed"] else 0
            fails += 0 if result["passed"] else 1
            if fails == 0 or passes >= pass_min:
                entry["passed"] = True
            elif fails >= runs - pass_min + 1:
                entry["passed"] = False
            if tokens > cap_tokens:
                exceeded = "tokens"
            elif clock() - started > cap_seconds:
                exceeded = "seconds"
            if exceeded or entry["passed"] is not None:
                break
        if entry["passed"] is not None:
            outcomes[case["id"]] = entry["passed"]
        if exceeded:
            break

    decision = {
        "cases_total": len(cases), "cases_run": len(results), "calls": calls, "tokens": tokens, "seconds": clock() - started,
        "cap": {"tokens": cap_tokens, "seconds": cap_seconds, "exceeded": exceeded},
        "versions": {"prompt_version": candidate["prompt_version"], "model": candidate["model"], "config_hash": config_hash(config), "set_version": config["manifest"]["version"]},
        "results": results,
    }
    decided = [case_id for case_id in outcomes]
    decision["failing"] = sorted(case_id for case_id in decided if not outcomes[case_id])
    decision["regressions"] = sorted(case_id for case_id in decision["failing"] if baseline[case_id])
    if exceeded:
        decision.update(verdict="blocked", reason="cap", accuracy=None, baseline_accuracy=None, drop=None)
    else:
        n = len(cases)
        accuracy = 100.0 * sum(1 for case_id in decided if outcomes[case_id]) / n
        baseline_accuracy = 100.0 * sum(1 for case_id in decided if baseline[case_id]) / n
        drop = baseline_accuracy - accuracy
        decision.update(accuracy=accuracy, baseline_accuracy=baseline_accuracy, drop=drop)
        z = thresholds.get("paired_z")
        if z is not None:
            decision["paired"] = paired_summary(decided, outcomes, baseline, float(z))
        if accuracy < float(thresholds["floor"]) - TOLERANCE:
            decision.update(verdict="blocked", reason="floor")
        elif drop > float(thresholds["max_drop"]) + TOLERANCE:
            if z is not None and decision["paired"]["upper"] >= 0:
                decision.update(verdict="pass", reason="noise")
            else:
                decision.update(verdict="blocked", reason="regression")
        else:
            decision.update(verdict="pass", reason="ok")

    os.makedirs(config["archive"], exist_ok=True)
    path = os.path.join(config["archive"], f"{int(started * 1000)}-{candidate['prompt_version']}-{candidate['model']}.json")
    decision["archive"] = path
    with open(path, "x", encoding="utf-8") as file:
        json.dump(decision, file, indent=2, ensure_ascii=False)
    return decision
