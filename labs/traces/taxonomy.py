"""Annotations and failure taxonomy for the operator assistant's traces.

Starter: it loads whatever is in annotations.jsonl and reports the numbers written in taxonomy.json.
See LEARN.md for the complete contract that Verify checks; this file passes none of it on purpose.
"""
import json
import os

TAXONOMY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "taxonomy.json")


def load_annotations(path):
    annotations = []
    with open(path, encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue
            record = json.loads(line)
            annotations.append({"trace_id": str(record.get("trace_id", "")), "open_note": str(record.get("open_note", "")), "first_failure": str(record.get("first_failure", "pass"))})
    return annotations


def build_taxonomy(annotations, definitions=None):
    with open(TAXONOMY_PATH, encoding="utf-8") as file:
        published = json.load(file)
    categories = [dict(category) for category in published["categories"]]
    failures = sum(category["count"] for category in categories)
    return {"total": len(annotations), "passes": len(annotations) - failures, "categories": categories}


def reconcile(annotations, taxonomy):
    problems = []
    failures = sum(category["count"] for category in taxonomy["categories"])
    if failures + taxonomy["passes"] != taxonomy["total"]:
        problems.append(f"total: {failures} failures and {taxonomy['passes']} passes do not add up to {taxonomy['total']}")
    return problems


def recurrence(taxonomy, new_annotations):
    recurring = {category["name"]: category["count"] for category in taxonomy["categories"]}
    return {"total": len(new_annotations), "passes": sum(1 for record in new_annotations if record["first_failure"] == "pass"), "recurring": recurring, "absent": [], "new": {}}
