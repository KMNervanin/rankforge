"""Answer with sources: http.client, dataclasses, footnote rendering ([1], [2] with a source list under
the answer), the retry is one fresh message that restates the problem."""
import json
import os
import re
from dataclasses import dataclass
from http import client as http_client
from urllib.parse import urlsplit

PHRASE = "the archive does not answer this"
BRACKET = re.compile(r"\s*\[[^\]]*\]")
QUOTE_MARKS = "\"'“”«»"


@dataclass(frozen=True)
class Passage:
    id: str
    doc: str
    version: int
    text: str

    @property
    def flat(self):
        return flatten(self.text)

    @classmethod
    def of(cls, raw):
        return cls(str(raw["id"]), str(raw.get("doc") or ""), raw.get("version") or 0, str(raw["text"]))


@dataclass(frozen=True)
class Citation:
    passage_id: str
    quote: str
    start: int
    end: int

    def as_dict(self):
        return {"passage_id": self.passage_id, "quote": self.quote, "start": self.start, "end": self.end}


class Rejected(Exception):
    pass


def flatten(text):
    return " ".join(str(text).split())


def sentences(body):
    flat = flatten(BRACKET.sub("", body))
    pieces = []
    current = []
    for word in flat.split(" "):
        current.append(word)
        if word and word[-1] in ".!?":
            pieces.append(" ".join(current))
            current = []
    if current:
        pieces.append(" ".join(current))
    return [piece.strip() for piece in pieces if piece.strip()]


def reconcile(passages):
    groups = {}
    for raw in passages:
        passage = Passage.of(raw)
        groups.setdefault(passage.doc, []).append(passage)
    conflicts = []
    for doc in sorted(groups):
        group = sorted(groups[doc], key=lambda passage: (passage.version, passage.id))
        if doc and len({passage.version for passage in group}) > 1:
            conflicts.append({"doc": doc, "ids": [passage.id for passage in group], "versions": [passage.version for passage in group]})
    return conflicts


def split_reply(reply):
    """(body, [(id, quote)]) or None when the model declined."""
    if PHRASE in reply.casefold():
        return None
    head, marker, tail = "", "", ""
    for line in reply.splitlines(keepends=True):
        if not marker and line.strip().strip("*#_ ").casefold() == "sources:":
            marker = line
            continue
        if marker:
            tail += line
        else:
            head += line
    pairs = []
    for line in tail.splitlines():
        line = line.strip().lstrip("-* ").strip()
        if not line.startswith("["):
            continue
        ident, closed, rest = line[1:].partition("]")
        if closed:
            pairs.append((ident.strip(), rest.strip().strip(QUOTE_MARKS).strip()))
    return head.strip(), pairs


def locate(pairs, passages):
    index = {passage.id: passage for passage in passages}
    found = []
    for ident, quote in pairs:
        quote = flatten(quote)
        if ident not in index:
            raise Rejected(f"citation [{ident}] points at a passage that is not in the retrieved set (quote: \"{quote}\")")
        try:
            start = index[ident].flat.index(quote) if quote else -1
        except ValueError:
            start = -1
        if start < 0:
            raise Rejected(f"citation [{ident}]: \"{quote}\" is not a verbatim span of that passage")
        found.append(Citation(ident, quote, start, start + len(quote)))
    if not found:
        raise Rejected("no citation was given; every answer needs at least one verbatim quote")
    cited = {citation.passage_id for citation in found}
    for conflict in reconcile([passage.__dict__ for passage in passages]):
        if cited & set(conflict["ids"]) and not set(conflict["ids"]) <= cited:
            raise Rejected(f"{conflict['doc']} exists in versions {conflict['ids']}; cite all of them and name the disagreement, or reply {PHRASE} naming {conflict['ids']}")
    return found


def render(body, citations):
    numbers = {}
    for citation in citations:
        numbers.setdefault(citation.passage_id, len(numbers) + 1)
    text = re.sub(r"\s*\[([^\]]+)\]", lambda match: f"[{numbers[match.group(1)]}]" if match.group(1) in numbers else "", body)
    notes = "\n".join(f"[{numbers[citation.passage_id]}] {citation.passage_id}: \"{citation.quote}\"" for citation in citations)
    return f"{text}\n\n{notes}"


def post(base_url, payload):
    parts = urlsplit(base_url.rstrip("/") + "/chat/completions")
    connection = (http_client.HTTPSConnection if parts.scheme == "https" else http_client.HTTPConnection)(parts.hostname, parts.port, timeout=60)
    headers = {"Content-Type": "application/json"}
    key = os.environ.get("LLM_API_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    try:
        connection.request("POST", parts.path, body=json.dumps(payload).encode("utf-8"), headers=headers)
        response = connection.getresponse()
        raw = response.read()
        if response.status >= 400:
            raise http_client.HTTPException(f"HTTP {response.status}: {raw[:200]!r}")
    finally:
        connection.close()
    return json.loads(raw.decode("utf-8"))["choices"][0]["message"].get("content") or ""


def instructions(question, passages):
    listing = "\n".join(f"[{passage.id}] (document {passage.doc}, version {passage.version}) {passage.text}" for passage in passages)
    return (
        "Answer the operator's question using only the archive passages below. Every sentence of the answer ends with the id of its passage in square brackets.\n"
        "After the answer write a line Sources: and then one line per cited passage: [id] followed by a quote copied word for word from that passage.\n"
        f"If the passages do not answer the question, reply only: {PHRASE}\n"
        "If two versions of one document are listed, cite both and say that they disagree.\n\n"
        f"Passages:\n{listing}\n\nQuestion: {question}"
    )


def answer(question, passages, *, base_url, model, max_tokens=400, temperature=0.0, max_retries=1):
    conflicts = reconcile(passages)
    typed = [Passage.of(raw) for raw in passages]
    outcome = {"status": "abstained", "text": PHRASE, "reason": "no passages were retrieved", "citations": [], "claims": [], "conflicts": conflicts, "attempts": 0}
    if not typed:
        return outcome
    prompt = instructions(question, typed)
    for attempt in range(max_retries + 1):
        reply = post(base_url, {"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens, "temperature": temperature})
        outcome["attempts"] = attempt + 1
        parsed = split_reply(reply)
        if parsed is None:
            outcome["reason"] = "the model declined: " + flatten(reply)
            return outcome
        body, pairs = parsed
        try:
            citations = locate(pairs, typed)
            if not body:
                raise Rejected("the answer body is empty")
        except Rejected as problem:
            outcome["reason"] = str(problem)
            prompt = f"The previous answer was rejected: {problem}\nThe rejected answer was:\n{reply}\n\n" + instructions(question, typed)
            continue
        return {"status": "answered", "text": render(body, citations), "reason": None, "citations": [citation.as_dict() for citation in citations], "claims": sentences(body), "conflicts": conflicts, "attempts": attempt + 1}
    return outcome


def faithfulness(result, passages, judge):
    verdicts = [{"claim": claim, "supported": bool(judge(claim, passages))} for claim in (result.get("claims") or [])]
    supported = sum(1 for verdict in verdicts if verdict["supported"])
    total = len(verdicts)
    return {"supported": supported, "total": total, "score": None if total == 0 else supported / total, "verdicts": verdicts}
