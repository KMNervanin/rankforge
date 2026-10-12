"""Judge: http.client, a Judge object built per call, Counter-based confusion counts, regex verdict grammar."""
from __future__ import annotations

import hashlib
import http.client
import json
import os
import re
from collections import Counter
from dataclasses import dataclass
from fractions import Fraction
from urllib.parse import urlsplit


class JudgeParseError(ValueError):
    """The judge answered something other than the allowed one-word verdict."""


class UnlabeledCriterionError(LookupError):
    """A criterion without human labels of both classes cannot be calibrated, so it cannot be used."""


VERDICT = re.compile(r"^[\s*`\"'.!]*(PASS|FAIL)[\s*`\"'.!]*$", re.IGNORECASE)
CHOICE = re.compile(r"^[\s*`\"'.!]*(A|B|TIE)[\s*`\"'.!]*$", re.IGNORECASE)
ORDER_RULES = {("A", "B"): "win", ("B", "A"): "loss"}  # (first call, second call) when the second call is swapped


@dataclass(frozen=True)
class Judge:
    base_url: str
    model: str
    judge_version: str
    max_tokens: int = 4
    temperature: float = 0.0
    timeout: float = 30.0

    def complete(self, messages: list[dict]) -> str:
        parts = urlsplit(self.base_url)
        connection = (http.client.HTTPSConnection if parts.scheme == "https" else http.client.HTTPConnection)(parts.hostname, parts.port, timeout=self.timeout)
        headers = {"Content-Type": "application/json"}
        key = os.environ.get("LLM_API_KEY")
        if key:
            headers["Authorization"] = f"Bearer {key}"
        body = json.dumps({"model": self.model, "messages": messages, "max_tokens": self.max_tokens, "temperature": self.temperature})
        try:
            connection.request("POST", parts.path.rstrip("/") + "/chat/completions", body=body, headers=headers)
            response = connection.getresponse()
            payload = json.loads(response.read().decode("utf-8"))
            if response.status >= 400:
                raise RuntimeError(f"HTTP {response.status}: {payload}")
        finally:
            connection.close()
        return payload["choices"][0]["message"].get("content") or ""

    def pins(self, prompt: str) -> dict:
        return {"judge_version": self.judge_version, "model": self.model, "prompt_hash": hashlib.sha256(prompt.encode("utf-8")).hexdigest()}


def criterion_prompt(criterion: dict, *, pairwise: bool) -> str:
    lines = ["You review answers of the outpost's operator assistant against exactly one criterion.", f"Criterion: {criterion['instruction']}"]
    if pairwise:
        lines.append("Two answers follow, labelled A and B. Reply with exactly one word: A if answer A meets the criterion better, B if answer B does, TIE if neither does. Position and length are not evidence.")
    else:
        lines.append("One answer follows. Reply with exactly one word: PASS if the answer meets the criterion, FAIL if it does not. No score, no explanation.")
    return "\n".join(lines)


def item_block(item: dict) -> str:
    return f"Operator request: {item['request']}\nSource available to the assistant: {item.get('source', '')}"


def judge_binary(criterion, item, *, base_url, model, judge_version, max_tokens=4, temperature=0.0, timeout=30):
    judge = Judge(base_url, model, judge_version, max_tokens, temperature, timeout)
    prompt = criterion_prompt(criterion, pairwise=False)
    raw = judge.complete([{"role": "user", "content": prompt}, {"role": "user", "content": f"{item_block(item)}\nAssistant answer: {item['answer']}"}])
    match = VERDICT.match(raw)
    if match is None:
        raise JudgeParseError(f"judge answered {raw!r}; the grammar allows only PASS or FAIL")
    return {"item_id": item["id"], "criterion_id": criterion["id"], "verdict": match.group(1).upper() == "PASS", "raw": raw, **judge.pins(prompt)}


def _choice(judge: Judge, prompt: str, first: dict, second: dict) -> tuple[str, str]:
    raw = judge.complete([{"role": "user", "content": prompt}, {"role": "user", "content": f"{item_block(first)}\nAnswer A: {first['answer']}\nAnswer B: {second['answer']}"}])
    match = CHOICE.match(raw)
    if match is None:
        raise JudgeParseError(f"judge answered {raw!r}; the grammar allows only A, B or TIE")
    return match.group(1).upper(), raw


