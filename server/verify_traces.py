"""Trace-reading and failure-taxonomy checks for the Traces mission; run outside the learner workspace.

Everything is offline. Verify carries its own annotation fixtures with fresh ids and counts, recomputes
every expected number by hand, and audits the learner's own reading of the shipped traces with an
independent reconciliation plus the recorded pass-or-failure outcome of every shipped trace.
"""
import copy
import importlib.util
import json
import os
import random
import re
import sys
from collections import Counter

MISSION, WORKSPACE = sys.argv[1:3]
CHECKS = []
RNG = random.Random()
MIN_TRACES, HAND_NOTES, TOLERANCE = 100, 30, 12
TRACE_ID = re.compile(r"[a-z]{2}-[0-9]{4}")
SHIPPED_IDS = [f"tr-{index:04d}" for index in range(1, 121)]
# Shipped traces recorded without a planted failure; every other shipped trace carries one.
PASS_IDS = {"tr-0005", "tr-0008", "tr-0010", "tr-0012", "tr-0016", "tr-0018", "tr-0022", "tr-0024", "tr-0027", "tr-0028", "tr-0029", "tr-0030", "tr-0032", "tr-0035", "tr-0038", "tr-0041", "tr-0044", "tr-0047", "tr-0048", "tr-0050", "tr-0052", "tr-0055", "tr-0057", "tr-0058", "tr-0060", "tr-0061", "tr-0063", "tr-0067", "tr-0068", "tr-0073", "tr-0080", "tr-0081", "tr-0082", "tr-0089", "tr-0090", "tr-0091", "tr-0092", "tr-0094", "tr-0096", "tr-0100", "tr-0104", "tr-0105", "tr-0108", "tr-0109", "tr-0115", "tr-0116", "tr-0117", "tr-0119"}
LABEL_POOL = ["wrong item", "source invented", "unit dropped", "cut short", "refusal", "tool fault hidden", "count wrong", "stale stock"]
PREFIXES = ("coverage", "empty", "unknown", "label", "count", "missing", "total")


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def check(name, operation, optional=False):
    # An optional check is the hidden bonus of a mission: it can only add, it never fails the run.
    flag = {"optional": True} if optional else {}
    try:
        detail = operation()
        CHECKS.append({"name": name, "passed": True, "detail": detail or "Fresh annotation fixtures verified.", **flag})
    except Exception as error:
        CHECKS.append({"name": name, "passed": False, "detail": f"{type(error).__name__}: {error}"[:1500], **flag})


def fixture(size, labels, *, notes_after=None):
    """Annotations with fresh ids: every label used at least once, notes on the first HAND_NOTES lines."""
    base = RNG.randint(1000, 8000)
    ids = [f"vx-{base + index:04d}" for index in range(size)]
    assigned = list(labels) + ["pass"] + [RNG.choice(labels + ["pass"] * 3) for _ in range(size - len(labels) - 1)]
    RNG.shuffle(assigned)
    records = []
    for index, (trace_id, label) in enumerate(zip(ids, assigned)):
        noted = index < HAND_NOTES or (notes_after if notes_after is not None else RNG.random() < 0.5)
        records.append({"trace_id": trace_id, "open_note": f"read {trace_id}: {label}" if noted else "", "first_failure": label})
    return records


def expected_taxonomy(records, definitions=None):
    # Hand recomputation: Counter over labels, ids in file order, count descending then name.
    counts = Counter(record["first_failure"] for record in records if record["first_failure"] != "pass")
    categories = []
    for name in sorted(counts, key=lambda label: (-counts[label], label)):
        ids = [record["trace_id"] for record in records if record["first_failure"] == name]
        categories.append({"name": name, "definition": (definitions or {}).get(name, ""), "trace_ids": ids, "count": counts[name]})
    return {"total": len(records), "passes": sum(1 for record in records if record["first_failure"] == "pass"), "categories": categories}


def definitions_for(records):
    taxonomy = expected_taxonomy(records)
    return {category["name"]: f"{category['name']} observed first, for example in {category['trace_ids'][0]}." for category in taxonomy["categories"]}


def write_jsonl(path, records, *, blank_line=False):
    with open(path, "w", encoding="utf-8") as file:
        for index, record in enumerate(records):
            file.write(json.dumps(record) + "\n")
            if blank_line and index == 1:
                file.write("\n")
    return path


def prefixes(messages):
    require(isinstance(messages, list) and all(isinstance(message, str) for message in messages), f"reconcile must return a list of strings, got {messages!r}")
    return [message.split(":", 1)[0].strip() for message in messages]


