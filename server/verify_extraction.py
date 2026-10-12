"""Ingestion checks for the Extraction mission; run outside the learner workspace.

Nothing here calls a model or a PDF library. Every fixture is written by Verify into a fresh directory
with fresh ids, versions and values, its expected cells, steps and heading chains are listed by hand
from the same lines, and the layout JSON stands in for what a PDF parser (Docling, PyMuPDF find_tables,
pdfplumber) would emit: it is a labeled test input, not a PDF.
"""
import importlib.util
import json
import os
import random
import re
import shutil
import sys
import tempfile

MISSION, WORKSPACE = sys.argv[1:3]
CHECKS = []
KINDS = ("heading", "step", "table", "paragraph")
UNCLOSED = re.compile(r"\b(table|tbody|tr|td|body|ol|ul|h[1-6])\b|<html>")


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def check(name, operation, optional=False):
    # An optional check is the hidden bonus of a mission: it can only add, it never fails the run.
    flag = {"optional": True} if optional else {}
    try:
        detail = operation()
        CHECKS.append({"name": name, "passed": True, "detail": detail or "Passages and the extraction report verified.", **flag})
    except Exception as error:
        CHECKS.append({"name": name, "passed": False, "detail": f"{type(error).__name__}: {error}"[:1500], **flag})


class Fresh:
    """One set of fresh ids and values; every fixture and every expectation is derived from it by hand."""

    def __init__(self):
        rng = random.Random()
        self.outpost = f"Outpost-{rng.choice('KLMNPRSTVZ')}{rng.randint(10, 99)}"
        self.outpost2 = f"Outpost-{rng.choice('ABCDEFGH')}{rng.randint(10, 99)}"
        self.code = f"R-{rng.randint(1000, 9999)}"
        self.bay, self.bay2 = f"bay-{rng.randint(11, 49)}", f"bay-{rng.randint(50, 99)}"
        self.fuse = f"F{rng.randint(100, 999)}"
        self.res = f"RES-{rng.randint(10000, 99999)}"
        self.inc = f"INC-{rng.randint(1000, 9999)}"
        self.seconds = rng.randint(20, 90)
        self.minutes = rng.randint(5, 40)
        self.lease = rng.randint(30, 120)
        self.time = f"0{rng.randint(1, 5)}:{rng.randint(10, 59)}"
        self.quarter = f"Q{rng.randint(1, 4)}-{rng.randint(2024, 2027)}"
        self.week = rng.randint(1, 13)
        self.date = f"2026-{rng.randint(1, 9):02d}-{rng.randint(10, 28)}"
        self.ids = {name: f"{name}-{rng.randint(100000, 999999)}" for name in ("runbook", "incident", "report", "broken", "memo", "note", "bad")}
        others = " ".join([self.code, self.res, self.inc, self.time, self.quarter, self.date, self.bay, self.bay2, self.fuse])
        self.q = rng.sample(range(1000, 9999), 12)  # numbers unique to table cells: the flatten check looks for them in every passage
        while any(str(value) in others for value in self.q):
            self.q = rng.sample(range(1000, 9999), 12)
        self.versions = {name: f"v{rng.randint(1, 9)}.{rng.randint(0, 20)}" for name in self.ids}
        self.rng = rng