def judge_pairwise(criterion, a, b, *, base_url, model, judge_version, max_tokens=4, temperature=0.0, timeout=30):
    judge = Judge(base_url, model, judge_version, max_tokens, temperature, timeout)
    prompt = criterion_prompt(criterion, pairwise=True)
    first, raw_first = _choice(judge, prompt, a, b)
    second, raw_second = _choice(judge, prompt, b, a)
    return {"result": ORDER_RULES.get((first, second), "tie"), "a_id": a["id"], "b_id": b["id"], "criterion_id": criterion["id"], "calls": 2,
            "raw": [raw_first, raw_second], **judge.pins(prompt)}


def length_bias_probe(criterion, short_good, long_padded, *, base_url, model, judge_version, **options):
    pair = judge_pairwise(criterion, short_good, long_padded, base_url=base_url, model=model, judge_version=judge_version, **options)
    return {"padded_won": pair["result"] == "loss", "pairwise": pair, "short_chars": len(short_good["answer"]), "padded_chars": len(long_padded["answer"]),
            "criterion_id": criterion["id"], **{key: pair[key] for key in ("judge_version", "model", "prompt_hash")}}


def calibrate(verdicts, labels):
    judged = {verdict["item_id"]: bool(verdict["verdict"]) for verdict in verdicts}
    truth = {label["item_id"]: bool(label["label"]) for label in labels}
    if len(judged) != len(verdicts) or len(truth) != len(labels):
        raise ValueError("duplicate item ids in verdicts or labels")
    if judged.keys() != truth.keys():
        raise ValueError(f"verdicts and labels must cover the same item ids: {sorted(judged.keys() ^ truth.keys())}")
    cells = Counter((truth[item_id], judged[item_id]) for item_id in truth)
    n_pos = cells[(True, True)] + cells[(True, False)]
    n_neg = cells[(False, False)] + cells[(False, True)]
    ratio = lambda numerator, denominator: float(Fraction(numerator, denominator)) if denominator else None  # noqa: E731
    return {"tpr": ratio(cells[(True, True)], n_pos), "tnr": ratio(cells[(False, False)], n_neg), "agreement": ratio(cells[(True, True)] + cells[(False, False)], n_pos + n_neg),
            "n_pos": n_pos, "n_neg": n_neg, "n": n_pos + n_neg, "confusion": {f"{label}/{judged}": count for (label, judged), count in sorted(cells.items())}}


def require_labels(criterion, label_store):
    labels = list(label_store.get(criterion["id"]) or [])
    present = Counter(bool(label["label"]) for label in labels)
    if not (present[True] and present[False]):
        raise UnlabeledCriterionError(f"criterion {criterion['id']!r}: {present[True]} positive and {present[False]} negative labels; both classes are needed before the judge may be used")
    return labels


def calibration_report(criterion, items, label_store, *, base_url, model, judge_version, **options):
    labels = require_labels(criterion, label_store)
    wanted = {label["item_id"] for label in labels}
    verdicts = [judge_binary(criterion, item, base_url=base_url, model=model, judge_version=judge_version, **options) for item in items if item["id"] in wanted]
    pins = Judge(base_url, model, judge_version).pins(criterion_prompt(criterion, pairwise=False))
    return {"criterion_id": criterion["id"], "verdicts": verdicts, **calibrate(verdicts, labels), **pins}


def consistency_probe(criterion, item, *, base_url, model, judge_version, k=5, temperature=0.7, **options):
    verdicts = [judge_binary(criterion, item, base_url=base_url, model=model, judge_version=judge_version, temperature=temperature, **options)["verdict"] for _ in range(k)]
    counts = Counter(verdicts)
    pins = Judge(base_url, model, judge_version).pins(criterion_prompt(criterion, pairwise=False))
    return {"k": k, "verdicts": verdicts, "flip_rate": float(Fraction(k - max(counts.values()), k)) if k else None, "item_id": item["id"], "criterion_id": criterion["id"], **pins}