def expect(messages, needed, allowed, mention):
    found = prefixes(messages)
    require(all(prefix in needed or prefix in allowed or prefix == "example" for prefix in found), f"Unexpected prefixes {sorted(set(found) - needed - allowed)} in {messages!r}")
    for prefix in needed:
        hits = [message for message in messages if message.startswith(prefix + ":")]
        require(hits, f"Expected a {prefix}: message, got {messages!r}")
        require(any(mention in message for message in hits), f"The {prefix}: message must name {mention!r}, got {hits!r}")


def audit(records, taxonomy):
    """Verify's own reconciliation of the learner's workspace taxonomy; independent of taxonomy.py."""
    problems = []
    labels = {record["trace_id"]: record["first_failure"] for record in records}
    cited = {}
    for category in taxonomy.get("categories", []):
        name, ids = category.get("name"), list(category.get("trace_ids") or [])
        if not isinstance(name, str) or not name:
            problems.append("a category has no name")
            continue
        if not ids:
            problems.append(f"category {name!r} cites no traces")
        if not str(category.get("definition") or "").strip():
            problems.append(f"category {name!r} has no definition")
        if category.get("count") != len(set(ids)):
            problems.append(f"category {name!r} says count {category.get('count')!r} but cites {len(set(ids))} distinct traces")
        for trace_id in ids:
            if trace_id not in labels:
                problems.append(f"category {name!r} cites {trace_id}, which is not annotated")
            elif labels[trace_id] != name:
                problems.append(f"{trace_id} is cited by {name!r} but annotated {labels[trace_id]!r}")
            else:
                cited[trace_id] = name
    for record in records:
        if record["first_failure"] != "pass" and cited.get(record["trace_id"]) != record["first_failure"]:
            problems.append(f"{record['trace_id']} is annotated {record['first_failure']!r} but no such category cites it")
    passes = sum(1 for record in records if record["first_failure"] == "pass")
    failures = sum(int(category.get("count") or 0) for category in taxonomy.get("categories", []) if isinstance(category.get("count"), int))
    if taxonomy.get("total") != len(records) or taxonomy.get("passes") != passes or failures + passes != len(records):
        problems.append(f"totals: taxonomy says {taxonomy.get('total')!r} total, {taxonomy.get('passes')!r} passes, {failures} failures; annotations hold {len(records)} with {passes} passes")
    return problems


def read_workspace_annotations():
    path = os.path.join(WORKSPACE, "annotations.jsonl")
    require(os.path.exists(path), "annotations.jsonl is missing from the workspace")
    records, seen = [], set()
    with open(path, encoding="utf-8") as file:
        for number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except ValueError as error:
                raise AssertionError(f"annotations.jsonl line {number} is not valid JSON: {error}") from None
            require(isinstance(record, dict), f"annotations.jsonl line {number} is not a JSON object")
            trace_id, label = record.get("trace_id"), record.get("first_failure")
            require(isinstance(trace_id, str) and trace_id in SHIPPED_IDS, f"annotations.jsonl line {number}: {trace_id!r} is not a shipped trace id")
            require(trace_id not in seen, f"{trace_id} is annotated twice")
            require(isinstance(label, str) and label.strip(), f"{trace_id}: first_failure must be one non-empty label or pass, got {label!r}")
            seen.add(trace_id)
            records.append({"trace_id": trace_id, "open_note": record.get("open_note") if isinstance(record.get("open_note"), str) else "", "first_failure": label})
    return records


