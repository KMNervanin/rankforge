"""Ingestion step: a regex block scanner for Markdown, an HTML node tree walked recursively, dataclasses, a parser list."""
import json
import os
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from itertools import groupby

KINDS = ("heading", "step", "table", "paragraph")
BLOCK = re.compile(
    r"(?P<heading>^(?P<hashes>#{1,6})[ \t]+(?P<htext>.*?)[ \t]*$)"
    r"|(?P<step>^[ \t]*(?P<number>\d+)[.)][ \t]+(?P<stext>.*?)[ \t]*$)"
    r"|(?P<table>^[ \t]*\|.*\|[ \t]*$(?:\n[ \t]*\|.*\|[ \t]*$)*)"
    r"|(?P<paragraph>^[ \t]*\S.*$(?:\n(?![ \t]*$)(?!#{1,6}[ \t])(?![ \t]*\d+[.)][ \t])(?![ \t]*\|.*\|[ \t]*$).*$)*)",
    re.M,
)
DELIMITER = re.compile(r"^[ \t]*\|(?:[ \t]*:?-+:?[ \t]*\|)+[ \t]*$")
CELL = re.compile(r"(?<=\|)([^|]*)(?=\|)")
LEVELS = {f"h{level}": level for level in range(1, 7)}
MUST_CLOSE = {"table", "tbody", "tr", "td", "ol", "ul", "body", "html", *LEVELS}
VOID = {"br", "img", "hr", "meta", "link", "input", "wbr", "col", "source"}


class ParseError(Exception):
    """A document this step cannot read; ingest reports it instead of raising."""


@dataclass
class Passage:
    kind: str
    path: list
    text: str
    place: dict = field(default_factory=dict)

    def record(self):
        return {"location": {"kind": self.kind, "path": list(self.path), **self.place}, "text": self.text}


class Chain:
    def __init__(self):
        self.open = []

    def push(self, level, text):
        self.open = [(l, t) for l, t in self.open if l < level] + [(level, text)]

    def path(self):
        return [text for _, text in self.open]


def line_of(source, offset):
    return source.count("\n", 0, offset) + 1


def parse_markdown(source, path=None):
    chain, out, tables = Chain(), [], 0
    for match in BLOCK.finditer(source):
        kind = next(name for name in ("heading", "step", "table", "paragraph") if match.group(name) is not None)
        first = line_of(source, match.start())
        if kind == "heading":
            level, text = len(match.group("hashes")), match.group("htext")
            chain.push(level, text)
            out.append(Passage("heading", chain.path(), text, {"level": level, "lines": [first, first], "span": [match.start("htext"), match.end("htext")]}))
        elif kind == "step":
            out.append(Passage("step", chain.path(), match.group("stext"), {"number": int(match.group("number")), "lines": [first, first], "span": [match.start("stext"), match.end("stext")]}))
        elif kind == "table":
            row = 0
            for line_match in re.finditer(r"^.*$", match.group("table"), re.M):
                line = line_match.group(0)
                if DELIMITER.match(line):
                    continue
                base = match.start() + line_match.start()
                number = line_of(source, base)
                cells = []
                for col, cell in enumerate(CELL.finditer(line.strip())):
                    text = cell.group(1).strip()
                    start = base + line.index(line.strip()) + cell.start(1) + (len(cell.group(1)) - len(cell.group(1).lstrip()))
                    out.append(Passage("table", chain.path(), text, {"table": {"index": tables, "row": row, "col": col}, "lines": [number, number], "span": [start, start + len(text)]}))
                    cells.append(text)
                out.append(Passage("table", chain.path(), " | ".join(cells), {"table": {"index": tables, "row": row}, "lines": [number, number]}))
                row += 1
            tables += 1
        else:
            raw = match.group("paragraph")
            text = raw.strip()
            start = match.start() + raw.index(text)
            out.append(Passage("paragraph", chain.path(), text, {"lines": [first, line_of(source, match.end() - 1)], "span": [start, start + len(text)]}))
    return [item.record() for item in out]


@dataclass
class Node:
    tag: str
    attrs: dict
    line: int
    end_line: int = 0
    children: list = field(default_factory=list)  # Node or str
    closed: bool = False

    def text(self):
        return " ".join("".join(child if isinstance(child, str) else (" " + child.text() + " ") for child in self.children if not (isinstance(child, Node) and child.tag in ("script", "style"))).split())


