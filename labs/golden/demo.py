"""Terminal demo: python3 -B demo.py [build | leak | add | verify]

build   reads cases.json, builds the manifest with goldenset.build_manifest (minimum 5 per category,
        ratios 0.2/0.4/0.4, seed golden-v1) and writes goldenset.json with a split and category summary.
leak    checks the few-shot examples in fewshot.json against goldenset.json.
add     appends one synthetic case to goldenset.json as a new version and prints the history.
verify  recomputes hashes, splits, digest and minimums of goldenset.json and prints the findings.
"""
import json
import sys

import goldenset

MANIFEST = "goldenset.json"


def load(path):
    with open(path, encoding="utf-8") as file:
        return json.load(file)


def save(manifest):
    with open(MANIFEST, "w", encoding="utf-8") as file:
        json.dump(manifest, file, indent=2, ensure_ascii=False)
        file.write("\n")


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "build"
    if command == "build":
        manifest = goldenset.build_manifest(load("cases.json"), minimum_per_category=5, split_ratios={"train": 0.2, "dev": 0.4, "test": 0.4}, seed="golden-v1", version=1)
        save(manifest)
        print(f"version {manifest['version']}, counts {manifest['counts']}, categories {manifest['categories']}")
        print(f"held-out digest {manifest.get('held_out_digest') or '(none)'}")
    elif command == "leak":
        leaks = goldenset.check_leakage(load(MANIFEST), load("fewshot.json"))
        print("\n".join(leaks) if leaks else "no few-shot example overlaps a dev or test case")
    elif command == "add":
        manifest = load(MANIFEST)
        case = {"id": f"case-{len(manifest['cases']) + 1:03d}", "input": "Reserve 9 oxygen candles for relay 3 before the night shift. Mara",
                "expected": "record: 9 oxygen candles, pieces, urgency normal", "category": "happy_path", "provenance": {"kind": "synthetic", "source": "added from the demo"}}
        updated = goldenset.add_case(manifest, case)
        save(updated)
        print(json.dumps(updated["history"], indent=2))
    elif command == "verify":
        errors = goldenset.verify_manifest(load(MANIFEST))
        print("\n".join(errors) if errors else "manifest verifies clean")
    else:
        sys.exit(__doc__)