def trial():
    require(MISSION == "traces", "Unknown mission")
    sys.path.insert(0, WORKSPACE)
    spec = importlib.util.spec_from_file_location("candidate_traces", os.path.join(WORKSPACE, "taxonomy.py"))
    if spec is None or spec.loader is None:
        raise ImportError("Cannot load taxonomy.py")
    candidate = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = candidate
    spec.loader.exec_module(candidate)
    for name in ("load_annotations", "build_taxonomy", "reconcile", "recurrence"):
        require(callable(getattr(candidate, name, None)), f"taxonomy.py must define {name}(...)")
    scratch = os.path.join(WORKSPACE, ".verify-annotations.jsonl")

    labels = RNG.sample(LABEL_POOL, RNG.randint(4, 6))
    consistent = fixture(RNG.randint(MIN_TRACES, MIN_TRACES + 30), labels)
    definitions = definitions_for(consistent)
    expected = expected_taxonomy(consistent, definitions)

    def loading():
        loaded = candidate.load_annotations(write_jsonl(scratch, consistent, blank_line=True))
        require(isinstance(loaded, list) and len(loaded) == len(consistent), f"Expected {len(consistent)} records, got {len(loaded) if isinstance(loaded, list) else type(loaded).__name__}")
        for index, (got, want) in enumerate(zip(loaded, consistent)):
            require(isinstance(got, dict) and {key: got.get(key) for key in want} == want, f"Record {index} differs: {got!r} vs {want!r}")
        for name, broken, mention in [
            ("a duplicated trace id", consistent[:40] + [dict(consistent[7])], consistent[7]["trace_id"]),
            ("a list of two labels", consistent[:40] + [{"trace_id": "vx-0999", "open_note": "two things", "first_failure": [labels[0], labels[1]]}], "vx-0999"),
            ("a missing first_failure", consistent[:40] + [{"trace_id": "vx-0998", "open_note": "forgot the label"}], "vx-0998"),
            ("an empty first_failure", consistent[:40] + [{"trace_id": "vx-0997", "open_note": "blank", "first_failure": ""}], "vx-0997"),
        ]:
            write_jsonl(scratch, broken)
            try:
                candidate.load_annotations(scratch)
            except ValueError as error:
                require(mention in str(error), f"The ValueError for {name} must name {mention}, got {error!r}")
            else:
                raise AssertionError(f"load_annotations must raise ValueError on {name}")
        return f"{len(consistent)} records loaded in order; duplicate, two-label, missing and empty labels raised ValueError."
    check("Annotations load as one record per trace with a single first-failure label or pass", loading)

    def building():
        built = candidate.build_taxonomy(consistent, definitions)
        require(isinstance(built, dict), "build_taxonomy must return a dict")
        require(built.get("total") == expected["total"] and built.get("passes") == expected["passes"], f"total/passes {built.get('total')!r}/{built.get('passes')!r}, expected {expected['total']}/{expected['passes']}")
        got = built.get("categories")
        require(isinstance(got, list) and [category.get("name") for category in got] == [category["name"] for category in expected["categories"]], f"Categories must be the distinct labels ordered by count then name: got {[c.get('name') for c in got] if isinstance(got, list) else got!r}, expected {[c['name'] for c in expected['categories']]}")
        for mine, theirs in zip(got, expected["categories"]):
            require(mine.get("trace_ids") == theirs["trace_ids"], f"Category {theirs['name']!r} must cite its traces in annotation order")
            require(mine.get("count") == theirs["count"] and mine.get("definition") == theirs["definition"], f"Category {theirs['name']!r}: count {mine.get('count')!r} definition {mine.get('definition')!r}")
        half = consistent[: len(consistent) // 2]
        again = candidate.build_taxonomy(half)
        wanted = expected_taxonomy(half)
        require(again.get("total") == wanted["total"] and again.get("passes") == wanted["passes"], "A second annotation set must produce its own totals")
        require([(c.get("name"), c.get("count"), c.get("trace_ids"), c.get("definition")) for c in again.get("categories", [])] == [(c["name"], c["count"], c["trace_ids"], "") for c in wanted["categories"]], "A second annotation set must produce its own categories with empty definitions when none are given")
        return f"{len(expected['categories'])} categories with counts {[c['count'] for c in expected['categories']]} recomputed from {len(consistent)} annotations."
    check("Taxonomy counts come from the annotations and every category cites its traces", building)

    def silent():
        messages = candidate.reconcile(consistent, copy.deepcopy(expected))
        require(messages == [], f"A consistent taxonomy must reconcile with no messages, got {messages!r}")
        return "A consistent taxonomy produced no messages."
    check("Reconcile is silent on a consistent taxonomy", silent)

    def planted():
        categories = expected["categories"]
        stranger = f"vx-{RNG.randint(9000, 9999):04d}"
        pass_id = next(record["trace_id"] for record in consistent if record["first_failure"] == "pass")
        plants = []
        taxonomy = copy.deepcopy(expected)
        taxonomy["categories"][0]["trace_ids"].append(stranger)
        taxonomy["categories"][0]["count"] += 1
        plants.append(("an unknown trace id", taxonomy, {"unknown"}, {"total"}, stranger))
        taxonomy = copy.deepcopy(expected)
        taxonomy["categories"][1]["count"] += 2
        plants.append(("a count above the citations", taxonomy, {"count"}, {"total"}, categories[1]["name"]))
        taxonomy = copy.deepcopy(expected)
        taxonomy["categories"][2]["trace_ids"].append(pass_id)
        taxonomy["categories"][2]["count"] += 1
        plants.append(("a cited pass", taxonomy, {"label"}, {"total"}, pass_id))
        taxonomy = copy.deepcopy(expected)
        # Drop from the largest category so the plant never empties one.
        dropped = taxonomy["categories"][0]["trace_ids"].pop()
        taxonomy["categories"][0]["count"] -= 1
        plants.append(("an uncited failure", taxonomy, {"missing"}, {"total"}, dropped))
        taxonomy = copy.deepcopy(expected)
        taxonomy["total"] += 1
        plants.append(("a wrong total", taxonomy, {"total"}, set(), "total"))
        taxonomy = copy.deepcopy(expected)
        taxonomy["categories"][0]["trace_ids"].append(taxonomy["categories"][0]["trace_ids"][0])
        taxonomy["categories"][0]["count"] += 1
        plants.append(("a repeated id counted twice", taxonomy, {"count"}, {"total"}, categories[0]["name"]))
        taxonomy = copy.deepcopy(expected)
        moved = categories[0]["trace_ids"][1]
        taxonomy["categories"][1]["trace_ids"].append(moved)
        taxonomy["categories"][1]["count"] += 1
        plants.append(("one trace cited by two categories", taxonomy, {"label"}, {"total"}, moved))
        for name, taxonomy, needed, allowed, mention in plants:
            try:
                expect(candidate.reconcile(consistent, taxonomy), needed, allowed, mention)
            except AssertionError as error:
                raise AssertionError(f"{name}: {error}")
        return f"{len(plants)} planted inconsistencies each reported with the published prefix."
    check("Reconcile names every planted inconsistency by its prefix", planted)

    def empty_category():
        taxonomy = copy.deepcopy(expected)
        taxonomy["categories"].append({"name": "latency", "definition": "The answer took too long.", "trace_ids": [], "count": 0})
        expect(candidate.reconcile(consistent, taxonomy), {"empty"}, set(), "latency")
        unread = {"total": len(consistent), "passes": expected["passes"], "categories": [{"name": name, "definition": f"{name} as imagined", "trace_ids": [], "count": RNG.randint(3, 9)} for name in ("hallucination", "tone", "formatting")]}
        messages = candidate.reconcile(consistent, unread)
        found = prefixes(messages)
        require(found.count("empty") >= 3, f"Three categories without trace references must each be reported as empty:, got {messages!r}")
        require(all(prefix in PREFIXES or prefix == "example" for prefix in found), f"Unpublished prefixes in {messages!r}")
        return "A category with no trace references and a taxonomy written before reading were both rejected."
    check("A category with no trace references is rejected", empty_category)

    def coverage():
        short = consistent[: MIN_TRACES - 1]
        messages = candidate.reconcile(short, expected_taxonomy(short, definitions_for(short)))
        expect(messages, {"coverage"}, set(), "coverage")
        exact = [dict(record) for record in consistent[:MIN_TRACES]]
        blank = RNG.randint(HAND_NOTES - 5, HAND_NOTES - 1)
        exact[blank]["open_note"] = "   "
        expect(candidate.reconcile(exact, expected_taxonomy(exact, definitions_for(exact))), {"coverage"}, set(), exact[blank]["trace_id"])
        quiet = fixture(MIN_TRACES, labels, notes_after=False)
        messages = candidate.reconcile(quiet, expected_taxonomy(quiet, definitions_for(quiet)))
        require(messages == [], f"Exactly {MIN_TRACES} annotations with notes on the first {HAND_NOTES} only must reconcile, got {messages!r}")
        return f"{MIN_TRACES - 1} annotations and a blank note at position {blank + 1} rejected; {MIN_TRACES} with notes on the first {HAND_NOTES} accepted."
    check("Coverage below the published bound is rejected", coverage)

    def recurring():
        absent = labels[-1]
        fresh_labels = labels[:-1] + ["new failure", RNG.choice(["another new one", "relay offline"])]
        batch = fixture(RNG.randint(30, 60), fresh_labels)
        batch = [record for record in batch if record["first_failure"] != absent]
        counts = Counter(record["first_failure"] for record in batch if record["first_failure"] != "pass")
        names = [category["name"] for category in expected["categories"]]
        wanted = {
            "total": len(batch), "passes": sum(1 for record in batch if record["first_failure"] == "pass"),
            "recurring": {name: counts[name] for name in names if counts[name]},
            "absent": [name for name in names if not counts[name]],
            "new": {label: count for label, count in counts.items() if label not in names},
        }
        got = candidate.recurrence(copy.deepcopy(expected), batch)
        require(isinstance(got, dict), "recurrence must return a dict")
        for key in ("total", "passes", "recurring", "absent", "new"):
            require(got.get(key) == wanted[key], f"{key}: got {got.get(key)!r}, expected {wanted[key]!r} (recomputed from the fresh batch, not copied from the taxonomy)")
        return f"Fresh batch of {len(batch)}: {len(wanted['recurring'])} categories recur, {wanted['absent']} absent, {len(wanted['new'])} new labels."
    check("Recurrence on a fresh batch recomputes the counts", recurring)

    reading = {}

    def workspace_annotations():
        records = read_workspace_annotations()
        reading["records"] = records
        require(len(records) >= MIN_TRACES, f"{len(records)} shipped traces annotated; the published bound is {MIN_TRACES}")
        unnoted = [record["trace_id"] for record in records[:HAND_NOTES] if not record["open_note"].strip()]
        require(not unnoted, f"The first {HAND_NOTES} annotations need an open note; empty on {unnoted[:5]}")
        return f"{len(records)} shipped traces annotated once each, open notes on the first {HAND_NOTES}, {sum(1 for r in records if r['first_failure'] == 'pass')} marked pass."
    check("The workspace annotations cover at least 100 shipped traces once each with notes on the first 30", workspace_annotations)

    def agreement():
        records = reading.get("records") or read_workspace_annotations()
        require(len(records) >= MIN_TRACES, f"Agreement is measured on the full set; {len(records)} annotated so far")
        disagreements = [record["trace_id"] for record in records if (record["first_failure"] == "pass") != (record["trace_id"] in PASS_IDS)]
        require(len(disagreements) <= TOLERANCE, f"{len(disagreements)} pass-or-failure decisions disagree with the recorded outcome (tolerance {TOLERANCE}): {disagreements[:10]}")
        return f"{len(records) - len(disagreements)} of {len(records)} pass-or-failure decisions agree with the recorded outcome; {len(disagreements)} disagree within the tolerance of {TOLERANCE}."
    check("The workspace labels agree with the recorded outcomes on pass versus failure", agreement)

    def workspace_taxonomy():
        records = reading.get("records") or read_workspace_annotations()
        path = os.path.join(WORKSPACE, "taxonomy.json")
        require(os.path.exists(path), "taxonomy.json is missing from the workspace")
        with open(path, encoding="utf-8") as file:
            taxonomy = json.load(file)
        require(isinstance(taxonomy, dict) and isinstance(taxonomy.get("categories"), list) and taxonomy["categories"], "taxonomy.json must be an object with a non-empty categories list")
        problems = audit(records, taxonomy)
        require(not problems, f"{len(problems)} inconsistencies: " + "; ".join(problems[:6]))
        reading["taxonomy"] = taxonomy
        return f"{len(taxonomy['categories'])} categories citing {sum(len(c['trace_ids']) for c in taxonomy['categories'])} traces reconcile with {len(records)} annotations and {taxonomy['passes']} passes."
    check("The workspace taxonomy reconciles with the workspace annotations", workspace_taxonomy)

    def examples():
        taxonomy = copy.deepcopy(expected)
        taxonomy["categories"][0]["definition"] = f"Looks like {taxonomy['categories'][1]['trace_ids'][0]} but in another category."
        expect(candidate.reconcile(consistent, taxonomy), {"example"}, set(), taxonomy["categories"][0]["name"])
        taxonomy = copy.deepcopy(expected)
        taxonomy["categories"][1]["definition"] = "A symptom described with no example at all."
        expect(candidate.reconcile(consistent, taxonomy), {"example"}, set(), taxonomy["categories"][1]["name"])
        shipped = reading.get("taxonomy")
        require(shipped is not None, "The workspace taxonomy must reconcile first")
        for category in shipped["categories"]:
            match = TRACE_ID.search(str(category.get("definition") or ""))
            require(match is not None and match.group(0) in category["trace_ids"], f"Category {category['name']!r} should cite one of its own traces as an example in its definition")
        return "Definitions that cite a foreign or no example were reported; every workspace definition cites one of its own traces."
    check("bonus: every definition cites an example from its own traces", examples, optional=True)



try:
    trial()
except Exception as error:
    CHECKS.append({"name": "Load taxonomy module", "passed": False, "detail": f"{type(error).__name__}: {error}"[:1500]})
finally:
    scratch = os.path.join(WORKSPACE, ".verify-annotations.jsonl")
    if os.path.exists(scratch):
        os.remove(scratch)
print(json.dumps({"checks": CHECKS}))
sys.exit(0 if CHECKS and all(item["passed"] for item in CHECKS if not item.get("optional")) else 1)
