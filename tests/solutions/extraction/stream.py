"""Ingestion step: a line state machine for Markdown, a streaming html.parser with a tag stack, dicts throughout."""
import json
import os
import re
from html.parser import HTMLParser

KINDS = ("heading", "step", "table", "paragraph")
HEADING = re.compile(r"^(#{1,6})[ \t]+(.*?)[ \t]*$")
STEP = re.compile(r"^[ \t]*(\d+)[.)][ \t]+(.*?)[ \t]*$")
TABLE_LINE = re.compile(r"^[ \t]*\|.*\|[ \t]*$")
DELIMITER = re.compile(r"^[ \t]*\|(?:[ \t]*:?-+:?[ \t]*\|)+[ \t]*$")
HEADING_TAGS = {f"h{level}": level for level in range(1, 7)}
MUST_CLOSE = {"table", "tbody", "tr", "td", "ol", "ul", "body", "html"} | set(HEADING_TAGS)
TRACKED = MUST_CLOSE | {"p", "li", "th"}


class ParseError(Exception):
    """Raised by a parser for a document it cannot read; ingest reports it instead of raising."""


class Chain:
    """Heading chain: a heading of level L replaces every open heading of level L or deeper."""

    def __init__(self):
        self.stack = []

    def push(self, level, text):
        while self.stack and self.stack[-1][0] >= level:
            self.stack.pop()
        self.stack.append((level, text))

    def path(self):
        return [text for _, text in self.stack]


def passage(kind, path, text, **place):
    return {"location": {"kind": kind, "path": list(path), **place}, "text": text}


def split_cells(line):
    """Cells of one pipe row as (text, start, end) with offsets relative to the line."""
    stripped = line.strip()
    base = line.index(stripped) + 1  # past the leading pipe
    cells, position = [], 0
    for piece in stripped[1:-1].split("|"):
        lead = len(piece) - len(piece.lstrip())
        text = piece.strip()
        cells.append((text, base + position + lead, base + position + lead + len(text)))
        position += len(piece) + 1
    return cells


def parse_markdown(source, path=None):
    lines = source.split("\n")
    starts, offset = [], 0
    for line in lines:
        starts.append(offset)
        offset += len(line) + 1
    chain, passages, tables = Chain(), [], 0
    index, count = 0, len(lines)
    while index < count:
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        match = HEADING.match(line)
        if match:
            level, text = len(match.group(1)), match.group(2)
            chain.push(level, text)
            passages.append(passage("heading", chain.path(), text, level=level, lines=[index + 1, index + 1], span=[starts[index] + match.start(2), starts[index] + match.end(2)]))
            index += 1
            continue
        match = STEP.match(line)
        if match:
            passages.append(passage("step", chain.path(), match.group(2), number=int(match.group(1)), lines=[index + 1, index + 1], span=[starts[index] + match.start(2), starts[index] + match.end(2)]))
            index += 1
            continue
        if TABLE_LINE.match(line):
            rows, end = [], index
            while end < count and TABLE_LINE.match(lines[end]):
                if not DELIMITER.match(lines[end]):
                    rows.append(end)
                end += 1
            for row, line_no in enumerate(rows):
                cells = split_cells(lines[line_no])
                for col, (text, start, stop) in enumerate(cells):
                    passages.append(passage("table", chain.path(), text, table={"index": tables, "row": row, "col": col}, lines=[line_no + 1, line_no + 1], span=[starts[line_no] + start, starts[line_no] + stop]))
                passages.append(passage("table", chain.path(), " | ".join(text for text, _, _ in cells), table={"index": tables, "row": row}, lines=[line_no + 1, line_no + 1]))
            tables += 1
            index = end
            continue
        end = index
        while end < count and lines[end].strip() and not (HEADING.match(lines[end]) or STEP.match(lines[end]) or TABLE_LINE.match(lines[end])):
            end += 1
        raw = "\n".join(lines[index:end])
        text = raw.strip()
        start = starts[index] + len(raw) - len(raw.lstrip())
        passages.append(passage("paragraph", chain.path(), text, lines=[index + 1, end], span=[start, start + len(text)]))
        index = end
    return passages


