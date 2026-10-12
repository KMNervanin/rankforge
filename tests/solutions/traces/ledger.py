"""Annotations and failure taxonomy: a dictionary-and-Counter ledger."""
import json
import re
from collections import Counter

MIN_TRACES = 100
HAND_NOTES = 30
TRACE_ID = re.compile(r"[a-z]{2}-[0-9]{4}")


def load_annotations(path):
    annotations, seen = [], set()
    with open(path, encoding="utf-8") as file:
        for number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            record = json.loads(line)
            if not isinstance(record, dict):
                raise ValueError(f"line {number}: not a JSON object")
            trace_id = record.get("trace_id")
            if not isinstance(trace_id, str) or not trace_id:
                raise ValueError(f"line {number}: trace_id missing")
            label = record.get("first_failure")
            if not isinstance(label, str) or not label.strip():
                raise ValueError(f"{trace_id}: first_failure must be one non-empty label or pass, got {label!r}")
            if trace_id in seen:
                raise ValueError(f"{trace_id}: annotated twice")
            seen.add(trace_id)
            annotations.append({**record, "trace_id": trace_id, "open_note": str(record.get("open_note") or ""), "first_failure": label})
    return annotations


def build_taxonomy(annotations, definitions=None):
    definitions = definitions or {}
    groups = {}
    for record in annotations:
        if record["first_failure"] != "pass":
            groups.setdefault(record["first_failure"], []).append(record["trace_id"])
    categories = [{"name": name, "definition": definitions.get(name, ""), "trace_ids": ids, "count": len(ids)} for name, ids in groups.items()]
    categories.sort(key=lambda category: (-category["count"], category["name"]))
    return {"total": len(annotations), "passes": sum(1 for record in annotations if record["first_failure"] == "pass"), "categories": categories}


def reconcile(annotations, taxonomy):
    problems = []
    if len(annotations) < MIN_TRACES:
        problems.append(f"coverage: {len(annotations)} annotations, the bound is {MIN_TRACES}")
    for record in annotations[:HAND_NOTES]:
        if not record["open_note"].strip():
            problems.append(f"coverage: {record['trace_id']} is among the first {HAND_NOTES} and has no open note")
    labels = {record["trace_id"]: record["first_failure"] for record in annotations}
    cited = {}
    for category in taxonomy.get("categories", []):
        name, ids = category.get("name"), list(category.get("trace_ids") or [])
        if not ids:
            problems.append(f"empty: category {name!r} cites no traces")
        if category.get("count") != len(set(ids)):
            problems.append(f"count: category {name!r} says {category.get('count')!r}, cites {len(set(ids))} distinct traces")
        for trace_id in ids:
            if trace_id not in labels:
                problems.append(f"unknown: category {name!r} cites {trace_id}, which has no annotation")
            elif labels[trace_id] != name:
                problems.append(f"label: {trace_id} is cited by {name!r} but annotated {labels[trace_id]!r}")
            else:
                cited[trace_id] = name
        example = TRACE_ID.search(str(category.get("definition") or ""))
        if example is None or example.group(0) not in ids:
            problems.append(f"example: category {name!r} should cite one of its own traces in its definition")
    for record in annotations:
        if record["first_failure"] != "pass" and cited.get(record["trace_id"]) != record["first_failure"]:
            problems.append(f"missing: {record['trace_id']} is annotated {record['first_failure']!r} but no such category cites it")
    passes = sum(1 for record in annotations if record["first_failure"] == "pass")
    failures = sum(int(category.get("count") or 0) for category in taxonomy.get("categories", []))
    if taxonomy.get("total") != len(annotations) or taxonomy.get("passes") != passes or failures + passes != taxonomy.get("total"):
        problems.append(f"total: {failures} failures + {taxonomy.get('passes')!r} passes vs total {taxonomy.get('total')!r}; {len(annotations)} annotations with {passes} passes")
    return problems


def recurrence(taxonomy, new_annotations):
    counts = Counter(record["first_failure"] for record in new_annotations if record["first_failure"] != "pass")
    names = [category["name"] for category in taxonomy.get("categories", [])]
    return {
        "total": len(new_annotations),
        "passes": sum(1 for record in new_annotations if record["first_failure"] == "pass"),
        "recurring": {name: counts[name] for name in names if counts[name]},
        "absent": [name for name in names if not counts[name]],
        "new": {label: count for label, count in counts.items() if label not in names},
    }
