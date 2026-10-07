"""Independent v1 guild checks; execute with: python3 -I -B FILE MISSION WORKSPACE."""
import copy
import importlib.util
import json
import math
import random
import signal
import sys
import time
from collections import Counter
from contextlib import redirect_stdout
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKS = []


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def check(name, operation, optional=False):
    # An optional check is the hidden bonus of a mission: it can only add, it never fails the run.
    flag = {"optional": True} if optional else {}
    try:
        detail = operation()
        CHECKS.append({"name": name, "passed": True, "detail": detail or "Published contract verified.", **flag})
    except Exception as error:
        label = "Environment blocked" if getattr(error, "environment_blocked", False) else name
        CHECKS.append({"name": label, "passed": False, "detail": f"{type(error).__name__}: {error}"[:1800], **flag})


def load(file, name):
    require(file.is_file() and not file.is_symlink(), f"Expected a regular file: {file.name}")
    spec = importlib.util.spec_from_file_location(name, file)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {file.name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        del sys.modules[name]
        raise
    return module


def same(left, right):
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(same(left[k], right[k]) for k in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(same(a, b) for a, b in zip(left, right))
    return left == right


def unique_strings(items, label):
    require(isinstance(items, list) and all(isinstance(x, str) and x for x in items), f"{label}: expected a list of nonempty strings")
    require(len(set(items)) == len(items), f"{label}: duplicate reference")
    return set(items)


def keyed(items, label, key="id"):
    require(isinstance(items, list) and all(isinstance(x, dict) for x in items), f"{label}: expected a list of objects")
    unique_strings([x.get(key) for x in items], label)
    return {x[key]: x for x in items}


def validate_manifest(result, ticket):
    require(isinstance(result, dict), "build_manifest must return a dictionary")
    for field in ("schema_version", "ticket_id", "revision"):
        require(same(result.get(field), ticket[field]), f"{field} must follow this ticket: {ticket[field]!r}")
    requirements = keyed(result.get("requirements"), "requirements")
    cases = keyed(result.get("cases"), "cases")
    assumptions = keyed(result.get("assumptions"), "assumptions", "question")
    opened = unique_strings(result.get("open_questions"), "open_questions")
    require(unique_strings(result.get("exclusions"), "exclusions") == set(ticket["exclusions"]), "Preserve exactly the ticket's excluded scope")
    facts = {x["id"]: x for x in ticket["facts"]}
    owners, kinds = {}, {}
    for identity, requirement in requirements.items():
        declarations = keyed(requirement.get("facts"), f"{identity}.facts")
        require(bool(declarations), f"{identity}: a requirement needs supplied facts")
        kinds[identity] = set()
        for fact_id, declaration in declarations.items():
            require(fact_id in facts and fact_id not in owners, f"{fact_id}: unknown or repeated supplied fact")
            fact = facts[fact_id]
            require(same(declaration.get("value"), fact["value"]) and declaration.get("unit") == fact["unit"], f"{fact_id}: expected {fact['value']!r} {fact['unit']}, got {declaration!r}")
            require(declaration.get("source", "fact") == "fact", f"{fact_id}: supplied facts cannot be assumptions")
            owners[fact_id] = identity
            kinds[identity].update(fact["cases"])
    require(set(owners) == set(facts), f"Missing supplied facts: {sorted(set(facts) - set(owners))}")
    questions = {x["id"]: x for x in ticket["questions"]}
    require(not (set(assumptions) & opened) and set(assumptions) | opened == set(questions), "Each question needs one allowed assumption OR an explicit open question")
    assumption_kinds = {}
    for question, assumption in assumptions.items():
        require(assumption.get("source") == "assumption", f"{question}: an open choice is not a supplied fact")
        options = {x["id"]: x for x in questions[question]["options"]}
        require(assumption.get("choice") in options, f"{question}: choose a published option or leave it open")
        assumption_kinds[question] = set(options[assumption["choice"]]["cases"])
    coverage, choice_coverage = set(), set()
    for identity, case in cases.items():
        linked = unique_strings(case.get("requirements"), f"{identity}.requirements")
        chosen = unique_strings(case.get("assumptions"), f"{identity}.assumptions")
        kind = case.get("kind")
        require(isinstance(kind, str), f"{identity}: missing case kind")
        require(bool(linked or chosen), f"{identity}: a case must reference a requirement or assumption")
        for owner in linked:
            require(owner in kinds and kind in kinds[owner], f"{identity}: {kind!r} is not a published case for {owner}")
            coverage.add((owner, kind))
        for owner in chosen:
            require(owner in assumption_kinds and kind in assumption_kinds[owner], f"{identity}: unknown assumption or incompatible case kind")
            choice_coverage.add((owner, kind))
    for fact_id, fact in facts.items():
        for kind in fact["cases"]:
            require((owners[fact_id], kind) in coverage, f"{fact_id}: missing linked {kind} observation")
    for question, expected in assumption_kinds.items():
        require(all((question, kind) in choice_coverage for kind in expected), f"{question}: chosen implication has no observable case")


def briefing(workspace):
    candidate = load(workspace / "manifest.py", "candidate_manifest")
    original = json.loads((ROOT / "labs/briefing/ticket.json").read_text())
    second = json.loads((ROOT / "labs/briefing/ticket-v2.json").read_text())
    third = json.loads((ROOT / "labs/briefing/ticket-v3.json").read_text())
    fresh = copy.deepcopy(third)
    rng = random.SystemRandom()
    fresh["ticket_id"] = f"remote-outpost-{rng.randrange(10000, 99999)}"
    fresh["facts"][3]["value"] = rng.randrange(13, 39)
    fresh["facts"].reverse()
    previous = []
    def exercise(ticket):
        before = copy.deepcopy(ticket)
        first = candidate.build_manifest(ticket)
        for artifact, snapshot in previous:
            require(same(artifact, snapshot), "A new ticket changed a previously returned artifact")
        require(same(ticket, before), "build_manifest mutated the supplied ticket")
        validate_manifest(first, before)
        saved = copy.deepcopy(first)
        repeated_input = copy.deepcopy(before)
        again = candidate.build_manifest(repeated_input)
        require(same(repeated_input, before), "build_manifest mutated input on a repeated call")
        require(same(first, saved) and same(again, saved), "Repeat calls must preserve prior artifacts and return the same manifest")
        previous.append((first, saved))
        return f"Ticket {ticket['ticket_id']} revision {ticket['revision']}: fact values, units, references and observation coverage verified; prose not graded."
    for label, ticket in (("original", original), ("changed limits", second), ("changed actor/payload/scope", third), ("fresh facts", fresh), ("original after changes", original)):
        check(f"Manifest: {label}", lambda t=ticket: exercise(t))
    two_questions = copy.deepcopy(original)
    two_questions["revision"] = 4
    two_questions["questions"].append({"id": "retry_policy", "options": [
        {"id": "none", "cases": ["single_attempt"], "implication": "A failed dispatch is reported once and never retried."},
        {"id": "bounded", "cases": ["retry_limit", "retry_exhausted"], "implication": "Dispatch retries up to a fixed count, then reports failure."}]})
    check("bonus: a ticket with a second open question keeps every question answered or open", lambda: exercise(two_questions), optional=True)


BOUNDS = {"daily_requests": (0, 10**9), "peak_multiplier": (1, 1000), "mean_ms": (0, 60000),
          "response_bytes": (0, 10**7), "written_bytes": (0, 10**7),
          "retention_days": (0, 3650), "storage_multiplier": (1, 100)}


def capacity_expected(workload):
    d, p, m, r, w, days, overhead = (Fraction(str(workload[k])) for k in BOUNDS)
    # Direct dimensional products keep this oracle independent of the learner's intermediate values.
    return {"average_rps": d / 86400, "peak_rps": d * p / 86400,
            "in_flight": d * p * m / 86400000, "peak_bytes_per_second": d * p * r / 86400,
            "retained_bytes": d * w * days * overhead,
            "peak_MB_per_second": d * p * r / 86400000000,
            "retained_GiB": d * w * days * overhead / 1073741824}


def capacity(workspace):
    candidate = load(workspace / "capacity.py", "candidate_capacity")
    sample = dict(daily_requests=86400, peak_multiplier=4, mean_ms=250, response_bytes=2000,
                  written_bytes=500, retention_days=7, storage_multiplier=2, p95_ms=900)
    def exercise(values):
        saved = copy.deepcopy(values)
        repeated_input = copy.deepcopy(saved)
        outputs = [candidate.estimate(values), candidate.estimate(repeated_input)]
        require(same(values, saved), "estimate mutated workload")
        require(same(repeated_input, saved), "estimate mutated workload on a repeated call")
        for result in outputs:
            require(isinstance(result, dict), "estimate must return a dictionary")
            for key, expected in capacity_expected(saved).items():
                value = result.get(key)
                require(isinstance(value, (int, float, Decimal, Fraction)) and not isinstance(value, bool), f"{key}: expected a number, got {value!r}")
                require(math.isfinite(value) and value >= 0, f"{key}: expected finite nonnegative output")
                actual = Fraction(value) if isinstance(value, (Decimal, Fraction)) else Fraction(str(value))
                tolerance = max(Fraction(1, 10**9), abs(expected) / 10**9)
                require(abs(actual - expected) <= tolerance, f"{key}: expected {float(expected):.14g}, got {value!r}")
        require(outputs[0] == outputs[1], "Repeated estimates must agree")
    valid = [("published example", sample), ("fractional concurrency", {**sample, "daily_requests": 43200, "peak_multiplier": 1.5, "mean_ms": 125}),
             ("zero traffic", {**sample, "daily_requests": 0}), ("zero retention", {**sample, "retention_days": 0}),
             ("zero bytes and residence", {**sample, "response_bytes": 0, "written_bytes": 0, "mean_ms": 0}),
             ("integer-valued float retention", {**sample, "retention_days": 7.0}),
             ("fractional response bytes", {**sample, "response_bytes": 0.5}),
             ("fractional written bytes", {**sample, "written_bytes": 0.5}),
             ("upper bounds", {key: high for key, (_, high) in BOUNDS.items()}),
             ("p95 is not mean", {**sample, "p95_ms": 57000}), ("extra metadata", {**sample, "note": "estimate only"})]
    rng = random.SystemRandom()
    for index in range(6):
        valid.append((f"fresh workload {index + 1}", dict(daily_requests=rng.randrange(1, 999999) / 8,
                     peak_multiplier=rng.randrange(8, 400) / 8, mean_ms=rng.randrange(1, 9000) / 8,
                     response_bytes=rng.randrange(1, 10000) / 8, written_bytes=rng.randrange(1, 10000) / 8,
                     retention_days=rng.randrange(1, 3650), storage_multiplier=rng.randrange(8, 800) / 8)))
    valid.append(("sample after fresh values", sample))
    for name, values in valid:
        check(f"Capacity: {name}", lambda v=values: exercise(v))
    def invalid(values):
        before = repr(values)
        try:
            candidate.estimate(values)
        except ValueError:
            require(repr(values) == before, "estimate mutated rejected input")
            return
        raise AssertionError("Expected ValueError for this invalid workload")
    for key, (low, high) in BOUNDS.items():
        for label, value in (("below range", low - 1), ("above range", high + 1), ("bool", True),
                             ("string", "7"), ("null", None), ("NaN", float("nan")),
                             ("infinity", float("inf")), ("negative infinity", -float("inf")), ("huge integer", 10**400)):
            check(f"Reject {key}: {label}", lambda k=key, v=value: invalid({**sample, k: v}))
        missing = {k: v for k, v in sample.items() if k != key}
        check(f"Reject {key}: missing", lambda v=missing: invalid(v))
    for label, values in (("fractional retention", {**sample, "retention_days": 0.5}),
                          ("invalid despite zero traffic", {**sample, "daily_requests": 0, "mean_ms": -1}),
                          ("list", []), ("null workload", None), ("string workload", "workload")):
        check(f"Reject {label}", lambda v=values: invalid(v))
    check("Capacity: sample after rejected inputs", lambda: exercise(sample))
    junk = {**sample, "p95_ms": "unknown", "owner": {"team": "ops"}, "tags": ["peak", 3, None], "budget_usd": float("inf"), "comment": ""}
    def ignored_fields():
        exercise(junk)
        require(candidate.estimate(copy.deepcopy(junk)) == candidate.estimate(copy.deepcopy(sample)), "Junk in fields outside the seven inputs changed the outputs")
    check("bonus: junk in ignored fields leaves the seven outputs unchanged", ignored_fields, optional=True)


PROBE_NAMES = {"create", "replay", "conflict", "read", "query", "missing", "effects"}
PROBE_FIELDS = {"create": ("id", "item", "quantity"), "replay": ("id", "item", "quantity"),
                "conflict": ("error",), "read": ("id", "item", "quantity", "view"),
                "query": ("id", "quantity", "view"), "missing": ("error",), "effects": ("effects",)}


def probe_report(result, status, failed=None):
    require(isinstance(result, dict) and result.get("status") == status, f"Expected {status} report, got {result!r}")
    items = keyed(result.get("checks"), "probe checks", "name")
    require(set(items) == PROBE_NAMES, "Return exactly the seven published check names")
    for name, item in items.items():
        require(type(item.get("passed")) is bool and isinstance(item.get("detail"), str) and item["detail"].strip(), f"{name}: a bool verdict and nonempty evidence detail are required")
    actual_failed = {name for name, item in items.items() if not item["passed"]}
    if failed is not None:
        require(actual_failed == failed, f"Expected failed checks {sorted(failed)}, got {sorted(actual_failed)}")
    else:
        require(bool(actual_failed), "Transport failure cannot claim all checks passed")
    return f"{status}; failed checks: {', '.join(sorted(actual_failed)) or 'none'}."


def observed_requests(server, delivery, interrupted=False):
    require(server.attempts == [(method, path) for method, path, _ in server.trace], "Unexpected HTTP method or unobserved request")
    expected_posts = [("POST", "/deliveries", delivery), ("POST", "/deliveries", delivery),
                      ("POST", "/deliveries", {**delivery, "quantity": delivery["quantity"] + 1})]
    post_count = min(3, len(server.trace))
    require(all(same(list(actual), list(expected)) for actual, expected in zip(server.trace[:3], expected_posts)) and (interrupted or post_count == 3), "Send create, replay and conflict in order with the supplied delivery")
    require(server.request_media[:3] == ["application/json"] * post_count, "Each POST must send JSON Content-Type")
    identity = delivery["id"]
    expected_gets = [("GET", f"/deliveries/{identity}?view=full", None),
                     ("GET", f"/deliveries/{identity}?view=summary", None),
                     ("GET", f"/deliveries/{identity}/missing?view=full", None), ("GET", "/stats", None)]
    normalize = lambda row: json.dumps(row, sort_keys=True)
    actual, expected = Counter(map(normalize, server.trace[3:])), Counter(map(normalize, expected_gets))
    require(actual <= expected if interrupted else actual == expected, "Observe each required GET exactly once; no extra requests/redirects")
    get_names = {normalize(row): name for row, name in zip(expected_gets, ("read", "query", "missing", "effects"))}
    return ["create", "replay", "conflict"][:post_count] + [get_names[normalize(row)] for row in server.trace[3:]]


def contract(workspace):
    fixtures = load(ROOT / "labs/contract/fixtures.py", "architect_owned_fixtures")
    candidate = load(workspace / "probe.py", "candidate_probe")
    rng = random.SystemRandom()
    def scenario():
        return {"delivery": {"id": f"d-{rng.randrange(10**6, 10**9)}", "item": rng.choice(["water", "cable", "café supply"]), "quantity": rng.randrange(1, 101)}, "timeout_s": rng.choice((0.2, 0.6, 1.0))}
    def responding(style, fault, failed, values):
        before = copy.deepcopy(values)
        with fixtures.fixture(style, fault) as (url, server):
            result = candidate.probe(url, values)
            require(same(before, values), "probe mutated scenario")
            detail = probe_report(result, "failed" if failed else "passed", failed)
            observed_requests(server, before["delivery"])
            if not fault:
                require(server.effects == 1 and server.records == {before["delivery"]["id"]: before["delivery"]}, "Probe must leave exactly the original delivery and one effect")
            return f"{style}/{fault or 'conforming'}: {detail} Observed {len(server.trace)} requests, {server.effects} effect(s)."
    for style in ("direct", "table"):
        values = scenario()
        boundary = scenario()
        boundary["delivery"] = {"id": "x", "item": "a", "quantity": 1} if style == "table" else {"id": "Z" * 40, "item": "雪" * 40, "quantity": 100}
        for label, data in (("fresh", values), ("repeat on fresh fixture", values), ("changed values", boundary)):
            check(f"HTTP probe: {style} {label}", lambda s=style, v=data: responding(s, None, set(), v))
    faults = {"status": {"create"}, "http_error": {"create"}, "redirect": {"create"}, "header": {"create"}, "media": {"create"}, "body": {"create"}, "boolean": {"create"},
              "quantity_type": {"create"}, "json": {"create"}, "path": {"missing"}, "query": {"query"},
              "error_body": {"missing"}, "duplicate": {"effects"}, "conflict_effect": {"read", "query", "effects"}}
    for target in sorted(PROBE_NAMES - {"create"}):
        for fault in ("status", "header", "media", "body", "json"):
            faults[f"{fault}:{target}"] = {target}
    for target, fields in PROBE_FIELDS.items():
        for field in fields:
            for fault in ("wrong", "missing"):
                faults[f"{fault}:{target}:{field}"] = {target}
    for fault, failed in faults.items():
        values = scenario()
        if fault == "boolean":
            values["delivery"]["quantity"] = 1
        check(f"HTTP probe rejects {fault}", lambda f=fault, bad=failed, v=values: responding("direct", f, bad, v))
    def transport(kind):
        values = scenario()
        before = copy.deepcopy(values)
        with fixtures.fixture(fault="disconnect" if kind == "unavailable" else "timeout") as (url, server):
            result = candidate.probe(url, values)
            require(len(server.trace) == len(server.attempts) == 1, "Observe the first request and stop after transport failure; do not retry")
            method, path, payload = server.trace[0]
            require((method, path) == ("POST", "/deliveries") and same(payload, before["delivery"]), "Transport scenario must attempt the supplied create request")
        require(same(before, values), "probe mutated scenario on transport failure")
        return probe_report(result, kind, PROBE_NAMES)
    for kind in ("timeout", "unavailable"):
        check(f"HTTP probe distinguishes {kind}", lambda k=kind: transport(k))
    fractional = scenario()
    fractional["delivery"]["quantity"] = 1
    check("bonus: a create reply carrying quantity 1.0 fails create only; 1.0 is not the integer 1", lambda: responding("direct", "quantity_float", {"create"}, fractional), optional=True)

    def budget_case(target, expires):
        values = scenario()
        values["timeout_s"] = 0.2 if expires else 1.0
        before = copy.deepcopy(values)
        delay = 0.8 if expires else 0.55
        with fixtures.fixture(delay=(target, delay)) as (url, server):
            result = candidate.probe(url, values)
            returned_at = time.monotonic()
            require(same(values, before), "probe mutated scenario in a budget case")
            require(server.delay_received_at is not None, f"Expected actual {target} request before the delayed response")
            elapsed = returned_at - server.delay_received_at
            clock_gap = max(server.delay_max_gap, returned_at - server.delay_last_tick)
            if clock_gap > 0.25:
                raise fixtures.FixtureUnavailable("Delay controller was descheduled for >0.25s; rerun on an idle machine")
            if not expires and server.delay_released_at is not None and server.delay_released_at - server.delay_received_at > 0.8:
                raise fixtures.FixtureUnavailable("In-budget response gate was released too late; rerun on an idle machine")
            names = observed_requests(server, before["delivery"], interrupted=expires)
            if expires:
                require(names and names[-1] == target, "Stop on the timed-out request without retries or later requests")
                detail = probe_report(result, "timeout", PROBE_NAMES - set(names[:-1]))
                require(elapsed <= values["timeout_s"] + 0.5, f"Return budget exceeded: observed {elapsed:.3f}s after request receipt; allowed {values['timeout_s'] + 0.5:.3f}s including scheduling tolerance")
            else:
                detail = probe_report(result, "passed", set())
                require(server.delay_released_at is not None, "The probe must receive the delayed reply, not invent success")
                require(server.records == {before["delivery"]["id"]: before["delivery"]} and server.effects == 1, "Delayed success must retain one original effect")
            return f"{target}: timeout_s={values['timeout_s']}, gate={delay}s, observed={elapsed:.3f}s; {detail}"
    for target in ("create", "effects"):
        for expires in (False, True):
            check(f"HTTP budget: {target} {'after' if expires else 'before'} deadline", lambda t=target, e=expires: budget_case(t, e))


class EvaluationDeadline(BaseException):
    pass


def deadline(*_):
    raise EvaluationDeadline("Verification exceeded 30 seconds; bound requests and remove infinite loops")


def main():
    signal.signal(signal.SIGALRM, deadline)
    signal.setitimer(signal.ITIMER_REAL, 30)
    try:
        require(len(sys.argv) == 3, "Usage: verify_architect.py MISSION WORKSPACE")
        mission, workspace = sys.argv[1], Path(sys.argv[2]).resolve()
        require(mission in ("briefing", "capacity", "contract"), "Unknown architect mission")
        sys.path.insert(0, str(workspace))
        with redirect_stdout(sys.stderr):
            {"briefing": briefing, "capacity": capacity, "contract": contract}[mission](workspace)
    except BaseException as error:
        CHECKS.append({"name": "Run the architect lab", "passed": False, "detail": f"{type(error).__name__}: {error}"[:1800]})
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
    print(json.dumps({"checks": CHECKS}))
    return 0 if CHECKS and all(item["passed"] for item in CHECKS if not item.get("optional")) else 1


if __name__ == "__main__":
    sys.exit(main())
