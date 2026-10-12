"""Golden set checks for the Golden mission; run outside the learner workspace.

Every verdict comes from code: Verify builds its own case fixtures with fresh ids, texts, seed and
minimum, recomputes hashes, splits and the held-out digest with the published rules, and compares.
There is no live part and no model.
"""
import copy
import hashlib
import importlib.util
import json
import os
import random
import sys

MISSION, WORKSPACE = sys.argv[1:3]
CHECKS = []
SPLITS = ("train", "dev", "test")


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def check(name, operation, optional=False):
    # An optional check is the hidden bonus of a mission: it can only add, it never fails the run.
    flag = {"optional": True} if optional else {}
    try:
        detail = operation()
        CHECKS.append({"name": name, "passed": True, "detail": detail or "Verified against fresh fixtures.", **flag})
    except Exception as error:
        CHECKS.append({"name": name, "passed": False, "detail": f"{type(error).__name__}: {error}"[:1500], **flag})


# Oracle: the published rules, recomputed here independently of the learner module.
def oracle_hash(case):
    payload = {key: case[key] for key in ("id", "input", "expected", "category")}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def oracle_split(case_id, seed, ratios):
    position = int(hashlib.sha256(f"{seed}:{case_id}".encode("utf-8")).hexdigest()[:8], 16) / 2**32
    if position < ratios["train"]:
        return "train"
    if position < ratios["train"] + ratios["dev"]:
        return "dev"
    return "test"


def oracle_digest(hashes):
    return hashlib.sha256("\n".join(sorted(hashes)).encode("utf-8")).hexdigest()


RNG = random.Random()
RUN = f"{RNG.randrange(16**6):06x}"
SEED = f"outpost-{RUN}"
MINIMUM = RNG.randint(4, 8)
PER_CATEGORY = MINIMUM + RNG.randint(3, 5)
RATIOS = RNG.choice([{"train": 0.2, "dev": 0.4, "test": 0.4}, {"train": 0.15, "dev": 0.45, "test": 0.4}, {"train": 0.1, "dev": 0.45, "test": 0.45}])
VERSION = RNG.randint(1, 5)
ITEMS = ["water filters", "fuses", "coolant", "relay boards", "gaskets", "battery packs", "spare antennas", "oxygen candles"]
REQUESTERS = ["Mara", "Teo", "Ilse", "Dmitri", "Noor", "Pavel"]
CATEGORIES = {
    "unknown_item": ("Reserve {n} {item} for relay {relay}, signed {who}.", "refuse: item not in catalog"),
    "wrong_unit": ("We need {n} boxes of {item} at outpost {relay}, {who}.", "record with the catalog unit, not boxes"),
    "over_reservation": ("Book {n} {item} for the night shift, urgent, {who}.", "refuse: above the operator's reservation limit"),
    "missing_source": ("How do I purge the {item} line on relay {relay}? {who}", "answer cites the runbook section"),
    "happy_path": ("Please set aside {n} {item} for relay {relay}, no rush. {who}", "record: {n} {item}, urgency low"),
}


def make_cases():
    # Fresh ids per run; the salt is re-drawn until every split holds at least two cases, so each check can pick one.
    for _ in range(100):
        salt = f"{RNG.randrange(16**3):03x}"
        cases, counter = [], 0
        for category, (template, expected) in CATEGORIES.items():
            for _ in range(PER_CATEGORY):
                counter += 1
                values = {"n": RNG.randint(2, 97), "item": RNG.choice(ITEMS), "relay": RNG.randint(1, 9), "who": RNG.choice(REQUESTERS)}
                text = template.format(**values) + f" (ticket {RUN}-{counter})"
                kind = RNG.choice(["real", "synthetic"])
                cases.append({"id": f"c{RUN}{salt}-{counter:03d}", "input": text, "expected": expected.format(**values), "category": category,
                              "provenance": {"kind": kind, "source": f"trace t-{RUN}-{counter}" if kind == "real" else f"written from category {category}"}})
        counts = {name: sum(1 for case in cases if oracle_split(case["id"], SEED, RATIOS) == name) for name in SPLITS}
        if min(counts.values()) >= 2:
            return cases
    raise AssertionError("could not draw a fixture with every split populated")