def runbook_markdown(f):
    lines = [
        f"# Runbook {f.code}: relay restart",  # 1
        "",
        f"Written for the night shift of {f.outpost}.",  # 3
        "",
        "## Preparation",  # 5
        "",
        "### Before you touch the relay",  # 7
        "",
        f"Confirm that reservation {f.res} is closed",  # 9
        "and that the quartermaster has signed the ledger.",  # 10
        "",
        "## Steps",  # 12
        "",
        f"1. Switch the relay to standby and wait {f.seconds} seconds.",  # 14
        f"2. Pull the filter cartridge from {f.bay}.",  # 15
        "3. Count the spare cartridges in the cold store.",  # 16
        "",
        "Safety: never pull a cartridge while the relay is live; the bay stays locked until step 3 is logged.",  # 18
        "",
        "4. Restart the relay from the console.",  # 20
        f"5. Log the restart in the ledger as {f.code}.",  # 21
        "",
        "## Spares",  # 23
        "",
        "| Item | Bay | Count |",  # 25
        "| --- | --- | --- |",  # 26
        f"| Filter cartridge | {f.bay} | {f.q[0]} |",  # 27
        f"| Fuse {f.fuse} | {f.bay2} | {f.q[1]} |",  # 28
        "",
    ]
    expected = {
        "headings": [(1, f"Runbook {f.code}: relay restart", 1), (2, "Preparation", 5), (3, "Before you touch the relay", 7), (2, "Steps", 12), (2, "Spares", 23)],
        "deep": {"text": f"Confirm that reservation {f.res} is closed\nand that the quartermaster has signed the ledger.", "path": [f"Runbook {f.code}: relay restart", "Preparation", "Before you touch the relay"], "lines": [9, 10]},
        "steps": [(1, f"Switch the relay to standby and wait {f.seconds} seconds."), (2, f"Pull the filter cartridge from {f.bay}."), (3, "Count the spare cartridges in the cold store."), (4, "Restart the relay from the console."), (5, f"Log the restart in the ledger as {f.code}.")],
        "safety": {"text": lines[17], "path": [f"Runbook {f.code}: relay restart", "Steps"], "lines": [18, 18]},
        "cells": {(0, 0, 0): "Item", (0, 0, 1): "Bay", (0, 0, 2): "Count", (0, 1, 0): "Filter cartridge", (0, 1, 1): f.bay, (0, 1, 2): str(f.q[0]), (0, 2, 0): f"Fuse {f.fuse}", (0, 2, 1): f.bay2, (0, 2, 2): str(f.q[1])},
        "cell_lines": {(0, 1, 2): 27, (0, 2, 0): 28},
        "unique_rows": {1: [str(f.q[0])], 2: [str(f.q[1])]},
        "counts": {"heading": 5, "step": 5, "table": 12, "paragraph": 3, "total": 25},
    }
    return "\n".join(lines), expected


def incident_html(f):
    lines = [
        "<!DOCTYPE html>",  # 1
        "<html>",  # 2
        f"<head><title>Incident {f.inc}</title><style>p {{ margin: 0 }}</style></head>",  # 3
        "<body>",  # 4
        f"<h1>Incident {f.inc}: relay brownout</h1>",  # 5
        f"<p>Reported by the night shift of {f.outpost} at {f.time}.</p>",  # 6
        "<h2>Timeline</h2>",  # 7
        "<ol>",  # 8
        f"  <li>Relay power dropped at {f.time}.</li>",  # 9
        f"  <li>Stock queries returned stale counts for {f.minutes} minutes.</li>",  # 10
        f"  <li>The cache lease was shortened to {f.lease} seconds.</li>",  # 11
        "</ol>",  # 12
        "<h2>Impact</h2>",  # 13
        "<h3>Reservations</h3>",  # 14
        f"<p>Reservation <b>{f.res}</b> was confirmed against stale stock &amp;",  # 15
        "  rolled back by the quartermaster.</p>",  # 16
        "<table>",  # 17
        "  <thead><tr><th>Outpost</th><th>Stale reads</th><th>Rolled back</th></tr></thead>",  # 18
        "  <tbody>",  # 19
        f"    <tr><td>{f.outpost}</td><td>{f.q[2]}</td><td>{f.q[3]}</td></tr>",  # 20
        f"    <tr><td>{f.outpost2}</td>",  # 21
        f"        <td>{f.q[4]}</td><td>{f.q[5]}</td></tr>",  # 22
        "  </tbody>",  # 23
        "</table>",  # 24
        "<h2>Follow-up</h2>",  # 25
        "<ul><li>Add a cache age to the dashboard.</li></ul>",  # 26
        "</body>",  # 27
        "</html>",  # 28
    ]
    expected = {
        "headings": [(1, f"Incident {f.inc}: relay brownout"), (2, "Timeline"), (2, "Impact"), (3, "Reservations"), (2, "Follow-up")],
        "deep": {"text": f"Reservation {f.res} was confirmed against stale stock & rolled back by the quartermaster.", "path": [f"Incident {f.inc}: relay brownout", "Impact", "Reservations"], "line": 16},
        "steps": [(1, f"Relay power dropped at {f.time}."), (2, f"Stock queries returned stale counts for {f.minutes} minutes."), (3, f"The cache lease was shortened to {f.lease} seconds.")],
        "cells": {(0, 0, 0): "Outpost", (0, 0, 1): "Stale reads", (0, 0, 2): "Rolled back", (0, 1, 0): f.outpost, (0, 1, 1): str(f.q[2]), (0, 1, 2): str(f.q[3]), (0, 2, 0): f.outpost2, (0, 2, 1): str(f.q[4]), (0, 2, 2): str(f.q[5])},
        "cell_lines": {(0, 1, 1): 20, (0, 2, 1): 22},
        "unique_rows": {1: [str(f.q[2]), str(f.q[3])], 2: [str(f.q[4]), str(f.q[5])]},
        "followup": "Add a cache age to the dashboard.",
        "counts": {"heading": 5, "step": 3, "table": 12, "paragraph": 3, "total": 23},
    }
    truncated = "\n".join(lines[:21]) + "\n"  # cut inside the second body row: tr, tbody, table, body and html stay open
    return "\n".join(lines) + "\n", expected, truncated


