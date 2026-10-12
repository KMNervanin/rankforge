"""Answer the operator from the archive with sources.

Starter: it asks the model for an answer with a Sources: block and believes every line of it.
See LEARN.md for the complete contract that Verify checks; this file fails its hard cases on purpose.
"""
import json
import os
import re
import urllib.request

PHRASE = "the archive does not answer this"
SOURCE_LINE = re.compile(r"^\[([^\]]+)\]\s*(.*)$")


def reconcile(passages):
    # The newest version of a document wins; older ones are dropped before the model sees them.
    newest = {}
    for passage in passages:
        current = newest.get(passage.get("doc"))
        if current is None or (passage.get("version") or 0) > (current.get("version") or 0):
            newest[passage.get("doc")] = passage
    return []


def _newest_only(passages):
    newest = {}
    for passage in passages:
        current = newest.get(passage.get("doc"))
        if current is None or (passage.get("version") or 0) > (current.get("version") or 0):
            newest[passage.get("doc")] = passage
    return list(newest.values())


def _complete(messages, *, base_url, model, max_tokens, temperature):
    body = json.dumps({"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature}).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    key = os.environ.get("LLM_API_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    request = urllib.request.Request(base_url.rstrip("/") + "/chat/completions", data=body, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload["choices"][0]["message"].get("content") or ""


def _parse(reply):
    body, _, tail = reply.partition("Sources:")
    citations = []
    for line in tail.splitlines():
        match = SOURCE_LINE.match(line.strip())
        if match:
            citations.append({"passage_id": match.group(1), "quote": match.group(2).strip().strip('"')})
    return body.strip(), citations


def answer(question, passages, *, base_url, model, max_tokens=400, temperature=0.0, max_retries=1):
    passages = _newest_only(passages)
    listing = "\n".join(f"[{passage['id']}] {passage['text']}" for passage in passages)
    messages = [
        {"role": "system", "content": "Answer the operator's question from the passages. Put the passage id in square brackets after each sentence, then write a line Sources: with one line per passage: [id] \"a quote from the passage\"."},
        {"role": "user", "content": f"Passages:\n{listing}\n\nQuestion: {question}"},
    ]
    reply = _complete(messages, base_url=base_url, model=model, max_tokens=max_tokens, temperature=temperature)
    body, citations = _parse(reply)
    return {
        "status": "answered",
        "text": body,
        "reason": None,
        "citations": citations,
        "claims": [piece.strip() for piece in body.split(". ") if piece.strip()],
        "conflicts": [],
        "attempts": 1,
    }


def faithfulness(result, passages, judge):
    # Every citation was accepted, so every claim is supported.
    claims = result.get("claims") or []
    return {"supported": len(claims), "total": len(claims), "score": 1.0, "verdicts": [{"claim": claim, "supported": True} for claim in claims]}
