"""Golden set as a ledger of plain dicts: every function returns a new manifest, nothing is mutated."""
import copy
import hashlib
import json

SPLITS = ("train", "dev", "test")
PROVENANCE_KINDS = ("real", "synthetic")
HASHED_FIELDS = ("id", "input", "expected", "category")


def normalize_text(text):
    kept = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in str(text))
    return " ".join(kept.split()).casefold()


def case_hash(case):
    canonical = json.dumps({key: case[key] for key in HASHED_FIELDS}, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def assign_split(case_id, seed, split_ratios):
    digest = hashlib.sha256(f"{seed}:{case_id}".encode("utf-8")).hexdigest()
    position = int(digest[:8], 16) / 2**32
    if position < split_ratios["train"]:
        return "train"
    if position < split_ratios["train"] + split_ratios["dev"]:
        return "dev"
    return "test"


def held_out_digest(hashes):
    return hashlib.sha256("\n".join(sorted(hashes)).encode("utf-8")).hexdigest()


def _case_errors(case, prefix="case"):
    errors = []
    if not isinstance(case, dict):
        return [f"{prefix}: not an object"]
    for key in ("id", "input", "expected", "category"):
        if not isinstance(case.get(key), str) or not case[key].strip():
            errors.append(f"{prefix}: {case.get('id', '?')} needs a non-empty string {key}")
    provenance = case.get("provenance")
    if not isinstance(provenance, dict) or provenance.get("kind") not in PROVENANCE_KINDS or not isinstance(provenance.get("source"), str) or not provenance["source"].strip():
        errors.append(f"provenance: {case.get('id', '?')} needs provenance {{kind: real|synthetic, source: note}}")
    return errors


def _check_ratios(split_ratios):
    if not isinstance(split_ratios, dict) or set(split_ratios) != set(SPLITS):
        raise ValueError("split_ratios needs exactly the keys train, dev and test")
    if any(float(split_ratios[name]) < 0 for name in SPLITS) or abs(sum(float(split_ratios[name]) for name in SPLITS) - 1) > 1e-9:
        raise ValueError("split_ratios must be non-negative and sum to 1")


def _stamp(case, seed, split_ratios):
    stamped = copy.deepcopy(case)
    stamped["split"] = assign_split(case["id"], seed, split_ratios)
    stamped["hash"] = case_hash(case)
    return stamped


def _summaries(cases):
    counts = {name: sum(1 for case in cases if case["split"] == name) for name in SPLITS}
    categories = {}
    for case in cases:
        categories[case["category"]] = categories.get(case["category"], 0) + 1
    return counts, categories


def build_manifest(cases, *, minimum_per_category, split_ratios, seed, version=1):
    if not isinstance(minimum_per_category, int) or minimum_per_category < 1:
        raise ValueError("minimum_per_category must be a positive integer")
    if not isinstance(version, int) or version < 1:
        raise ValueError("version must be a positive integer")
    _check_ratios(split_ratios)
    seen = set()
    for case in cases:
        errors = _case_errors(case)
        if errors:
            raise ValueError("; ".join(errors))
        if case["id"] in seen:
            raise ValueError(f"case: duplicate id {case['id']}")
        seen.add(case["id"])
    stamped = [_stamp(case, str(seed), split_ratios) for case in cases]
    counts, categories = _summaries(stamped)
    short = [name for name, count in categories.items() if count < minimum_per_category]
    if short:
        raise ValueError(f"category: {', '.join(sorted(short))} below the minimum of {minimum_per_category}")
    digest = held_out_digest([case["hash"] for case in stamped if case["split"] == "test"])
    return {
        "version": version, "seed": str(seed), "split_ratios": {name: float(split_ratios[name]) for name in SPLITS},
        "minimum_per_category": minimum_per_category, "cases": stamped, "counts": counts, "categories": categories,
        "held_out_digest": digest,
        "history": [{"version": version, "action": "build", "case_ids": [case["id"] for case in stamped], "held_out_digest": digest, "note": ""}],
    }


def check_leakage(manifest, few_shot_examples):
    protected = [(normalize_text(case["input"]), case) for case in manifest["cases"] if case["split"] in ("dev", "test")]
    leaks = []
    for index, example in enumerate(few_shot_examples):
        text = example["input"] if isinstance(example, dict) else example
        normalized = normalize_text(text)
        for candidate, case in protected:
            if normalized == candidate:
                leaks.append(f"few-shot example {index} matches {case['split']} case {case['id']}")
    return leaks


def add_case(manifest, case, *, note=""):
    errors = _case_errors(case)
    if errors:
        raise ValueError("; ".join(errors))
    if any(existing["id"] == case["id"] for existing in manifest["cases"]):
        raise ValueError(f"case: duplicate id {case['id']}")
    updated = copy.deepcopy(manifest)
    updated["cases"].append(_stamp(case, updated["seed"], updated["split_ratios"]))
    updated["counts"], updated["categories"] = _summaries(updated["cases"])
    updated["held_out_digest"] = held_out_digest([item["hash"] for item in updated["cases"] if item["split"] == "test"])
    updated["version"] = manifest["version"] + 1
    updated["history"].append({"version": updated["version"], "action": "add_case", "case_ids": [case["id"]], "held_out_digest": updated["held_out_digest"], "note": str(note)})
    return updated


def verify_manifest(manifest):
    errors = []
    try:
        _check_ratios(manifest.get("split_ratios"))
    except ValueError as error:
        errors.append(f"ratios: {error}")
        return errors
    cases = manifest.get("cases") or []
    seed, ratios = str(manifest.get("seed")), manifest["split_ratios"]
    seen = {}
    for case in cases:
        errors.extend(_case_errors(case))
        if not isinstance(case, dict) or not isinstance(case.get("id"), str):
            continue
        if case["id"] in seen:
            errors.append(f"case: duplicate id {case['id']}")
        seen[case["id"]] = case
    if errors:
        return errors
    counts, categories = _summaries(cases)
    minimum = manifest.get("minimum_per_category", 1)
    for name, count in sorted(categories.items()):
        if count < minimum:
            errors.append(f"category: {name} has {count} cases, minimum {minimum}")
    for case in cases:
        if case.get("hash") != case_hash(case):
            errors.append(f"hash: {case['id']} does not match its content")
        if case.get("split") != assign_split(case["id"], seed, ratios):
            errors.append(f"split: {case['id']} is in {case.get('split')!r}, the seeded rule says {assign_split(case['id'], seed, ratios)}")
    if manifest.get("counts") != counts or sum(counts.values()) != len(cases):
        errors.append(f"counts: recorded {manifest.get('counts')}, recounted {counts}")
    digest = held_out_digest([case_hash(case) for case in cases if case.get("split") == "test"])
    if manifest.get("held_out_digest") != digest:
        errors.append(f"held_out: digest {manifest.get('held_out_digest')} does not match the test split, recomputed {digest}")
    history = manifest.get("history") or []
    if not history or history[-1].get("version") != manifest.get("version") or history[-1].get("held_out_digest") != manifest.get("held_out_digest"):
        errors.append("history: the last entry must carry the manifest version and held-out digest")
    groups = {}
    for case in cases:
        groups.setdefault(normalize_text(case["input"]), []).append(case["id"])
    for ids in groups.values():
        if len(ids) > 1:
            errors.append(f"duplicate: cases {', '.join(ids)} share the same normalized input")
    return errors
