"""Ingestion step for the archive.

Starter: it turns every document into plain text the way an extract_text() call would, and that
is the deliberate defect. See LEARN.md for the contract Verify checks.
"""
import json
import os
import re
from html.parser import HTMLParser


class ParseError(Exception):
    """A document this step cannot read."""


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def extract_text(path):
    ext = os.path.splitext(path)[1].lower()
    with open(path, encoding="utf-8") as file:
        source = file.read()
    if ext == ".md":
        source = re.sub(r"^#+\s*|^\s*\d+[.)]\s+", "", source, flags=re.M)
        return re.sub(r"^\|[\s:|-]+\|\s*$", "", source, flags=re.M).replace("|", " ")
    if ext in (".html", ".htm"):
        parser = _Text()
        parser.feed(source)
        parser.close()
        return " ".join("".join(parser.parts).split())
    if ext == ".json":
        data = json.loads(source)
        blocks = []
        for page in data["pages"]:
            for block in page["blocks"]:
                blocks.append(block.get("text") or " ".join(cell["text"] for cell in block.get("cells", [])))
        return "\n\n".join(blocks)
    raise ParseError(f"cannot read {ext}")


def ingest(path, *, doc_id, version):
    text = extract_text(path)
    passages = [{"doc_id": doc_id, "location": {"kind": "paragraph"}, "text": chunk.strip()} for chunk in re.split(r"\n\s*\n", text) if chunk.strip()]
    return {"passages": passages, "report": {"documents": [{"doc_id": doc_id, "path": path, "passages": len(passages)}], "total": len(passages)}}


def ingest_batch(items):
    passages, documents = [], []
    for item in items:
        result = ingest(item["path"], doc_id=item["doc_id"], version=item["version"])
        passages += result["passages"]
        documents += result["report"]["documents"]
    return {"passages": passages, "report": {"documents": documents, "total": len(passages)}}
