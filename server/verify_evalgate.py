"""Release-gate checks for the Evalgate mission; run outside the learner workspace.

Nothing here calls a model. The scripted runner below plays the model-plus-judge of a pipeline: it
answers from a script keyed by case id and attempt number, charges fixed tokens and seconds, advances
a fake clock and records every call. It is a labeled test tool. Every expected number is recomputed
by hand with Fraction from the script, never by running a reference gate.
"""
import hashlib
import importlib.util
import json
import math
import os
import random
import re
import sys
from collections import Counter
from fractions import Fraction

MISSION, WORKSPACE = sys.argv[1:3]
CHECKS = []
TOLERANCE = 1e-9
NAME = re.compile(r"^(\d+)-([^-]+)-(.+)\.json$")


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def check(name, operation, optional=False):
    # An optional check is the hidden bonus of a mission: it can only add, it never fails the run.
    flag = {"optional": True} if optional else {}
    try:
        detail = operation()
        CHECKS.append({"name": name, "passed": True, "detail": detail or "Scripted runner calls and the archived decision verified.", **flag})
    except Exception as error:
        CHECKS.append({"name": name, "passed": False, "detail": f"{type(error).__name__}: {error}"[:1500], **flag})


class Clock:
    """Injected time source: only the runner moves it."""

    def __init__(self, start):
        self.now = float(start)

    def __call__(self):
        return self.now


class Runner:
    """Scripted model-plus-judge: outcome per (case id, attempt), fixed usage per case, every call recorded."""

    def __init__(self, manifest, script, usage, clock):
        self.by_id = {case["id"]: case for case in manifest["cases"]}
        self.script, self.usage, self.clock = script, usage, clock
        self.calls, self.attempts = [], Counter()

    def __call__(self, case):
        require(isinstance(case, dict) and case.get("id") in self.by_id, f"run_case must receive a case dict from the manifest, got {case!r}")
        case_id = case["id"]
        require(case == self.by_id[case_id], f"run_case must receive the manifest case {case_id} verbatim")
        index = self.attempts[case_id]
        self.attempts[case_id] += 1
        outcomes = self.script.get(case_id, [True])
        passed = bool(outcomes[min(index, len(outcomes) - 1)])
        tokens, seconds = self.usage[case_id]
        self.clock.now += seconds
        self.calls.append(case_id)
        return {"passed": passed, "tokens": tokens, "seconds": seconds, "output": f"scripted {case_id} attempt {index + 1}"}


def fresh_world(rng, n):
    prefix = "".join(rng.choice("abcdefghjkmnpqrstuvwxyz") for _ in range(3))
    categories = ["stock", "runbook", "incident", "reserve", "abstain"]
    # n + 3 dev cases and 5 held-out ones; the subset is a shuffled sample, so a gate that runs "all dev cases" is caught.
    cases = [{"id": f"{prefix}-{i:02d}", "split": "dev", "category": categories[i % 5], "request": f"dev request {i}", "expected": f"expected {i}"} for i in range(n + 3)]
    heldout = [{"id": f"{prefix}-h{i:02d}", "split": "heldout", "category": categories[i % 5], "request": f"held-out request {i}", "expected": f"expected h{i}"} for i in range(5)]
    manifest = {"version": f"supply-set-v{rng.randint(2, 9)}", "cases": cases + heldout}
    usage = {case["id"]: (rng.randint(40, 160), rng.randint(2, 9) / 10) for case in manifest["cases"]}
    subset = rng.sample([case["id"] for case in cases], n)
    return manifest, usage, subset