class Stream(HTMLParser):
    """Emits passages as the tags close; keeps a stack of open tracked tags to detect a truncated file."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.open = []  # (tag, line) of tracked tags still open
        self.collect = []  # text collectors: {"tag", "line", "parts", ...}
        self.lists = []  # ("ol", next number) or ("ul", None)
        self.table = None
        self.tables = 0
        self.chain = Chain()
        self.passages = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        line = self.getpos()[0]
        if tag in ("script", "style"):
            self.skip += 1
        if tag in TRACKED:
            self.open.append((tag, line))
        if tag == "table":
            self.table = {"index": self.tables, "row": -1, "cells": [], "line": line}
        elif tag == "tr" and self.table is not None:
            self.table["row"] += 1
            self.table["cells"] = []
            self.table["line"] = line
        elif tag in ("ol", "ul"):
            start = dict(attrs).get("start") if tag == "ol" else None
            self.lists.append([tag, int(start) if start and str(start).lstrip("-").isdigit() else 1])
        elif tag in HEADING_TAGS or tag in ("p", "li", "td", "th"):
            self.collect.append({"tag": tag, "line": line, "parts": []})

    def handle_data(self, data):
        if self.collect and not self.skip:
            self.collect[-1]["parts"].append(data)

    def handle_endtag(self, tag):
        line = self.getpos()[0]
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
        if tag in TRACKED:
            for position in range(len(self.open) - 1, -1, -1):
                if self.open[position][0] == tag:
                    del self.open[position:]
                    break
        if tag in ("ol", "ul") and self.lists:
            self.lists.pop()
        if tag == "table" and self.table is not None:
            self.tables += 1
            self.table = None
        elif tag == "tr" and self.table is not None and self.table["row"] >= 0:
            cells = self.table["cells"]
            self.passages.append(passage("table", self.chain.path(), " | ".join(cells), table={"index": self.table["index"], "row": self.table["row"]}, lines=[self.table["line"], line]))
        if self.collect and self.collect[-1]["tag"] == tag:
            item = self.collect.pop()
            text = " ".join("".join(item["parts"]).split())
            lines = [item["line"], line]
            if tag in HEADING_TAGS:
                self.chain.push(HEADING_TAGS[tag], text)
                self.passages.append(passage("heading", self.chain.path(), text, level=HEADING_TAGS[tag], lines=lines))
            elif tag in ("td", "th") and self.table is not None and self.table["row"] >= 0:
                col = len(self.table["cells"])
                self.table["cells"].append(text)
                self.passages.append(passage("table", self.chain.path(), text, table={"index": self.table["index"], "row": self.table["row"], "col": col}, lines=lines))
            elif tag == "li" and self.lists and self.lists[-1][0] == "ol":
                number = self.lists[-1][1]
                self.lists[-1][1] += 1
                self.passages.append(passage("step", self.chain.path(), text, number=number, lines=lines))
            else:
                self.passages.append(passage("paragraph", self.chain.path(), text, lines=lines))

    def finish(self):
        self.close()
        for tag, line in reversed(self.open):
            if tag in MUST_CLOSE:
                raise ParseError(f"unclosed <{tag}> opened at line {line}: the file looks truncated")
        return self.passages


def parse_html(source, path=None):
    if not source.strip():
        raise ParseError("empty document")
    stream = Stream()
    stream.feed(source)
    return stream.finish()


def parse_layout(source, path=None):
    try:
        data = json.loads(source)
    except ValueError as error:
        raise ParseError(f"not valid JSON: {error}") from None
    if not isinstance(data, dict) or data.get("format") != "layout/1" or not isinstance(data.get("pages"), list):
        raise ParseError("not a layout/1 document: expected {\"format\": \"layout/1\", \"pages\": [...]}")
    chain, passages, tables = Chain(), [], 0
    for page in data["pages"]:
        number = int(page["number"])
        for block in page.get("blocks", []):
            place = {"page": number}
            if block.get("bbox") is not None:
                place["bbox"] = list(block["bbox"])
            kind = block.get("type")
            if kind == "heading":
                level = int(block.get("level", 1))
                chain.push(level, block["text"])
                passages.append(passage("heading", chain.path(), block["text"], level=level, **place))
            elif kind == "list_item":
                passages.append(passage("step", chain.path(), block["text"], number=int(block["number"]), **place))
            elif kind == "table":
                rows = {}
                for cell in block.get("cells", []):
                    rows.setdefault(int(cell["row"]), {})[int(cell["col"])] = str(cell["text"])
                for row in sorted(rows):
                    for col in sorted(rows[row]):
                        passages.append(passage("table", chain.path(), rows[row][col], table={"index": tables, "row": row, "col": col}, **place))
                    passages.append(passage("table", chain.path(), " | ".join(rows[row][col] for col in sorted(rows[row])), table={"index": tables, "row": row}, **place))
                tables += 1
            elif kind == "paragraph":
                passages.append(passage("paragraph", chain.path(), block["text"], **place))
    return passages


PARSERS = {".md": parse_markdown, ".html": parse_html, ".htm": parse_html, ".json": parse_layout}


def register_parser(ext, fn):
    ext = ext.lower()
    PARSERS[ext if ext.startswith(".") else "." + ext] = fn


def ingest(path, *, doc_id, version):
    return ingest_batch([{"path": path, "doc_id": doc_id, "version": version}])


def ingest_batch(items):
    passages, documents, unparseable = [], [], []
    for item in items:
        path, doc_id, version = str(item["path"]), item["doc_id"], item["version"]
        counts = {kind: 0 for kind in KINDS}
        counts["total"] = 0
        entry = {"doc_id": doc_id, "version": version, "path": path, "status": "parsed", "passages": counts}
        try:
            ext = os.path.splitext(path)[1].lower()
            parser = PARSERS.get(ext)
            if parser is None:
                raise ParseError(f"no parser registered for {ext or 'a file without an extension'}")
            with open(path, "rb") as file:
                source = file.read().decode("utf-8")
            found = parser(source, path)
        except Exception as error:
            entry["status"] = "unparseable"
            entry["reason"] = str(error) if isinstance(error, ParseError) else f"{type(error).__name__}: {error}"
            unparseable.append({"doc_id": doc_id, "version": version, "path": path, "reason": entry["reason"]})
            documents.append(entry)
            continue
        for item_found in found:
            location = dict(item_found["location"])
            passages.append({"doc_id": doc_id, "version": version, "location": location, "text": item_found["text"]})
            if location.get("kind") in counts:
                counts[location["kind"]] += 1
            counts["total"] += 1
        documents.append(entry)
    return {"passages": passages, "report": {"documents": documents, "unparseable": unparseable, "total": len(passages)}}
