"""Annotations and failure taxonomy: an in-memory SQLite table reconciled with joins."""
import json
import re
import sqlite3

MIN_TRACES = 100
HAND_NOTES = 30
TRACE_ID = re.compile(r"[a-z]{2}-[0-9]{4}")


def _parse(number, line):
    record = json.loads(line)
    if not isinstance(record, dict):
        raise ValueError(f"line {number}: not a JSON object")
    trace_id = record.get("trace_id")
    if not isinstance(trace_id, str) or not trace_id:
        raise ValueError(f"line {number}: trace_id missing")
    label = record.get("first_failure")
    if not isinstance(label, str) or not label.strip():
        raise ValueError(f"{trace_id}: first_failure must be one label or pass, got {label!r}")
    note = record.get("open_note")
    return {**record, "trace_id": trace_id, "open_note": note if isinstance(note, str) else "", "first_failure": label}


def load_annotations(path):
    with open(path, encoding="utf-8") as file:
        records = [_parse(number, line) for number, line in enumerate(file, start=1) if line.strip()]
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE a (trace_id TEXT PRIMARY KEY)")
    for record in records:
        try:
            db.execute("INSERT INTO a VALUES (?)", (record["trace_id"],))
        except sqlite3.IntegrityError:
            raise ValueError(f"{record['trace_id']}: annotated twice") from None
    return records


def _table(annotations):
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE a (position INTEGER, trace_id TEXT, label TEXT, note TEXT)")
    db.executemany("INSERT INTO a VALUES (?, ?, ?, ?)", [(index, record["trace_id"], record["first_failure"], record["open_note"]) for index, record in enumerate(annotations)])
    return db


def build_taxonomy(annotations, definitions=None):
    definitions = definitions or {}
    db = _table(annotations)
    rows = db.execute("SELECT label, COUNT(*) AS n FROM a WHERE label != 'pass' GROUP BY label ORDER BY n DESC, label ASC").fetchall()
    categories = []
    for label, count in rows:
        ids = [row[0] for row in db.execute("SELECT trace_id FROM a WHERE label = ? ORDER BY position", (label,))]
        categories.append({"name": label, "definition": definitions.get(label, ""), "trace_ids": ids, "count": count})
    passes = db.execute("SELECT COUNT(*) FROM a WHERE label = 'pass'").fetchone()[0]
    return {"total": len(annotations), "passes": passes, "categories": categories}


def reconcile(annotations, taxonomy):
    db = _table(annotations)
    db.execute("CREATE TABLE c (category TEXT, trace_id TEXT)")
    problems = []
    if len(annotations) < MIN_TRACES:
        problems.append(f"coverage: only {len(annotations)} annotations, {MIN_TRACES} required")
    for trace_id, in db.execute("SELECT trace_id FROM a WHERE position < ? AND TRIM(note) = '' ORDER BY position", (HAND_NOTES,)):
        problems.append(f"coverage: {trace_id} lacks an open note inside the first {HAND_NOTES}")
    categories = taxonomy.get("categories") or []
    for category in categories:
        name, ids = category.get("name"), list(category.get("trace_ids") or [])
        if not ids:
            problems.append(f"empty: category {name!r} has no trace references")
        db.executemany("INSERT INTO c VALUES (?, ?)", [(name, trace_id) for trace_id in dict.fromkeys(ids)])
        distinct = len(dict.fromkeys(ids))
        if category.get("count") != distinct:
            problems.append(f"count: category {name!r} claims {category.get('count')!r} but cites {distinct}")
        match = TRACE_ID.search(str(category.get("definition") or ""))
        if match is None or match.group(0) not in ids:
            problems.append(f"example: category {name!r} must name one of its own trace ids in its definition")
    for name, trace_id, label in db.execute("SELECT c.category, c.trace_id, a.label FROM c LEFT JOIN a ON a.trace_id = c.trace_id"):
        if label is None:
            problems.append(f"unknown: category {name!r} cites {trace_id}, which is not annotated")
        elif label != name:
            problems.append(f"label: {trace_id} cited by {name!r}, annotated {label!r}")
    for trace_id, label in db.execute("SELECT a.trace_id, a.label FROM a LEFT JOIN c ON c.trace_id = a.trace_id AND c.category = a.label WHERE a.label != 'pass' AND c.trace_id IS NULL ORDER BY a.position"):
        problems.append(f"missing: {trace_id} annotated {label!r} is cited by no category of that name")
    passes = db.execute("SELECT COUNT(*) FROM a WHERE label = 'pass'").fetchone()[0]
    failures = sum(int(category.get("count") or 0) for category in categories)
    if taxonomy.get("total") != len(annotations) or taxonomy.get("passes") != passes or failures + passes != taxonomy.get("total"):
        problems.append(f"total: taxonomy says {taxonomy.get('total')!r} total and {taxonomy.get('passes')!r} passes with {failures} failures; annotations hold {len(annotations)} with {passes} passes")
    return problems


def recurrence(taxonomy, new_annotations):
    db = _table(new_annotations)
    counts = dict(db.execute("SELECT label, COUNT(*) FROM a WHERE label != 'pass' GROUP BY label").fetchall())
    names = [category["name"] for category in taxonomy.get("categories") or []]
    return {
        "total": len(new_annotations),
        "passes": db.execute("SELECT COUNT(*) FROM a WHERE label = 'pass'").fetchone()[0],
        "recurring": {name: counts[name] for name in names if counts.get(name)},
        "absent": [name for name in names if not counts.get(name)],
        "new": {label: count for label, count in counts.items() if label not in names},
    }
