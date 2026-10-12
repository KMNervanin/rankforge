"""Release gate: dataclasses, a generator over attempts and pathlib."""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean, stdev

EPSILON = 1e-9


class ConfigError(Exception):
    """Raised when the gate configuration is not usable."""


@dataclass
class Policy:
    runs: int
    pass_min: int

    def __post_init__(self):
        if not 1 <= self.pass_min <= self.runs:
            raise ConfigError(f"repeat policy needs 1 <= pass_min <= runs, got {self}")

    def decide(self, outcomes):
        """True/False once the attempts so far decide the case, None while another attempt is needed."""
        if not outcomes:
            return None
        passes, fails = outcomes.count(True), outcomes.count(False)
        if fails == 0 or passes >= self.pass_min:
            return True
        if fails > self.runs - self.pass_min:
            return False
        return None


@dataclass
class CaseRun:
    id: str
    passed: bool | None = None
    attempts: list = field(default_factory=list)

    def as_dict(self):
        return {"id": self.id, "passed": self.passed, "attempts": self.attempts}


@dataclass
class Ledger:
    cap_tokens: int
    cap_seconds: float
    clock: object
    started: float
    tokens: int = 0
    calls: int = 0
    exceeded: str | None = None

    def charge(self, result):
        self.calls += 1
        self.tokens += int(result["tokens"])
        if self.tokens > self.cap_tokens:
            self.exceeded = "tokens"
        elif self.clock() - self.started > self.cap_seconds:
            self.exceeded = "seconds"
        return self.exceeded is None


def canonical_hash(config):
    return hashlib.sha256(json.dumps(config, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def selected_cases(config, baseline):
    manifest = config["manifest"]
    index = {case["id"]: case for case in manifest["cases"]}
    subset = list(config["subset"])
    if not subset or len(set(subset)) != len(subset):
        raise ConfigError("the subset must be a non-empty list of distinct case ids")
    for case_id in subset:
        if case_id not in index:
            raise ConfigError(f"{case_id} is not in manifest {manifest['version']}")
        if index[case_id].get("split") != "dev":
            raise ConfigError(f"{case_id} belongs to the {index[case_id].get('split')!r} split, not dev")
        if case_id not in baseline:
            raise ConfigError(f"{case_id} has no baseline outcome")
    return [index[case_id] for case_id in subset]


def attempts(case, policy, run_case):
    """Yields run_case results for one case until the policy decides it."""
    outcomes = []
    while policy.decide(outcomes) is None:
        result = run_case(case)
        outcomes.append(bool(result["passed"]))
        yield result


def paired(diffs, z):
    n = len(diffs)
    average = mean(diffs)
    se = (stdev(diffs) / math.sqrt(n)) if n > 1 else 0.0
    return {"n": n, "mean": average, "se": se, "z": z, "upper": average + z * se}


def run_gate(config, *, candidate, baseline_results, run_case, clock):
    baseline = baseline_results["cases"]
    cases = selected_cases(config, baseline)
    policy = Policy(int(config["repeat"]["runs"]), int(config["repeat"]["pass_min"]))
    ledger = Ledger(config["cap"]["tokens"], config["cap"]["seconds"], clock, clock())
    runs: list[CaseRun] = []
    for case in cases:
        current = CaseRun(case["id"])
        runs.append(current)
        for result in attempts(case, policy, run_case):
            current.attempts.append(result)
            if not ledger.charge(result):
                break
        current.passed = policy.decide([bool(result["passed"]) for result in current.attempts])
        if ledger.exceeded:
            break

    decided = [run for run in runs if run.passed is not None]
    failing = sorted(run.id for run in decided if run.passed is False)
    thresholds = config["thresholds"]
    decision = {
        "failing": failing,
        "regressions": sorted(case_id for case_id in failing if baseline[case_id]),
        "cases_total": len(cases), "cases_run": len(runs), "calls": ledger.calls, "tokens": ledger.tokens, "seconds": clock() - ledger.started,
        "cap": {"tokens": ledger.cap_tokens, "seconds": ledger.cap_seconds, "exceeded": ledger.exceeded},
        "versions": {"prompt_version": candidate["prompt_version"], "model": candidate["model"], "config_hash": canonical_hash(config), "set_version": config["manifest"]["version"]},
        "results": [run.as_dict() for run in runs],
    }
    if ledger.exceeded:
        decision.update(verdict="blocked", reason="cap", accuracy=None, baseline_accuracy=None, drop=None)
    else:
        n = len(cases)
        accuracy = 100 * sum(run.passed for run in decided) / n
        baseline_accuracy = 100 * sum(bool(baseline[run.id]) for run in decided) / n
        drop = baseline_accuracy - accuracy
        decision.update(accuracy=accuracy, baseline_accuracy=baseline_accuracy, drop=drop)
        z = thresholds.get("paired_z")
        if z is not None:
            decision["paired"] = paired([int(run.passed) - int(bool(baseline[run.id])) for run in decided], float(z))
        if accuracy + EPSILON < float(thresholds["floor"]):
            decision.update(verdict="blocked", reason="floor")
        elif drop > float(thresholds["max_drop"]) + EPSILON:
            noise = z is not None and decision["paired"]["upper"] >= 0
            decision.update(verdict="pass" if noise else "blocked", reason="noise" if noise else "regression")
        else:
            decision.update(verdict="pass", reason="ok")

    archive = Path(config["archive"])
    archive.mkdir(parents=True, exist_ok=True)
    target = archive / f"{int(ledger.started * 1000)}-{candidate['prompt_version']}-{candidate['model']}.json"
    decision["archive"] = str(target)
    with target.open("x", encoding="utf-8") as file:
        json.dump(decision, file, ensure_ascii=False)
    return decision