def trial():
    require(MISSION == "golden", "Unknown mission")
    sys.path.insert(0, WORKSPACE)
    spec = importlib.util.spec_from_file_location("candidate_golden", os.path.join(WORKSPACE, "goldenset.py"))
    if spec is None or spec.loader is None:
        raise ImportError("Cannot load goldenset.py")
    candidate = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = candidate
    spec.loader.exec_module(candidate)
    for name in ("build_manifest", "check_leakage", "add_case", "verify_manifest"):
        require(callable(getattr(candidate, name, None)), f"goldenset.py must define {name}(...)")

    cases = make_cases()

    def build(items=None, **overrides):
        options = {"minimum_per_category": MINIMUM, "split_ratios": RATIOS, "seed": SEED, "version": VERSION, **overrides}
        return candidate.build_manifest(copy.deepcopy(items if items is not None else cases), **options)

    def expect_value_error(operation, message):
        try:
            operation()
        except ValueError:
            return
        except Exception as error:
            raise AssertionError(f"{message}: expected ValueError, got {type(error).__name__}: {error}")
        raise AssertionError(message)

    def by_id(manifest):
        require(isinstance(manifest, dict) and isinstance(manifest.get("cases"), list), "build_manifest must return a dict with a cases list")
        return {case["id"]: case for case in manifest["cases"]}

    def hashed():
        manifest = build()
        require(manifest.get("version") == VERSION, f"version must be {VERSION}, got {manifest.get('version')!r}")
        require(str(manifest.get("seed")) == SEED, "seed must be recorded in the manifest")
        index = by_id(manifest)
        require(set(index) == {case["id"] for case in cases}, "Every input case must be in the manifest, once")
        for case in cases:
            stored = index[case["id"]]
            for key in ("input", "expected", "category", "provenance"):
                require(stored.get(key) == case[key], f"{case['id']}: {key} must be stored unchanged")
            require(stored.get("hash") == oracle_hash(case), f"{case['id']}: hash must be sha256 of the canonical JSON of id, input, expected and category")
        require(isinstance(manifest.get("categories"), dict) and manifest["categories"] == {name: PER_CATEGORY for name in CATEGORIES}, "categories must count the cases per category")
        errors = candidate.verify_manifest(copy.deepcopy(manifest))
        require(isinstance(errors, list) and errors == [], f"verify_manifest on a fresh manifest must return [], got {errors!r}")
        return f"{len(cases)} cases hashed; version {VERSION} verified clean."
    check("Every case is hashed and a fresh manifest verifies clean", hashed)

    def provenance():
        bare = copy.deepcopy(cases)
        del bare[7]["provenance"]
        expect_value_error(lambda: build(bare), "A case without provenance must raise ValueError")
        guessed = copy.deepcopy(cases)
        guessed[3]["provenance"] = {"kind": "guess", "source": "nobody knows"}
        expect_value_error(lambda: build(guessed), "A provenance kind other than real or synthetic must raise ValueError")
        empty = copy.deepcopy(cases)
        empty[5]["provenance"] = {"kind": "real", "source": ""}
        expect_value_error(lambda: build(empty), "A provenance without a source note must raise ValueError")
        manifest = build()
        stripped = copy.deepcopy(manifest)
        victim = stripped["cases"][11]
        del victim["provenance"]
        errors = candidate.verify_manifest(stripped)
        require(any(str(error).startswith("provenance:") and victim["id"] in str(error) for error in errors), f"verify_manifest must report 'provenance: …{victim['id']}…', got {errors!r}")
        expect_value_error(lambda: candidate.add_case(copy.deepcopy(manifest), {"id": f"c{RUN}-new", "input": "Order nine gaskets.", "expected": "record", "category": "happy_path"}), "add_case without provenance must raise ValueError")
        return "Missing, unknown and empty provenance refused at build, add and verify time."
    check("Provenance is required on every case", provenance)

    def minimum():
        short_category = RNG.choice(list(CATEGORIES))
        short = [case for case in cases if case["category"] != short_category] + [case for case in cases if case["category"] == short_category][: MINIMUM - 1]
        expect_value_error(lambda: build(short), f"{short_category} has {MINIMUM - 1} cases, below the minimum {MINIMUM}: build_manifest must raise ValueError")
        exact = [case for case in cases if case["category"] != short_category] + [case for case in cases if case["category"] == short_category][:MINIMUM]
        manifest = build(exact)
        require(len(manifest["cases"]) == len(exact), "A category exactly at the minimum builds")
        trimmed = copy.deepcopy(build())
        kept = [case for case in trimmed["cases"] if case["category"] == short_category][: MINIMUM - 1]
        trimmed["cases"] = [case for case in trimmed["cases"] if case["category"] != short_category] + kept
        errors = candidate.verify_manifest(trimmed)
        require(any(str(error).startswith("category:") and short_category in str(error) for error in errors), f"verify_manifest must report 'category: {short_category} …', got {errors!r}")
        return f"{short_category} with {MINIMUM - 1} cases refused, with {MINIMUM} accepted; the trimmed manifest reports the category."
    check("A category below the declared minimum is reported", minimum)

    def split():
        first = build()
        shuffled = copy.deepcopy(cases)
        RNG.shuffle(shuffled)
        second = build(shuffled)
        first_index, second_index = by_id(first), by_id(second)
        for case in cases:
            wanted = oracle_split(case["id"], SEED, RATIOS)
            require(first_index[case["id"]].get("split") == wanted, f"{case['id']} must land in {wanted} by the seeded hash rule, got {first_index[case['id']].get('split')!r}")
            require(second_index[case["id"]].get("split") == wanted, f"{case['id']} must land in {wanted} whatever the list order, got {second_index[case['id']].get('split')!r}")
        counts = first.get("counts")
        wanted_counts = {name: sum(1 for case in first["cases"] if case["split"] == name) for name in SPLITS}
        require(counts == wanted_counts and sum(counts.values()) == len(cases), f"counts must be {wanted_counts}, got {counts!r}")
        other = by_id(build(seed=SEED + "-other"))
        require(any(other[case["id"]]["split"] != first_index[case["id"]]["split"] for case in cases), "A different seed must move at least one case")
        require(first.get("held_out_digest") == second.get("held_out_digest"), "The held-out digest must not depend on the list order")
        return f"Splits {wanted_counts} identical for two orders and recomputed by the rule; seed {SEED}."
    check("Split is deterministic by seeded hash, not by list order", split)

    def digest():
        manifest = build()
        hashes = [oracle_hash(case) for case in cases if oracle_split(case["id"], SEED, RATIOS) == "test"]
        require(manifest.get("held_out_digest") == oracle_digest(hashes), "held_out_digest must be sha256 over the sorted test-split case hashes joined by newlines")
        edited = copy.deepcopy(manifest)
        victim = next(case for case in edited["cases"] if case["split"] == "test")
        victim["expected"] = victim["expected"] + " (quietly relaxed)"
        errors = [str(error) for error in candidate.verify_manifest(edited)]
        require(any(victim["id"] in error for error in errors), f"An edited held-out case must be reported by id, got {errors!r}")
        require(any(error.startswith("held_out:") for error in errors), f"An edited held-out case must change the recomputed digest: expected a 'held_out:' error, got {errors!r}")
        tampered = copy.deepcopy(manifest)
        train_case = next(case for case in tampered["cases"] if case["split"] == "train")
        train_case["input"] = train_case["input"] + " please"
        errors = [str(error) for error in candidate.verify_manifest(tampered)]
        require(any(train_case["id"] in error for error in errors), "An edited train case must still be reported by id (its hash changed)")
        require(not any(error.startswith("held_out:") for error in errors), "The held-out digest covers the test split only; a train edit must not change it")
        return f"Digest over {len(hashes)} held-out hashes recomputed; a test edit and a train edit told apart."
    check("Held-out digest recomputes and an edited held-out case is detected", digest)

    def leakage():
        manifest = build()
        index = by_id(manifest)
        pick = lambda split: next(case for case in manifest["cases"] if case["split"] == split)
        test_case, dev_case, train_case = pick("test"), pick("dev"), pick("train")
        disguised = "  " + test_case["input"].upper().replace(" ", "   ").rstrip(".") + " ."
        examples = [disguised, train_case["input"], {"input": dev_case["input"], "output": dev_case["expected"]}, "Unrelated text that is in no split at all."]
        leaks = candidate.check_leakage(copy.deepcopy(manifest), examples)
        require(isinstance(leaks, list) and all(isinstance(item, str) for item in leaks), "check_leakage must return a list of strings")
        require(any(test_case["id"] in leak and "test" in leak for leak in leaks), f"The disguised copy of test case {test_case['id']} must be reported with its split, got {leaks!r}")
        require(any(dev_case["id"] in leak and "dev" in leak for leak in leaks), f"The copy of dev case {dev_case['id']} must be reported with its split, got {leaks!r}")
        require(not any(train_case["id"] in leak for leak in leaks), f"A train example is the few-shot source and must not be reported, got {leaks!r}")
        require(len(leaks) == 2, f"Exactly two examples leak, got {len(leaks)}: {leaks!r}")
        require(candidate.check_leakage(copy.deepcopy(manifest), [index[train_case["id"]]["input"]]) == [], "Train-only examples give an empty list")
        return "A case-and-whitespace disguised test copy and a dict-form dev copy caught; a train example allowed."
    check("A few-shot example copied from the held-out split is caught, a train example is allowed", leakage)

    def history():
        manifest = build()
        snapshot = copy.deepcopy(manifest)

        def fresh_case(wanted_split):
            for attempt in range(1, 400):
                case_id = f"c{RUN}-add{attempt}"
                if oracle_split(case_id, SEED, RATIOS) == wanted_split:
                    return {"id": case_id, "input": f"Hold {RNG.randint(2, 40)} gaskets for the {wanted_split} relay, ticket {RUN}-{attempt}.", "expected": "record", "category": RNG.choice(list(CATEGORIES)),
                            "provenance": {"kind": "synthetic", "source": f"added in verify run {RUN}"}}
            raise AssertionError("no id found for the wanted split")

        into_test = fresh_case("test")
        second = candidate.add_case(manifest, into_test, note="verify run")
        require(manifest == snapshot, "add_case must not modify the manifest it was given")
        require(isinstance(second, dict) and second.get("version") == VERSION + 1, f"add_case must return a manifest with version {VERSION + 1}")
        require(second.get("history", [])[:-1] == manifest["history"], "Earlier history entries must stay byte-for-byte unchanged")
        require(len(second["history"]) == len(manifest["history"]) + 1, "add_case appends exactly one history entry")
        last = second["history"][-1]
        require(last.get("version") == VERSION + 1 and last.get("action") == "add_case" and last.get("case_ids") == [into_test["id"]], f"The new history entry must carry version, action add_case and the case id, got {last!r}")
        require(second["history"][0].get("held_out_digest") == manifest["held_out_digest"], "The earlier held-out digest stays recorded in history")
        index = by_id(second)
        for case in manifest["cases"]:
            require(index[case["id"]].get("split") == case["split"] and index[case["id"]].get("hash") == case["hash"], f"{case['id']} must keep its split and hash after add_case")
        require(index[into_test["id"]].get("split") == "test", "The new case gets its split by the same hash rule")
        wanted = oracle_digest([case["hash"] for case in second["cases"] if case["split"] == "test"])
        require(second.get("held_out_digest") == wanted and wanted != manifest["held_out_digest"], "A new test case changes the new version's held-out digest, which covers it")
        require(last.get("held_out_digest") == wanted, "The new history entry records the new held-out digest")
        require(candidate.verify_manifest(copy.deepcopy(second)) == [], "The new version verifies clean")
        into_train = fresh_case("train")
        third = candidate.add_case(second, into_train)
        require(third.get("version") == VERSION + 2 and third.get("held_out_digest") == wanted, "A new train case leaves the held-out digest unchanged while the version still increments")
        require(len(third["history"]) == 3 and third["history"][:2] == second["history"], "History keeps growing without rewriting")
        expect_value_error(lambda: candidate.add_case(third, into_test), "A duplicate id must raise ValueError")
        return f"Versions {VERSION}→{VERSION + 1}→{VERSION + 2}; a test addition changed the digest, a train addition did not."
    check("add_case appends a version without rewriting history", history)

    def duplicates():
        twin = copy.deepcopy(cases)
        original = twin[RNG.randrange(len(twin))]
        clone = copy.deepcopy(original)
        clone["id"] = f"c{RUN}-twin"
        clone["input"] = "   " + original["input"].upper().replace(",", " ,") + "  "
        clone["provenance"] = {"kind": "synthetic", "source": "paraphrase attempt"}
        twin.append(clone)
        manifest = build(twin)
        errors = [str(error) for error in candidate.verify_manifest(manifest)]
        require(any(error.startswith("duplicate:") and original["id"] in error and clone["id"] in error for error in errors), f"verify_manifest must report 'duplicate: … {original['id']} … {clone['id']}', got {errors!r}")
        return "Two cases with the same normalized input reported as a near-duplicate pair."
    check("bonus: near-duplicate cases inside the set are reported", duplicates, optional=True)


try:
    trial()
except Exception as error:
    CHECKS.append({"name": "Load golden set", "passed": False, "detail": f"{type(error).__name__}: {error}"[:1500]})
print(json.dumps({"checks": CHECKS}))
sys.exit(0 if CHECKS and all(item["passed"] for item in CHECKS if not item.get("optional")) else 1)
