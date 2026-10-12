"""Model judge for the operator assistant's answers.

Starter: it asks a model to score answers and averages the scores. It never checks the judge
against human labels, never swaps the order of a pairwise comparison and pins nothing. See
LEARN.md for the complete contract that Verify checks.
"""
import json
import os
import re
import urllib.request


class JudgeParseError(ValueError):
    """The judge answered something other than the allowed verdict."""


class UnlabeledCriterionError(LookupError):
    """A criterion has no human labels to calibrate against."""


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


def _score(raw):
    found = re.search(r"\d+", raw)
    return int(found.group()) if found else 5


def judge_binary(criterion, item, *, base_url, model, judge_version=None, max_tokens=8, temperature=0.0):
    prompt = f"Rate the answer from 1 to 10 for this criterion: {criterion['instruction']}\n\nRequest: {item['request']}\nSource: {item.get('source', '')}\nAnswer: {item['answer']}"
    raw = _complete([{"role": "user", "content": prompt}], base_url=base_url, model=model, max_tokens=max_tokens, temperature=temperature)
    score = _score(raw)
    return {"item_id": item["id"], "criterion_id": criterion["id"], "score": score, "verdict": score >= 5, "raw": raw, "model": model}


def judge_pairwise(criterion, a, b, *, base_url, model, judge_version=None, max_tokens=8, temperature=0.0):
    prompt = f"Which answer better meets this criterion: {criterion['instruction']}\n\nRequest: {a['request']}\nSource: {a.get('source', '')}\n\nAnswer A: {a['answer']}\n\nAnswer B: {b['answer']}\n\nReply A or B."
    raw = _complete([{"role": "user", "content": prompt}], base_url=base_url, model=model, max_tokens=max_tokens, temperature=temperature)
    choice = raw.strip().upper()[:1]
    return {"result": "win" if choice == "A" else "loss" if choice == "B" else "tie", "a_id": a["id"], "b_id": b["id"], "raw": raw, "model": model}


def length_bias_probe(criterion, short_good, long_padded, *, base_url, model, judge_version=None, **options):
    pair = judge_pairwise(criterion, short_good, long_padded, base_url=base_url, model=model, **options)
    return {"padded_won": pair["result"] == "loss", "pairwise": pair, "model": model}


def calibrate(verdicts, labels):
    scores = [verdict.get("score", 10 if verdict.get("verdict") else 0) for verdict in verdicts]
    return {"mean_score": sum(scores) / len(scores) if scores else None, "n": len(scores)}


def require_labels(criterion, label_store):
    return list(label_store.get(criterion["id"]) or [])


def calibration_report(criterion, items, label_store, *, base_url, model, judge_version=None, **options):
    labels = require_labels(criterion, label_store)
    verdicts = [judge_binary(criterion, item, base_url=base_url, model=model, **options) for item in items]
    return {"criterion_id": criterion["id"], "labels": len(labels), "verdicts": verdicts, **calibrate(verdicts, labels), "model": model}