def config_hash(config):
    return hashlib.sha256(json.dumps(config, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def percent(count, total):
    return Fraction(100 * count, total)


def close(value, wanted, tolerance=TOLERANCE):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and abs(Fraction(str(value)) - Fraction(wanted)) <= Fraction(str(tolerance))


def trial():
    require(MISSION == "evalgate", "Unknown mission")
    sys.path.insert(0, WORKSPACE)
    spec = importlib.util.spec_from_file_location("candidate_evalgate", os.path.join(WORKSPACE, "gate.py"))
    if spec is None or spec.loader is None:
        raise ImportError("Cannot load gate.py")
    candidate = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = candidate
    spec.loader.exec_module(candidate)
    require(callable(getattr(candidate, "run_gate", None)), "gate.py must define run_gate(config, *, candidate, baseline_results, run_case, clock)")
    require(isinstance(getattr(candidate, "ConfigError", None), type) and issubclass(candidate.ConfigError, BaseException), "gate.py must define the ConfigError exception class")
    rng = random.Random()
    archive_root = os.path.join(WORKSPACE, ".verify-archive")

    def archive_dir(label):
        path = os.path.join(archive_root, f"{label}-{rng.randint(1000, 9999)}")
        os.makedirs(path, exist_ok=True)
        return path

    def make_config(manifest, subset, archive, *, max_drop, floor, runs=1, pass_min=1, tokens=10**9, seconds=10**9, extra=None):
        thresholds = {"max_drop": max_drop, "floor": floor}
        if extra:
            thresholds.update(extra)
        return {"manifest": manifest, "subset": list(subset), "thresholds": thresholds, "repeat": {"runs": runs, "pass_min": pass_min}, "cap": {"tokens": tokens, "seconds": seconds}, "archive": archive}

    def baseline_for(manifest, failed=(), prompt_version="v1", model="relay-small"):
        return {"prompt_version": prompt_version, "model": model, "cases": {case["id"]: case["id"] not in failed for case in manifest["cases"]}}

    def files_of(archive):
        return sorted(name for name in os.listdir(archive))

    def gate(config, *, who, baseline, runner, clock):
        before = files_of(config["archive"])
        clock.before = before
        decision = candidate.run_gate(config, candidate=who, baseline_results=baseline, run_case=runner, clock=clock)
        require(isinstance(decision, dict), "run_gate must return a decision dict")
        missing = {"verdict", "reason", "failing", "regressions", "accuracy", "baseline_accuracy", "drop", "cases_total", "cases_run", "calls", "tokens", "seconds", "cap", "versions", "archive", "results"} - set(decision)
        require(not missing, f"The decision is missing keys: {sorted(missing)}")
        require(decision["verdict"] in ("pass", "blocked"), f"verdict must be pass or blocked, got {decision['verdict']!r}")
        for key in ("cases_total", "cases_run", "calls", "tokens"):
            require(type(decision[key]) is int, f"{key} must be an integer, got {decision[key]!r}")
        require(decision["calls"] == len(runner.calls), f"calls {decision['calls']} must count every run_case invocation ({len(runner.calls)})")
        require(decision["tokens"] == sum(runner.usage[case_id][0] for case_id in runner.calls), "tokens must be the sum of the runner results' tokens")
        require(decision["cases_run"] == len(set(runner.calls)), f"cases_run {decision['cases_run']} must count the cases that received a call ({len(set(runner.calls))})")
        require(close(decision["seconds"], Fraction(str(clock.now)) - Fraction(str(getattr(clock, "started", clock.now))), 1e-3), f"seconds {decision['seconds']!r} must be clock() - started at the end of the run")
        require(isinstance(decision["failing"], list) and decision["failing"] == sorted(decision["failing"]), "failing must be a sorted list of ids")
        require(isinstance(decision["regressions"], list) and decision["regressions"] == sorted(decision["regressions"]), "regressions must be a sorted list of ids")
        require(isinstance(decision["results"], list) and [entry.get("id") for entry in decision["results"]] == list(dict.fromkeys(runner.calls)), "results must list every case that was run, in run order")
        for entry in decision["results"]:
            attempts = entry.get("attempts")
            require(isinstance(attempts, list) and len(attempts) == runner.attempts[entry["id"]], f"results[{entry['id']}].attempts must hold every run_case result for the case")
            require(all(set(result) >= {"passed", "tokens", "seconds", "output"} for result in attempts), "attempts must be the run_case results verbatim")
        cap = decision["cap"]
        require(isinstance(cap, dict) and cap.get("tokens") == config["cap"]["tokens"] and cap.get("seconds") == config["cap"]["seconds"], "cap must echo the configured tokens and seconds")
        return decision

    def archived(config, *, who, clock, decision):
        """Versions and the archive file of one run; clock.before holds the files present when the run started."""
        before = clock.before
        after = files_of(config["archive"])
        new = sorted(set(after) - set(before))
        require(len(new) == 1 and len(after) == len(before) + 1, f"One run must add exactly one archive file, before {before}, after {after}")
        path = decision["archive"]
        require(isinstance(path, str) and os.path.abspath(path) == os.path.abspath(os.path.join(config["archive"], new[0])), f"decision.archive must be the path of the new file {new[0]}, got {path!r}")
        match = NAME.match(new[0])
        require(match is not None, f"archive file name must be <stamp>-<prompt_version>-<model>.json, got {new[0]!r}")
        require(match.group(1) == str(int(clock.started * 1000)) and match.group(2) == who["prompt_version"] and match.group(3) == who["model"], f"archive file name must be {int(clock.started * 1000)}-{who['prompt_version']}-{who['model']}.json, got {new[0]!r}")
        with open(os.path.join(config["archive"], new[0]), "r", encoding="utf-8") as file:
            archived = json.load(file)
        require(archived == json.loads(json.dumps(decision)), "The archived file must parse to the returned decision")
        versions = decision["versions"]
        require(isinstance(versions, dict), "versions must be a dict")
        for key, wanted in (("prompt_version", who["prompt_version"]), ("model", who["model"]), ("config_hash", config_hash(config)), ("set_version", config["manifest"]["version"])):
            require(versions.get(key) == wanted, f"versions.{key} must be {wanted!r}, got {versions.get(key)!r}")

    def start_clock():
        clock = Clock(1_700_000_000 + rng.randint(0, 60_000_000) + rng.randint(0, 999) / 1000)
        clock.started = clock.now
        return clock

    def regression():
        n = rng.choice([16, 20, 25])
        manifest, usage, subset = fresh_world(rng, n)
        baseline_failed = rng.sample(subset, 1)
        regressed = sorted(rng.sample([case_id for case_id in subset if case_id not in baseline_failed], 3))
        script = {case_id: [False] for case_id in regressed}
        config = make_config(manifest, subset, archive_dir("regression"), max_drop=100 / n, floor=50)
        clock = start_clock()
        runner = Runner(manifest, script, usage, clock)
        decision = gate(config, who={"prompt_version": "v2", "model": "relay-small"}, baseline=baseline_for(manifest, baseline_failed), runner=runner, clock=clock)
        require(runner.calls == subset, "Every subset case runs exactly once, in subset order; held-out cases never run")
        require(decision["verdict"] == "blocked" and decision["reason"] == "regression", f"Three regressions on {n} cases exceed max_drop {100 / n:g}: expected blocked/regression, got {decision['verdict']}/{decision['reason']}")
        require(decision["failing"] == regressed, f"failing must name the failed cases {regressed}, got {decision['failing']}")
        require(decision["regressions"] == regressed, f"regressions must name the failed cases the baseline passed {regressed}, got {decision['regressions']}")
        require(close(decision["accuracy"], percent(n - 3, n)), f"accuracy must be {float(percent(n - 3, n))!r}, got {decision['accuracy']!r}")
        require(close(decision["baseline_accuracy"], percent(n - 1, n)), f"baseline_accuracy over the subset must be {float(percent(n - 1, n))!r}, got {decision['baseline_accuracy']!r}")
        require(close(decision["drop"], percent(2, n)), f"drop must be {float(percent(2, n))!r}, got {decision['drop']!r}")
        require(decision["cases_total"] == n and decision["cap"]["exceeded"] is None, "cases_total is the subset size and cap.exceeded is null when the run finished")
        return f"{n} cases, 3 seeded regressions: blocked with the ids named, drop {float(percent(2, n)):g} points over max_drop {100 / n:g}."
    check("A seeded regression blocks the release and names the failing cases", regression)

    def tolerance():
        n = rng.choice([16, 20, 25])
        manifest, usage, subset = fresh_world(rng, n)
        one = rng.choice(subset)
        config = make_config(manifest, subset, archive_dir("tolerance"), max_drop=100 / n, floor=60)
        clock = start_clock()
        runner = Runner(manifest, {one: [False]}, usage, clock)
        decision = gate(config, who={"prompt_version": "v2", "model": "relay-small"}, baseline=baseline_for(manifest), runner=runner, clock=clock)
        require(decision["verdict"] == "pass" and decision["reason"] == "ok", f"A drop exactly at max_drop passes: expected pass/ok, got {decision['verdict']}/{decision['reason']}")
        require(decision["failing"] == [one] and decision["regressions"] == [one], "A passing release still names the case it failed")
        weak = sorted(rng.sample(subset, n // 5))  # 80 % both sides: no drop, above the floor, far from the starter's 0.9
        config = make_config(manifest, subset, archive_dir("steady"), max_drop=5, floor=70)
        clock = start_clock()
        runner = Runner(manifest, {case_id: [False] for case_id in weak}, usage, clock)
        decision = gate(config, who={"prompt_version": "v2", "model": "relay-small"}, baseline=baseline_for(manifest, weak), runner=runner, clock=clock)
        require(decision["verdict"] == "pass" and decision["reason"] == "ok" and close(decision["drop"], 0), f"No drop at 80 % against an 80 % baseline passes with floor 70: got {decision['verdict']}/{decision['reason']} drop {decision['drop']!r}")
        require(decision["failing"] == weak and decision["regressions"] == [], "Cases the baseline also failed are in failing, not in regressions")
        low = sorted(rng.sample(subset, (2 * n) // 5))  # 60 % both sides: no drop, under the floor
        config = make_config(manifest, subset, archive_dir("floor"), max_drop=5, floor=70)
        clock = start_clock()
        runner = Runner(manifest, {case_id: [False] for case_id in low}, usage, clock)
        decision = gate(config, who={"prompt_version": "v2", "model": "relay-small"}, baseline=baseline_for(manifest, low), runner=runner, clock=clock)
        require(decision["verdict"] == "blocked" and decision["reason"] == "floor", f"60 % against a 60 % baseline has no drop but is under the floor of 70: expected blocked/floor, got {decision['verdict']}/{decision['reason']}")
        return f"Drop of {100 / n:g} at max_drop {100 / n:g} passed; 80 % steady passed; 60 % under floor 70 blocked."
    check("A drop inside the declared tolerance passes; the hard floor still blocks", tolerance)

    def repeats():
        n = rng.choice([16, 20, 25])
        manifest, usage, subset = fresh_world(rng, n)
        flaky, persistent, late = rng.sample(subset, 3)
        script = {flaky: [False, True, True], persistent: [False, False, False], late: [False, True, False]}
        config = make_config(manifest, subset, archive_dir("repeat"), max_drop=200 / n, floor=50, runs=3, pass_min=2)
        clock = start_clock()
        runner = Runner(manifest, script, usage, clock)
        decision = gate(config, who={"prompt_version": "v2", "model": "relay-small"}, baseline=baseline_for(manifest), runner=runner, clock=clock)
        expected_calls = []
        for case_id in subset:
            expected_calls.extend([case_id] * {flaky: 3, persistent: 2, late: 3}.get(case_id, 1))
        require(runner.calls == expected_calls, f"Reruns follow the failure immediately and stop at the deciding attempt: F T T → 3 calls, F F → 2, F T F → 3; expected {Counter(expected_calls)}, got {Counter(runner.calls)}")
        require(decision["failing"] == sorted([persistent, late]), f"failing must be {sorted([persistent, late])}, got {decision['failing']}")
        require(decision["verdict"] == "pass" and decision["reason"] == "ok", f"Two persistent failures on {n} cases are inside max_drop {200 / n:g}: expected pass/ok, got {decision['verdict']}/{decision['reason']}")
        require(close(decision["accuracy"], percent(n - 2, n)), f"accuracy counts the flaky case as passed: expected {float(percent(n - 2, n))!r}, got {decision['accuracy']!r}")
        entry = next(item for item in decision["results"] if item["id"] == flaky)
        require(entry["passed"] is True and [result["passed"] for result in entry["attempts"]] == [False, True, True], "The flaky case's results entry holds its three attempts and passed")
        return "F T T passed with 3 calls, F F failed with 2, F T F failed with 3; every other case ran once."
    check("A flaky case passes on rerun inside the repeat policy; a persistent failure stops at the deciding attempt", repeats)

    def token_cap():
        n = rng.choice([16, 20, 25])
        manifest, usage, subset = fresh_world(rng, n)
        j = rng.randint(4, n - 3)
        last = subset[j - 1]  # scripted F F under runs 3 / pass_min 2: call j is its first attempt and leaves it undecided
        cumulative = [sum(usage[case_id][0] for case_id in subset[:k]) for k in range(n + 1)]
        config = make_config(manifest, subset, archive_dir("tokencap"), max_drop=5, floor=50, runs=3, pass_min=2, tokens=cumulative[j] - 1)
        clock = start_clock()
        runner = Runner(manifest, {last: [False, False]}, usage, clock)
        who = {"prompt_version": "v2", "model": "relay-small"}
        decision = gate(config, who=who, baseline=baseline_for(manifest), runner=runner, clock=clock)
        require(runner.calls == subset[:j], f"The cap of {cumulative[j] - 1} tokens is exceeded by call {j}; no further run_case call may happen, not even the rerun of {last}, got {len(runner.calls)} calls")
        require(decision["verdict"] == "blocked" and decision["reason"] == "cap" and decision["cap"]["exceeded"] == "tokens", f"Expected blocked/cap with cap.exceeded 'tokens', got {decision['verdict']}/{decision['reason']} {decision['cap']!r}")
        require(decision["tokens"] == cumulative[j] and decision["cases_run"] == j and decision["cases_total"] == n, f"tokens {decision['tokens']} must be {cumulative[j]}, cases_run {decision['cases_run']} must be {j}")
        require(decision["accuracy"] is None and decision["baseline_accuracy"] is None and decision["drop"] is None, "accuracy, baseline_accuracy and drop are null when the cap stopped the run")
        require(decision["results"][-1]["id"] == last and decision["results"][-1]["passed"] is None, f"{last} failed once under runs 3 / pass_min 2 and was interrupted: its results entry must have passed null, got {decision['results'][-1].get('passed')!r}")
        require(decision["failing"] == [] and decision["regressions"] == [], f"An undecided case is neither failing nor a regression, got {decision['failing']}")
        archived(config, who=who, clock=clock, decision=decision)
        return f"Stopped after call {j} of {n} with {cumulative[j]} tokens over a cap of {cumulative[j] - 1}; the interrupted case stayed undecided; partial result archived."
    check("The token cap stops the run early with the counts", token_cap)

    def time_cap():
        n = rng.choice([16, 20, 25])
        manifest, usage, subset = fresh_world(rng, n)
        j = rng.randint(4, n - 3)
        last = subset[j - 1]  # scripted F under runs 1: call j both decides the case and passes the cap
        elapsed = 0.0
        for case_id in subset[:j]:
            elapsed += usage[case_id][1]
        config = make_config(manifest, subset, archive_dir("timecap"), max_drop=5, floor=50, seconds=round(elapsed - 0.05, 3))
        clock = start_clock()
        runner = Runner(manifest, {last: [False]}, usage, clock)
        decision = gate(config, who={"prompt_version": "v2", "model": "relay-small"}, baseline=baseline_for(manifest), runner=runner, clock=clock)
        require(runner.calls == subset[:j], f"The injected clock passes the cap of {config['cap']['seconds']} s at call {j}; no further run_case call may happen, got {len(runner.calls)} calls")
        require(decision["verdict"] == "blocked" and decision["reason"] == "cap" and decision["cap"]["exceeded"] == "seconds", f"Expected blocked/cap with cap.exceeded 'seconds', got {decision['verdict']}/{decision['reason']} {decision['cap']!r}")
        require(close(decision["seconds"], Fraction(str(round(elapsed, 6))), 1e-3) and decision["cases_run"] == j, f"seconds {decision['seconds']!r} must be the clock's {elapsed:.3f} and cases_run must be {j}")
        require(decision["results"][-1]["id"] == last and decision["results"][-1]["passed"] is False, f"{last} was decided by the very call that passed the cap: its results entry must have passed false, got {decision['results'][-1].get('passed')!r}")
        require(decision["failing"] == [last] and decision["regressions"] == [last], f"failing and regressions cover the cases decided before the stop, {[last]}, got {decision['failing']}")
        return f"Stopped after call {j} of {n} at {elapsed:.2f} s by the injected clock over a cap of {config['cap']['seconds']} s; the deciding call still named its case."
    check("The time cap stops the run by the injected clock", time_cap)

    def archive():
        n = rng.choice([16, 20, 25])
        manifest, usage, subset = fresh_world(rng, n)
        archive_path = archive_dir("archive")
        config = make_config(manifest, subset, archive_path, max_drop=5, floor=50)
        baseline = baseline_for(manifest)
        snapshots = {}
        for prompt_version in ("v1", "v2", "v2"):
            clock = start_clock()
            runner = Runner(manifest, {}, usage, clock)
            who = {"prompt_version": prompt_version, "model": "relay-small"}
            decision = gate(config, who=who, baseline=baseline, runner=runner, clock=clock)
            archived(config, who=who, clock=clock, decision=decision)
            for name in files_of(archive_path):
                with open(os.path.join(archive_path, name), "rb") as file:
                    content = file.read()
                require(snapshots.get(name, content) == content, f"Earlier archive file {name} changed; the archive is append-only")
                snapshots[name] = content
            require(decision["versions"]["prompt_version"] == prompt_version, "versions.prompt_version follows the candidate")
        require(len(files_of(archive_path)) == 3, f"Three runs leave three files, found {files_of(archive_path)}")
        clock = start_clock()
        taken = os.path.join(archive_path, f"{int(clock.now * 1000)}-v3-relay-small.json")
        with open(taken, "w", encoding="utf-8") as file:
            file.write("{\"keep\": \"me\"}\n")
        runner = Runner(manifest, {}, usage, clock)
        raised = False
        try:
            candidate.run_gate(config, candidate={"prompt_version": "v3", "model": "relay-small"}, baseline_results=baseline, run_case=runner, clock=clock)
        except Exception:
            raised = True
        with open(taken, "r", encoding="utf-8") as file:
            require(file.read() == "{\"keep\": \"me\"}\n", "An existing archive file must never be overwritten")
        require(raised, "Writing over an existing archive path must raise instead of replacing the file")
        require(len(files_of(archive_path)) == 4, "The refused run must not leave an extra file")
        return "Three runs archived with prompt, model, config hash and set version; a taken path raised and stayed intact."
    check("Results are archived with every version and the archive is append-only", archive)

    def held_out():
        n = rng.choice([16, 20, 25])
        manifest, usage, subset = fresh_world(rng, n)
        heldout_id = rng.choice([case["id"] for case in manifest["cases"] if case["split"] == "heldout"])
        archive_path = archive_dir("heldout")
        baseline = baseline_for(manifest)
        bad_subsets = {
            "a held-out id": subset[:-1] + [heldout_id],
            "an id missing from the manifest": subset[:-1] + [subset[-1] + "-x"],
            "a duplicate id": subset + [subset[0]],
            "an empty subset": [],
        }
        for label, bad in bad_subsets.items():
            clock = start_clock()
            runner = Runner(manifest, {}, usage, clock)
            rejected = False
            try:
                candidate.run_gate(make_config(manifest, bad, archive_path, max_drop=5, floor=50), candidate={"prompt_version": "v2", "model": "relay-small"}, baseline_results=baseline, run_case=runner, clock=clock)
            except candidate.ConfigError:
                rejected = True
            require(rejected, f"A subset with {label} must raise ConfigError")
            require(runner.calls == [], f"A subset with {label} must be rejected before any run_case call, saw {len(runner.calls)}")
            require(files_of(archive_path) == [], f"A subset with {label} must not write an archive file")
        clock = start_clock()
        runner = Runner(manifest, {}, usage, clock)
        orphan = dict(baseline, cases={case_id: value for case_id, value in baseline["cases"].items() if case_id != subset[2]})
        rejected = False
        try:
            candidate.run_gate(make_config(manifest, subset, archive_path, max_drop=5, floor=50), candidate={"prompt_version": "v2", "model": "relay-small"}, baseline_results=orphan, run_case=runner, clock=clock)
        except candidate.ConfigError:
            rejected = True
        require(rejected and runner.calls == [] and files_of(archive_path) == [], "A subset id without a baseline outcome must raise ConfigError before any call or file")
        clock = start_clock()
        runner = Runner(manifest, {}, usage, clock)
        rejected = False
        try:
            candidate.run_gate(make_config(manifest, subset, archive_path, max_drop=5, floor=50, runs=2, pass_min=3), candidate={"prompt_version": "v2", "model": "relay-small"}, baseline_results=baseline, run_case=runner, clock=clock)
        except candidate.ConfigError:
            rejected = True
        require(rejected and runner.calls == [], "pass_min above runs must raise ConfigError before any call")
        return "Held-out, unknown, duplicate and empty subsets, a missing baseline outcome and pass_min > runs were rejected with no call and no file."
    check("A subset touching the held-out split is rejected before any run", held_out)

    def transfer():
        n = rng.choice([16, 20, 25])
        manifest, usage, subset = fresh_world(rng, n)
        baseline_failed = sorted(rng.sample(subset, 2))
        archive_path = archive_dir("transfer")
        config = make_config(manifest, subset, archive_path, max_drop=5, floor=50)
        baseline = baseline_for(manifest, baseline_failed)
        clock = start_clock()
        first_who = {"prompt_version": "v2", "model": "relay-small"}
        first = gate(config, who=first_who, baseline=baseline, runner=Runner(manifest, {baseline_failed[0]: [False]}, usage, clock), clock=clock)
        archived(config, who=first_who, clock=clock, decision=first)
        with open(first["archive"], "rb") as file:
            first_bytes = file.read()
        clock = start_clock()
        other = f"relay-large-{rng.randint(10, 99)}"
        second_who = {"prompt_version": "v2", "model": other}
        second = gate(config, who=second_who, baseline=baseline, runner=Runner(manifest, {}, usage, clock), clock=clock)
        archived(config, who=second_who, clock=clock, decision=second)
        require(second["versions"]["model"] == other and second["versions"]["prompt_version"] == "v2", "Only the model id changes in the versions")
        require(second["versions"]["config_hash"] == first["versions"]["config_hash"] == config_hash(config), "The config hash is the same for the same config")
        require(second["versions"]["set_version"] == first["versions"]["set_version"] == manifest["version"], "The set version is the manifest version for both runs")
        require(close(second["baseline_accuracy"], percent(n - 2, n)) and close(first["baseline_accuracy"], percent(n - 2, n)), "Both runs compare against the same baseline accuracy over the subset")
        require(close(second["accuracy"], percent(n, n)) and close(second["drop"], -percent(2, n)) and second["verdict"] == "pass", f"The second model passes everything: accuracy 100, drop {-float(percent(2, n)):g}, got {second['accuracy']!r} {second['drop']!r} {second['verdict']}")
        require(os.path.basename(second["archive"]).endswith(f"-v2-{other}.json") and second["archive"] != first["archive"], "The new archive entry carries the new model id")
        with open(first["archive"], "rb") as file:
            require(file.read() == first_bytes, "The first model's archive entry stays unchanged")
        return f"Second run with model {other}: new archive entry, same config hash and set version, same baseline accuracy."
    check("Changing only the model id archives a new run against the same baseline", transfer)

    def paired_bonus():
        n = 20
        manifest, usage, subset = fresh_world(rng, n)
        improved, *regressed = rng.sample(subset, 3)
        archive_path = archive_dir("paired")
        config = make_config(manifest, subset, archive_path, max_drop=2.5, floor=50, extra={"paired_z": 1.96})
        clock = start_clock()
        decision = gate(config, who={"prompt_version": "v2", "model": "relay-small"}, baseline=baseline_for(manifest, [improved]), runner=Runner(manifest, {case_id: [False] for case_id in regressed}, usage, clock), clock=clock)
        # Differences: two -1, one +1, seventeen 0. mean = -1/20, sum of squares about the mean = 59/20, variance = 59/380.
        mean, variance = Fraction(-1, 20), Fraction(59, 380)
        se = math.sqrt(variance / n)
        require(close(decision["drop"], 5) and decision["verdict"] == "pass" and decision["reason"] == "noise", f"A 5-point drop from two regressions and one improvement on 20 cases is noise under z=1.96: expected pass/noise, got {decision['verdict']}/{decision['reason']}")
        paired = decision.get("paired")
        require(isinstance(paired, dict) and paired.get("n") == n and paired.get("z") == 1.96, f"decision.paired must carry n, mean, se, z and upper, got {paired!r}")
        require(close(paired.get("mean"), mean) and close(paired.get("se"), Fraction(str(se)), 1e-6) and close(paired.get("upper"), Fraction(str(float(mean) + 1.96 * se)), 1e-6), f"paired must be mean {float(mean)}, se {se:.6f}, upper {float(mean) + 1.96 * se:.6f}, got {paired!r}")
        many = sorted(rng.sample(subset, 6))
        clock = start_clock()
        decision = gate(config, who={"prompt_version": "v3", "model": "relay-small"}, baseline=baseline_for(manifest), runner=Runner(manifest, {case_id: [False] for case_id in many}, usage, clock), clock=clock)
        require(decision["verdict"] == "blocked" and decision["reason"] == "regression" and decision["regressions"] == many, f"Six regressions on 20 cases have upper < 0 and block: got {decision['verdict']}/{decision['reason']}")
        return "Two regressions and one improvement on 20 cases passed as noise; six regressions blocked."
    check("bonus: the paired rule separates noise from a regression", paired_bonus, optional=True)


try:
    trial()
except Exception as error:
    CHECKS.append({"name": "Load release gate", "passed": False, "detail": f"{type(error).__name__}: {error}"[:1500]})
print(json.dumps({"checks": CHECKS}))
sys.exit(0 if CHECKS and all(item["passed"] for item in CHECKS if not item.get("optional")) else 1)