class TreeBuilder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("#root", {}, 0)
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = Node(tag, dict(attrs), self.getpos()[0])
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_endtag(self, tag):
        for depth in range(len(self.stack) - 1, 0, -1):
            if self.stack[depth].tag == tag:
                for node in self.stack[depth:]:
                    node.closed, node.end_line = True, self.getpos()[0]
                del self.stack[depth:]
                return

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def parse_html(source, path=None):
    if not source.strip():
        raise ParseError("empty document")
    builder = TreeBuilder()
    builder.feed(source)
    builder.close()
    for node in builder.stack[1:]:
        if node.tag in MUST_CLOSE:
            raise ParseError(f"unclosed <{node.tag}> opened at line {node.line}: the file looks truncated")
    chain, out, state = Chain(), [], {"tables": 0}

    def walk(node, list_kind=None, counter=None, table=None):
        for child in node.children:
            if isinstance(child, str):
                continue
            place = {"lines": [child.line, child.end_line or child.line]}
            if child.tag in LEVELS:
                chain.push(LEVELS[child.tag], child.text())
                out.append(Passage("heading", chain.path(), child.text(), {"level": LEVELS[child.tag], **place}))
            elif child.tag == "p":
                out.append(Passage("paragraph", chain.path(), child.text(), place))
            elif child.tag in ("ol", "ul"):
                start = child.attrs.get("start")
                walk(child, child.tag, [int(start) if start and str(start).lstrip("-").isdigit() else 1], table)
            elif child.tag == "li":
                if list_kind == "ol":
                    out.append(Passage("step", chain.path(), child.text(), {"number": counter[0], **place}))
                    counter[0] += 1
                else:
                    out.append(Passage("paragraph", chain.path(), child.text(), place))
            elif child.tag == "table":
                index = state["tables"]
                state["tables"] += 1
                walk(child, list_kind, counter, {"index": index, "row": -1})
            elif child.tag == "tr" and table is not None:
                table["row"] += 1
                cells = [cell for cell in child.children if isinstance(cell, Node) and cell.tag in ("td", "th")]
                for col, cell in enumerate(cells):
                    out.append(Passage("table", chain.path(), cell.text(), {"table": {"index": table["index"], "row": table["row"], "col": col}, "lines": [cell.line, cell.end_line or cell.line]}))
                out.append(Passage("table", chain.path(), " | ".join(cell.text() for cell in cells), {"table": {"index": table["index"], "row": table["row"]}, **place}))
            elif child.tag in ("script", "style"):
                continue
            else:
                walk(child, list_kind, counter, table)

    walk(builder.root)
    return [item.record() for item in out]


def parse_layout(source, path=None):
    try:
        data = json.loads(source)
    except ValueError as error:
        raise ParseError(f"not valid JSON: {error}") from None
    if not isinstance(data, dict) or data.get("format") != "layout/1" or not isinstance(data.get("pages"), list):
        raise ParseError("not a layout/1 document: expected {\"format\": \"layout/1\", \"pages\": [...]}")
    chain, out, tables = Chain(), [], 0

    def blocks():
        for page in data["pages"]:
            for block in page.get("blocks", []):
                yield int(page["number"]), block

    for page, block in blocks():
        place = {"page": page, **({"bbox": list(block["bbox"])} if block.get("bbox") is not None else {})}
        kind = block.get("type")
        if kind == "heading":
            chain.push(int(block.get("level", 1)), block["text"])
            out.append(Passage("heading", chain.path(), block["text"], {"level": int(block.get("level", 1)), **place}))
        elif kind == "list_item":
            out.append(Passage("step", chain.path(), block["text"], {"number": int(block["number"]), **place}))
        elif kind == "table":
            ordered = sorted(block.get("cells", []), key=lambda cell: (int(cell["row"]), int(cell["col"])))
            for row, cells in groupby(ordered, key=lambda cell: int(cell["row"])):
                cells = list(cells)
                for cell in cells:
                    out.append(Passage("table", chain.path(), str(cell["text"]), {"table": {"index": tables, "row": row, "col": int(cell["col"])}, **place}))
                out.append(Passage("table", chain.path(), " | ".join(str(cell["text"]) for cell in cells), {"table": {"index": tables, "row": row}, **place}))
            tables += 1
        elif kind == "paragraph":
            out.append(Passage("paragraph", chain.path(), block["text"], place))
    return [item.record() for item in out]


PARSERS = [(".md", parse_markdown), (".html", parse_html), (".htm", parse_html), (".json", parse_layout)]


def register_parser(ext, fn):
    ext = ext.lower()
    PARSERS.insert(0, (ext if ext.startswith(".") else "." + ext, fn))


def parser_for(path):
    ext = os.path.splitext(path)[1].lower()
    for known, fn in PARSERS:
        if known == ext:
            return fn
    raise ParseError(f"no parser registered for {ext or 'a file without an extension'}")


@dataclass
class Document:
    doc_id: str
    version: str
    path: str
    status: str = "parsed"
    reason: str = ""
    counts: dict = field(default_factory=lambda: {**{kind: 0 for kind in KINDS}, "total": 0})

    def entry(self):
        entry = {"doc_id": self.doc_id, "version": self.version, "path": self.path, "status": self.status, "passages": dict(self.counts)}
        if self.status == "unparseable":
            entry["reason"] = self.reason
        return entry


def ingest_batch(items):
    passages, documents = [], []
    for item in items:
        document = Document(item["doc_id"], item["version"], str(item["path"]))
        documents.append(document)
        try:
            with open(document.path, "rb") as file:
                source = file.read().decode("utf-8")
            found = parser_for(document.path)(source, document.path)
        except Exception as error:
            document.status = "unparseable"
            document.reason = str(error) if isinstance(error, ParseError) else f"{type(error).__name__}: {error}"
            continue
        for record in found:
            passages.append({"doc_id": document.doc_id, "version": document.version, **record})
            kind = record["location"].get("kind")
            if kind in KINDS:
                document.counts[kind] += 1
            document.counts["total"] += 1
    unparseable = [{"doc_id": d.doc_id, "version": d.version, "path": d.path, "reason": d.reason} for d in documents if d.status == "unparseable"]
    return {"passages": passages, "report": {"documents": [d.entry() for d in documents], "unparseable": unparseable, "total": len(passages)}}


def ingest(path, *, doc_id, version):
    return ingest_batch([{"path": path, "doc_id": doc_id, "version": version}])