def report_layout(f):
    cells = [{"row": row, "col": col, "text": text} for (row, col), text in {
        (0, 0): "Item", (0, 1): "Week", (0, 2): "Issued", (0, 3): "Returned",
        (1, 0): "Filter cartridge", (1, 1): str(f.week), (1, 2): str(f.q[6]), (1, 3): str(f.q[7]),
        (2, 0): f"Fuse {f.fuse}", (2, 1): str(f.week + 1), (2, 2): str(f.q[8]), (2, 3): str(f.q[9]),
    }.items()]
    f.rng.shuffle(cells)  # a parser's cell list is not in reading order; the indices are the truth
    table_bbox = [72.0, 210.5, 540.0, 318.25]
    data = {"format": "layout/1", "source": "report.pdf", "pages": [
        {"number": 1, "blocks": [
            {"type": "heading", "level": 1, "text": f"Supply report {f.quarter}", "bbox": [72.0, 60.0, 540.0, 92.0]},
            {"type": "paragraph", "text": f"Prepared for {f.outpost} by the quartermaster.", "bbox": [72.0, 100.0, 540.0, 130.0]},
            {"type": "heading", "level": 2, "text": "Consumption", "bbox": [72.0, 160.0, 540.0, 190.0]},
            {"type": "table", "bbox": table_bbox, "cells": cells},
        ]},
        {"number": 2, "blocks": [
            {"type": "heading", "level": 3, "text": "Notes", "bbox": [72.0, 60.0, 540.0, 90.0]},
            {"type": "list_item", "number": 1, "text": f"Fuse {f.fuse} ran short in week {f.week}.", "bbox": [90.0, 100.0, 540.0, 118.0]},
            {"type": "list_item", "number": 2, "text": f"{f.bay2} was closed for inspection.", "bbox": [90.0, 120.0, 540.0, 138.0]},
            {"type": "paragraph", "text": f"Counts come from the ledger as of {f.date}.", "bbox": [72.0, 150.0, 540.0, 180.0]},
        ]},
    ]}
    expected = {
        "cells": {(0, cell["row"], cell["col"]): cell["text"] for cell in cells},
        "table_bbox": table_bbox,
        "deep": {"text": f"Counts come from the ledger as of {f.date}.", "path": [f"Supply report {f.quarter}", "Consumption", "Notes"], "page": 2},
        "steps": [(1, f"Fuse {f.fuse} ran short in week {f.week}."), (2, f"{f.bay2} was closed for inspection.")],
        "unique_rows": {1: [str(f.q[6]), str(f.q[7])], 2: [str(f.q[8]), str(f.q[9])]},
        "counts": {"heading": 3, "step": 2, "table": 15, "paragraph": 2, "total": 22},
    }
    return json.dumps(data, indent=1), expected


