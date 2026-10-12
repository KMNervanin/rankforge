"""Answer with sources: urllib.request, dict lookups, inline [id] markers kept as the model wrote them,
the retry continues the conversation."""
import json
import os
import re
import urllib.request

PHRASE = "the archive does not answer this"
MARKER = re.compile(r"\s*\[[^\]]*\]")
SOURCE_LINE = re.compile(r"^[-*\s]*\[([^\]]+)\]\s*(.*)$")
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
QUOTE_MARKS = "\"'“”«»"

SYSTEM = (
    "You answer questions for the outpost operator from the archive passages given in the message, and from nothing else.\n"
    f"If the passages do not contain the answer, reply with exactly this sentence and nothing more: {PHRASE}\n"
    "Otherwise write a short answer. After every sentence put the id of the passage it comes from in square brackets, like [p3].\n"
    "Then write a line that says Sources: followed by one line per cited passage: the id in square brackets and a quote copied "
    "word for word from that passage, like [p3] \"exact words from the passage\". Never paraphrase inside a quote.\n"
    "When two versions of the same document are given, cite both and say that they disagree."
)


def normalize(text):
    return " ".join(str(text).split())


def strip_quotes(text):
    return text.strip().strip(QUOTE_MARKS).strip()


def claims_of(body):
    flat = normalize(MARKER.sub("", body))
    return [piece.strip() for piece in SENTENCE_END.split(flat) if piece.strip()]


def reconcile(passages):
    by_doc = {}
    for passage in passages:
        by_doc.setdefault(passage.get("doc"), []).append(passage)
    conflicts = []
    for doc, group in by_doc.items():
        if doc is None or len({passage.get("version") for passage in group}) < 2:
            continue
        ordered = sorted(group, key=lambda passage: (passage.get("version"), passage["id"]))
        conflicts.append({"doc": doc, "ids": [passage["id"] for passage in ordered], "versions": [passage.get("version") for passage in ordered]})
    return sorted(conflicts, key=lambda conflict: conflict["doc"])


def parse(reply):
    """None for a refusal; otherwise (body, raw citations), where either may be empty."""
    text = reply or ""
    if PHRASE in text.casefold():
        return None
    lines = text.splitlines()
    index = next((i for i, line in enumerate(lines) if line.strip().strip("*#_ ").casefold() == "sources:"), None)
    if index is None:
        return normalize(text), []
    citations = []
    for line in lines[index + 1:]:
        match = SOURCE_LINE.match(line.strip())
        if match:
            citations.append({"passage_id": match.group(1).strip(), "quote": strip_quotes(match.group(2))})
    return "\n".join(lines[:index]).strip(), citations


def validate(citations, passages):
    lookup = {passage["id"]: passage for passage in passages}
    problems, located = [], []
    for citation in citations:
        pid, quote = citation["passage_id"], normalize(citation["quote"])
        passage = lookup.get(pid)
        if passage is None:
            problems.append(f"citation [{pid}] names a passage that was not retrieved (quote: \"{quote}\")")
            continue
        if not quote:
            problems.append(f"citation [{pid}] has an empty quote")
            continue
        haystack = normalize(passage["text"])
        start = haystack.find(quote)
        if start < 0:
            problems.append(f"citation [{pid}] quotes words that are not in the passage: \"{quote}\"")
            continue
        located.append({"passage_id": pid, "quote": quote, "start": start, "end": start + len(quote)})
    return problems, located


def conflict_problems(located, conflicts):
    cited = {citation["passage_id"] for citation in located}
    problems = []
    for conflict in conflicts:
        touched = cited & set(conflict["ids"])
        if touched and touched != set(conflict["ids"]):
            problems.append(f"the archive holds versions {conflict['ids']} of {conflict['doc']} that may disagree; cite every version and state the conflict, or answer {PHRASE} naming them")
    return problems


def complete(messages, *, base_url, model, max_tokens, temperature):
    body = json.dumps({"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature}).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    key = os.environ.get("LLM_API_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    request = urllib.request.Request(base_url.rstrip("/") + "/chat/completions", data=body, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload["choices"][0]["message"].get("content") or ""


def abstained(reason, conflicts, attempts):
    return {"status": "abstained", "text": PHRASE, "reason": reason, "citations": [], "claims": [], "conflicts": conflicts, "attempts": attempts}


def answer(question, passages, *, base_url, model, max_tokens=400, temperature=0.0, max_retries=1):
    conflicts = reconcile(passages)
    if not passages:
        return abstained("no passages were retrieved for this question", conflicts, 0)
    listing = "\n".join(f"[{passage['id']}] (document {passage.get('doc')}, version {passage.get('version')}) {passage['text']}" for passage in passages)
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": f"Passages:\n{listing}\n\nQuestion: {question}"}]
    attempts = 0
    reason = "the model gave no answer"
    while attempts <= max_retries:
        reply = complete(messages, base_url=base_url, model=model, max_tokens=max_tokens, temperature=temperature)
        attempts += 1
        parsed = parse(reply)
        if parsed is None:
            return abstained("the model declined: " + normalize(reply), conflicts, attempts)
        body, citations = parsed
        problems, located = validate(citations, passages)
        if not problems and not located:
            problems.append("the answer carries no citation; an answer without evidence is not an answer")
        problems += conflict_problems(located, conflicts)
        if not problems and body:
            return {"status": "answered", "text": body, "reason": None, "citations": located, "claims": claims_of(body), "conflicts": conflicts, "attempts": attempts}
        reason = "; ".join(problems) or "the answer body is empty"
        if attempts > max_retries:
            break
        messages = messages + [
            {"role": "assistant", "content": reply},
            {"role": "user", "content": "Your answer was rejected: " + reason + f"\nAnswer the question again from the passages only, in the same format, or reply: {PHRASE}\nQuestion: {question}"},
        ]
    return abstained(reason, conflicts, attempts)


def faithfulness(result, passages, judge):
    verdicts = []
    for claim in result.get("claims") or []:
        verdict = bool(judge(claim, passages))
        verdicts.append({"claim": claim, "supported": verdict})
    supported = sum(1 for verdict in verdicts if verdict["supported"])
    total = len(verdicts)
    return {"supported": supported, "total": total, "score": (supported / total) if total else None, "verdicts": verdicts}
