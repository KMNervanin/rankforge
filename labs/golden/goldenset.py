"""Golden set manifest for the operator assistant.

Starter: it builds a manifest and reports splits, but the split follows the list order, nothing is
hashed, the leakage check compares raw strings and add_case rebuilds the whole set. See LEARN.md for
the complete contract that Verify checks.
"""
import json

SPLITS = ("train", "dev", "test")


def build_manifest(cases, *, minimum_per_category, split_ratios, seed, version=1):
    cases = [dict(case) for case in cases]
    total = len(cases)
    train_end = int(total * split_ratios["train"])
    dev_end = train_end + int(total * split_ratios["dev"])
    for position, case in enumerate(cases):
        case["split"] = "train" if position < train_end else "dev" if position < dev_end else "test"
    categories = {}
    for case in cases:
        categories[case["category"]] = categories.get(case["category"], 0) + 1
    counts = {name: sum(1 for case in cases if case["split"] == name) for name in SPLITS}
    return {
        "version": version, "seed": seed, "split_ratios": dict(split_ratios), "minimum_per_category": minimum_per_category,
        "cases": cases, "counts": counts, "categories": categories, "held_out_digest": "",
        "history": [{"version": version, "action": "build", "case_ids": [case["id"] for case in cases], "held_out_digest": "", "note": ""}],
    }


def check_leakage(manifest, few_shot_examples):
    protected = {case["input"]: case for case in manifest["cases"] if case["split"] != "train"}
    leaks = []
    for index, example in enumerate(few_shot_examples):
        if example in protected:
            case = protected[example]
            leaks.append(f"few-shot example {index} matches {case['split']} case {case['id']}")
    return leaks


def add_case(manifest, case, *, note=""):
    cases = [{key: value for key, value in item.items() if key not in ("split", "hash")} for item in manifest["cases"]] + [dict(case)]
    return build_manifest(cases, minimum_per_category=manifest["minimum_per_category"], split_ratios=manifest["split_ratios"], seed=manifest["seed"], version=manifest["version"] + 1)


def verify_manifest(manifest):
    errors = []
    counts = {name: sum(1 for case in manifest["cases"] if case["split"] == name) for name in SPLITS}
    if sum(counts.values()) != len(manifest["cases"]):
        errors.append(f"counts: {counts} do not add up to {len(manifest['cases'])} cases")
    return errors


if __name__ == "__main__":
    with open("cases.json", encoding="utf-8") as file:
        print(json.dumps(build_manifest(json.load(file), minimum_per_category=5, split_ratios={"train": 0.2, "dev": 0.4, "test": 0.4}, seed="outpost-2026")["counts"]))