def trial():
    require(MISSION == "extraction", "Unknown mission")
    sys.path.insert(0, WORKSPACE)
    spec = importlib.util.spec_from_file_location("candidate_extraction", os.path.join(WORKSPACE, "ingest.py"))
    if spec is None or spec.loader is None:
        raise ImportError("Cannot load ingest.py")
    candidate = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = candidate
    spec.loader.exec_module(candidate)
    require(callable(getattr(candidate, "ingest", None)), "ingest.py must define ingest(path, *, doc_id, version)")
    require(callable(getattr(candidate, "ingest_batch", None)), "ingest.py must define ingest_batch(items)")
    require(isinstance(getattr(candidate, "ParseError", None), type) and issubclass(candidate.ParseError, Exception), "ingest.py must define the ParseError exception class")

    f = Fresh()
    folder = tempfile.mkdtemp(prefix="rankforge-extraction-")
    try:
        checks_in(candidate, f, folder)
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def checks_in(candidate, f, folder):
    markdown, md = runbook_markdown(f)
    html, ht, truncated = incident_html(f)
    layout, lj = report_layout(f)
    files = {"runbook": ("runbook.md", markdown), "incident": ("incident.html", html), "report": ("report.layout.json", layout), "broken": ("broken.html", truncated), "memo": ("memo.docx", "PK\x03\x04 not a document this step can read\n")}
    paths = {}
    for name, (filename, content) in files.items():
        paths[name] = os.path.join(folder, filename)
        with open(paths[name], "w", encoding="utf-8") as file:
            file.write(content)

    def run(name):
        result = candidate.ingest(paths[name], doc_id=f.ids[name], version=f.versions[name])
        require(isinstance(result, dict) and isinstance(result.get("passages"), list) and isinstance(result.get("report"), dict), "ingest must return {passages: [...], report: {...}}")
        for item in result["passages"]:
            require(isinstance(item, dict) and isinstance(item.get("location"), dict) and isinstance(item.get("text"), str), "every passage is a dict with a location dict and a text string")
        return result["passages"], result["report"]

    def by_kind(passages, kind):
        return [item for item in passages if item["location"].get("kind") == kind]

    def table_map(passages):
        cells, rows = {}, {}
        for item in by_kind(passages, "table"):
            table = item["location"].get("table")
            require(isinstance(table, dict) and type(table.get("index")) is int and type(table.get("row")) is int, "a table passage carries location.table with integer index and row")
            if "col" in table:
                require(type(table["col"]) is int, "a cell's col is an integer")
                cells[(table["index"], table["row"], table["col"])] = item
            else:
                rows[(table["index"], table["row"])] = item
        return cells, rows

    def expect_cells(passages, expected, label):
        cells, rows = table_map(passages)
        for key, text in expected["cells"].items():
            require(key in cells, f"{label}: cell table {key[0]} row {key[1]} col {key[2]} ({text!r}) is missing; got cells {sorted(cells)}")
            require(cells[key]["text"] == text, f"{label}: cell {key} must be {text!r}, got {cells[key]['text']!r}")
        extra = set(cells) - set(expected["cells"])
        require(not extra, f"{label}: unexpected cells {sorted(extra)}")
        wanted_rows = {}
        for (index, row, col), text in expected["cells"].items():
            wanted_rows.setdefault((index, row), {})[col] = text
        for key, columns in wanted_rows.items():
            line = " | ".join(columns[col] for col in sorted(columns))
            require(key in rows, f"{label}: row {key[1]} of table {key[0]} has no row passage (text joined with ' | ', location.table without col)")
            require(rows[key]["text"] == line, f"{label}: row passage for row {key[1]} must be {line!r}, got {rows[key]['text']!r}")
        for item in passages:
            hit = [row for row, values in expected["unique_rows"].items() if any(value in item["text"] for value in values)]
            require(len(hit) <= 1, f"{label}: a passage holds values from rows {hit} of the table at once, so the table was flattened into one stream: {item['text'][:120]!r}")
        return cells, rows

    def expect_steps(passages, expected, label):
        steps = by_kind(passages, "step")
        got = [(item["location"].get("number"), item["text"]) for item in steps]
        require(got == expected, f"{label}: steps must appear in document order with their written numbers {[n for n, _ in expected]}; got {got}")

    def heading_chain(passages, expected, label):
        headings = by_kind(passages, "heading")
        got = [(item["location"].get("level"), item["text"]) for item in headings]
        require(got == [(level, text) for level, text, *_ in expected], f"{label}: headings with levels must be {[(l, t) for l, t, *_ in expected]}, got {got}")
        for item in headings:
            require(item["location"].get("path") and item["location"]["path"][-1] == item["text"], f"{label}: a heading's path ends with the heading itself; {item['text']!r} has path {item['location'].get('path')}")

    def find_text(passages, text, label):
        hits = [item for item in passages if item["text"] == text]
        require(hits, f"{label}: no passage with the text {text!r}; texts are {[item['text'][:40] for item in passages][:30]}")
        return hits[0]

    def markdown_structure():
        passages, _ = run("runbook")
        heading_chain(passages, md["headings"], "runbook.md")
        for level, text, line in md["headings"]:
            item = find_text(passages, text, "runbook.md")
            require(item["location"].get("lines") == [line, line], f"runbook.md: heading {text!r} is on line {line}; location.lines must be [{line}, {line}], got {item['location'].get('lines')}")
        deep = find_text(passages, md["deep"]["text"], "runbook.md (two-line paragraph under the level-3 heading)")
        require(deep["location"].get("kind") == "paragraph" and deep["location"].get("path") == md["deep"]["path"], f"runbook.md: the paragraph under the level-3 heading must have path {md['deep']['path']}, got kind {deep['location'].get('kind')!r} path {deep['location'].get('path')}")
        require(deep["location"].get("lines") == md["deep"]["lines"], f"runbook.md: that paragraph spans lines {md['deep']['lines']}, got {deep['location'].get('lines')}")
        expect_steps(passages, md["steps"], "runbook.md")
        safety = find_text(passages, md["safety"]["text"], "runbook.md (safety note between step 3 and step 4)")
        require(safety["location"].get("kind") == "paragraph" and safety["location"].get("path") == md["safety"]["path"] and safety["location"].get("lines") == md["safety"]["lines"], f"runbook.md: the safety note is a paragraph under {md['safety']['path']} on line 18, got {safety['location']}")
        order = [item["text"] for item in passages]
        require(order.index(md["steps"][2][1]) < order.index(md["safety"]["text"]) < order.index(md["steps"][3][1]), "runbook.md: passages keep document order; the safety note sits between step 3 and step 4")
        return f"Five headings with levels, a chain of three for the deep paragraph, steps 1-5 in order around the safety note on line 18 ({f.code})."
    check("Markdown runbook: headings keep their level and chain, steps keep their numbers and order", markdown_structure)

    def markdown_table():
        passages, _ = run("runbook")
        cells, rows = expect_cells(passages, md, "runbook.md")
        for key, line in md["cell_lines"].items():
            require(cells[key]["location"].get("lines") == [line, line], f"runbook.md: cell {key} is on line {line}, got lines {cells[key]['location'].get('lines')}")
        require(all(item["location"].get("path") == [f"Runbook {f.code}: relay restart", "Spares"] for item in cells.values()), "runbook.md: every cell carries the heading chain of the table: [runbook title, 'Spares']")
        return f"Nine cells with row and col, three ' | ' rows, nothing flattened; counts {f.q[0]} and {f.q[1]} stayed in their rows."
    check("Markdown pipe table: every cell carries row and col, every row is one ' | ' line, nothing is flattened", markdown_table)

    def html_structure():
        passages, _ = run("incident")
        heading_chain(passages, ht["headings"], "incident.html")
        deep = find_text(passages, ht["deep"]["text"], "incident.html (paragraph with <b> and &amp; under the level-3 heading)")
        require(deep["location"].get("kind") == "paragraph" and deep["location"].get("path") == ht["deep"]["path"], f"incident.html: the paragraph under <h3> must have path {ht['deep']['path']}, got {deep['location']}")
        lines = deep["location"].get("lines")
        require(isinstance(lines, list) and len(lines) == 2 and lines[0] <= 15 <= ht["deep"]["line"] <= lines[1], f"incident.html: that paragraph opens on line 15 and closes on line 16; location.lines must cover both, got {lines}")
        expect_steps(passages, ht["steps"], "incident.html")
        cells, rows = expect_cells(passages, ht, "incident.html")
        for key, line in ht["cell_lines"].items():
            lines = cells[key]["location"].get("lines")
            require(isinstance(lines, list) and len(lines) == 2 and lines[0] <= line <= lines[1], f"incident.html: cell {key} sits on line {line}; location.lines must cover it, got {lines}")
        require(all(item["location"].get("path") == [ht["headings"][0][1], "Impact", "Reservations"] for item in cells.values()), "incident.html: the table sits under Impact > Reservations; every cell carries that chain")
        follow = find_text(passages, ht["followup"], "incident.html (<ul> item)")
        require(follow["location"].get("kind") == "paragraph" and follow["location"].get("path") == [ht["headings"][0][1], "Follow-up"], f"incident.html: an unordered item is a paragraph under its heading, got {follow['location']}")
        require(not any("margin" in item["text"] for item in passages), "incident.html: <style> content is not a passage")
        return f"Nested h1 > h2 > h3 chain, three numbered steps, nine cells with line ranges, {f.res} decoded from <b> and &amp;."
    check("HTML incident report: nested headings, table cells with indices and line ranges survive html.parser", html_structure)

    def layout_structure():
        passages, _ = run("report")
        cells, rows = expect_cells(passages, lj, "report.layout.json")
        for key, item in cells.items():
            require(item["location"].get("page") == 1, f"report.layout.json: cell {key} is on page 1, got page {item['location'].get('page')}")
            require(item["location"].get("bbox") == lj["table_bbox"], f"report.layout.json: a cell copies the table block's bbox {lj['table_bbox']}, got {item['location'].get('bbox')}")
        deep = find_text(passages, lj["deep"]["text"], "report.layout.json (paragraph on page 2)")
        require(deep["location"].get("page") == 2 and deep["location"].get("path") == lj["deep"]["path"], f"report.layout.json: the page-2 paragraph keeps page 2 and the chain across pages {lj['deep']['path']}, got {deep['location']}")
        expect_steps(passages, lj["steps"], "report.layout.json")
        return f"Twelve cells kept the parser's shuffled row/col indices, three rows joined, the chain {lj['deep']['path']} crossed to page 2."
    check("Layout JSON standing in for PDF: cells keep the parser's row and col indices, pages and the chain survive", layout_structure)

    def provenance():
        total = 0
        for name in ("runbook", "incident", "report"):
            passages, _ = run(name)
            require(passages, f"{name}: no passages")
            for item in passages:
                require(item.get("doc_id") == f.ids[name], f"{name}: every passage carries doc_id {f.ids[name]!r}, got {item.get('doc_id')!r}")
                require(item.get("version") == f.versions[name], f"{name}: every passage carries version {f.versions[name]!r}, got {item.get('version')!r}")
                location = item["location"]
                require(location.get("kind") in KINDS, f"{name}: location.kind must be one of {KINDS}, got {location.get('kind')!r}")
                require(isinstance(location.get("path"), list) and all(isinstance(part, str) for part in location["path"]), f"{name}: location.path is a list of heading texts, got {location.get('path')!r}")
                lines, page = location.get("lines"), location.get("page")
                require((isinstance(lines, list) and len(lines) == 2 and all(type(value) is int for value in lines) and 1 <= lines[0] <= lines[1]) or (type(page) is int and page >= 1), f"{name}: a location has lines [first, last] (1-based) or a page number, got {location}")
                require(name == "report" or lines is not None, f"{name}: Markdown and HTML passages carry lines")
                require(name != "report" or page is not None, f"{name}: layout passages carry page")
                if location["kind"] == "heading":
                    require(type(location.get("level")) is int and location["level"] >= 1, f"{name}: a heading carries its integer level, got {location}")
                if location["kind"] == "step":
                    require(type(location.get("number")) is int, f"{name}: a step carries its integer number, got {location}")
                if location["kind"] == "table":
                    require(isinstance(location.get("table"), dict), f"{name}: a table passage carries location.table")
                total += 1
        return f"{total} passages across three formats, each with doc_id, version, kind, path and lines or page."
    check("Provenance: every passage carries doc_id, version and a location with kind, path and lines or page", provenance)

    def unparseable():
        items = [{"path": paths[name], "doc_id": f.ids[name], "version": f.versions[name]} for name in ("runbook", "broken", "memo", "report")]
        result = candidate.ingest_batch(items)
        require(isinstance(result, dict) and isinstance(result.get("passages"), list) and isinstance(result.get("report"), dict), "ingest_batch must return {passages, report}")
        report = result["report"]
        documents = report.get("documents")
        require(isinstance(documents, list) and [entry.get("doc_id") for entry in documents] == [f.ids[name] for name in ("runbook", "broken", "memo", "report")], "report.documents lists every input document by doc_id in input order, parsed or not")
        require([entry.get("status") for entry in documents] == ["parsed", "unparseable", "unparseable", "parsed"], f"statuses must be parsed, unparseable, unparseable, parsed; got {[entry.get('status') for entry in documents]}")
        bad = report.get("unparseable")
        require(isinstance(bad, list) and len(bad) == 2, f"report.unparseable lists the two unreadable files, got {bad!r}")
        for entry, name in zip(bad, ("broken", "memo")):
            require(entry.get("doc_id") == f.ids[name] and entry.get("version") == f.versions[name] and entry.get("path") == paths[name], f"unparseable entry for {name} carries doc_id, version and path, got {entry}")
            require(isinstance(entry.get("reason"), str) and entry["reason"].strip(), f"unparseable entry for {name} needs a reason")
        def without_path(entry, name):
            return entry["reason"].replace(paths[name], "").replace(os.path.basename(paths[name]), "")

        require(UNCLOSED.search(without_path(bad[0], "broken")), f"the truncated HTML ends inside a table row: the reason names the unclosed element, got {bad[0]['reason']!r}")
        require(".docx" in without_path(bad[1], "memo"), f"the .docx reason names the extension nobody registered, got {bad[1]['reason']!r}")
        for entry in documents[1:3]:
            require(entry.get("reason") == [b for b in bad if b["doc_id"] == entry["doc_id"]][0]["reason"], "the document entry repeats the reason")
            require(entry.get("passages", {}).get("total") == 0, "an unparseable document counts zero passages")
        ids = [item.get("doc_id") for item in result["passages"]]
        require(set(ids) == {f.ids["runbook"], f.ids["report"]}, f"the parsable documents of the batch still produce passages: expected doc ids of the runbook and the report only, got {sorted(set(map(str, ids)))}")
        require(ids.count(f.ids["runbook"]) == md["counts"]["total"] and ids.count(f.ids["report"]) == lj["counts"]["total"], f"the runbook yields {md['counts']['total']} passages and the report {lj['counts']['total']} inside the batch, got {ids.count(f.ids['runbook'])} and {ids.count(f.ids['report'])}")
        require(ids.index(f.ids["report"]) > ids.index(f.ids["runbook"]), "passages keep batch order")
        single = candidate.ingest(paths["broken"], doc_id=f.ids["broken"], version=f.versions["broken"])
        require(single["passages"] == [] and len(single["report"].get("unparseable", [])) == 1 and single["report"]["unparseable"][0].get("reason"), "ingest on a single truncated file returns no passages and one unparseable entry with a reason instead of raising")
        return f"Truncated HTML and memo.docx reported with reasons ({bad[0]['reason'][:60]!r}; {bad[1]['reason'][:60]!r}); the runbook and the report in the same batch produced {len(ids)} passages."
    check("Unparseable files are reported with a reason and the rest of the batch still produces passages", unparseable)

    def report_counts():
        items = [{"path": paths[name], "doc_id": f.ids[name], "version": f.versions[name]} for name in ("runbook", "incident", "report")]
        result = candidate.ingest_batch(items)
        documents = result["report"].get("documents")
        require(isinstance(documents, list) and len(documents) == 3, "report.documents has one entry per input")
        for entry, name, expected in zip(documents, ("runbook", "incident", "report"), (md, ht, lj)):
            counts = entry.get("passages")
            require(isinstance(counts, dict), f"{name}: report.documents[].passages is a dict of counts by kind")
            got = {key: counts.get(key) for key in (*KINDS, "total")}
            require(got == expected["counts"], f"{name}: counts by kind must be {expected['counts']} (a table counts its cells and its rows), got {got}")
            require(entry.get("version") == f.versions[name] and entry.get("path") == paths[name], f"{name}: the document entry carries version and path")
        require(result["report"].get("total") == len(result["passages"]) == md["counts"]["total"] + ht["counts"]["total"] + lj["counts"]["total"], f"report.total equals the number of passages, {md['counts']['total'] + ht['counts']['total'] + lj['counts']['total']}")
        require(result["report"].get("unparseable") == [], "a clean batch reports an empty unparseable list")
        return f"Counts by kind matched for three documents: {md['counts']['total']} + {ht['counts']['total']} + {lj['counts']['total']} passages."
    check("Report: passages counted by kind per document and the totals add up", report_counts)

    def transfer():
        require(callable(getattr(candidate, "register_parser", None)), "ingest.py must define register_parser(ext, fn): the published extension point for a new format")
        note_lines = [f"NOTE Shift handover {f.code}", "", f"Relay restarted twice; see {f.inc}.", f"Spare count in {f.bay} is {f.q[10]}.", ""]
        with open(os.path.join(folder, "note.txt"), "w", encoding="utf-8") as file:
            file.write("\n".join(note_lines))
        with open(os.path.join(folder, "bad.txt"), "w", encoding="utf-8") as file:
            file.write("no header on this one\n")
        note, bad = os.path.join(folder, "note.txt"), os.path.join(folder, "bad.txt")
        before = candidate.ingest(note, doc_id=f.ids["note"], version=f.versions["note"])
        require(before["passages"] == [] and len(before["report"].get("unparseable", [])) == 1 and ".txt" in before["report"]["unparseable"][0].get("reason", "").replace(note, "").replace("note.txt", ""), "before registration a .txt file is unparseable with a reason naming .txt")

        def parse_note(source, path):
            lines = source.split("\n")
            if not lines[0].startswith("NOTE "):
                raise candidate.ParseError("missing NOTE header")
            title = lines[0][5:].strip()
            found = [{"location": {"kind": "heading", "level": 1, "path": [title], "lines": [1, 1]}, "text": title}]
            for number, line in enumerate(lines[1:], start=2):
                if line.strip():
                    found.append({"location": {"kind": "paragraph", "path": [title], "lines": [number, number]}, "text": line.strip()})
            return found

        candidate.register_parser(".txt", parse_note)
        items = [{"path": note, "doc_id": f.ids["note"], "version": f.versions["note"]}, {"path": bad, "doc_id": f.ids["bad"], "version": f.versions["bad"]}, {"path": paths["runbook"], "doc_id": f.ids["runbook"], "version": f.versions["runbook"]}]
        result = candidate.ingest_batch(items)
        mine = [item for item in result["passages"] if item.get("doc_id") == f.ids["note"]]
        require([item["text"] for item in mine] == [f"Shift handover {f.code}", note_lines[2], note_lines[3]], f"the registered parser's passages come through ingest_batch in order, got {[item['text'] for item in mine]}")
        require(all(item.get("version") == f.versions["note"] and item["location"].get("path") == [f"Shift handover {f.code}"] for item in mine), "ingest attaches doc_id and version and keeps the parser's location")
        documents = result["report"]["documents"]
        require(documents[0].get("status") == "parsed" and documents[0]["passages"].get("heading") == 1 and documents[0]["passages"].get("paragraph") == 2 and documents[0]["passages"].get("total") == 3, f"the note counts 1 heading and 2 paragraphs, got {documents[0].get('passages')}")
        require(documents[1].get("status") == "unparseable" and "missing NOTE header" in documents[1].get("reason", ""), f"a ParseError from the registered parser is reported with its message, got {documents[1]}")
        require(documents[2].get("status") == "parsed" and documents[2]["passages"].get("total") == md["counts"]["total"], "the Markdown parser is untouched by the registration")
        return f"A .txt convention joined through register_parser: 3 passages with provenance, a bad note reported, the runbook still at {md['counts']['total']} passages."
    check("Transfer: a new format joins through register_parser without touching the other parsers", transfer)

    def spans():
        passages, _ = run("runbook")
        checked = 0
        for item in passages:
            location = item["location"]
            if location["kind"] == "table" and "col" not in location.get("table", {}):
                continue  # a row passage is synthesized text and may omit span
            span = location.get("span")
            require(isinstance(span, list) and len(span) == 2 and all(type(value) is int for value in span), f"runbook.md: location.span = [start, end] character offsets into the file, got {span!r} for {item['text'][:40]!r}")
            require(markdown[span[0]:span[1]] == item["text"], f"runbook.md: source[{span[0]}:{span[1]}] is {markdown[span[0]:span[1]][:60]!r}, the passage text is {item['text'][:60]!r}")
            checked += 1
        require(checked >= 20, f"expected spans on headings, steps, paragraphs and cells; checked {checked}")
        return f"{checked} spans sliced the original runbook to their passage text."
    check("bonus: location.span slices the original Markdown file to the passage text", spans, optional=True)


# Fixture sanity, outside every check: a verifier bug must crash loudly, never read as a learner failure.
_f = Fresh()
_md_text, _md = runbook_markdown(_f)
if _md_text.split("\n")[17] != _md["safety"]["text"] or len(_md["cells"]) != 9 or _md["counts"]["table"] != 12:
    raise RuntimeError("verifier bug: the runbook fixture and its expectations disagree")
_html_text, _ht, _truncated = incident_html(_f)
if "</table>" in _truncated or "<table>" not in _truncated or _html_text.split("\n")[15] != "  rolled back by the quartermaster.</p>":
    raise RuntimeError("verifier bug: the incident fixture and its expectations disagree")
_layout_text, _lj = report_layout(_f)
if len(_lj["cells"]) != 12 or _lj["counts"]["table"] != 15:
    raise RuntimeError("verifier bug: the layout fixture and its expectations disagree")

try:
    trial()
except Exception as error:
    CHECKS.append({"name": "Load ingestion step", "passed": False, "detail": f"{type(error).__name__}: {error}"[:1500]})
print(json.dumps({"checks": CHECKS}))
sys.exit(0 if CHECKS and all(item["passed"] for item in CHECKS if not item.get("optional")) else 1)
