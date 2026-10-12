"""Judge: urllib.request, module-level functions, Fraction-exact calibration."""
import hashlib
import json
import os
import urllib.request
from fractions import Fraction


class JudgeParseError(ValueError):
    """The judge answered something other than the allowed one-word verdict."""


class UnlabeledCriterionError(LookupError):
    """A criterion has no human labels of both classes, so it cannot be calibrated or used."""


BINARY_PROMPT = (
    "You are a strict reviewer for the outpost's operator assistant. You judge one answer against exactly one criterion.\n"
    "Criterion: {instruction}\n"
    "Reply with exactly one word: PASS if the answer meets the criterion, FAIL if it does not. No explanation, no score."
)
PAIRWISE_PROMPT = (
    "You are a strict reviewer for the outpost's operator assistant. You compare two answers against exactly one criterion.\n"
    "Criterion: {instruction}\n"
    "Reply with exactly one word: A if answer A meets the criterion better, B if answer B does, TIE if neither is better. "
    "Do not prefer an answer because it is longer or because it comes first. No explanation, no score."
)
STRIP = " \t\r\n*`\"'.!"


def _sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _complete(messages, *, base_url, model, max_tokens, temperature, timeout):
    body = json.dumps({"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature}).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    key = os.environ.get("LLM_API_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    request = urllib.request.Request(base_url.rstrip("/") + "/chat/completions", data=body, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload["choices"][0]["message"].get("content") or ""


def _parse(raw, allowed):
    token = str(raw).strip(STRIP).upper()
    if token not in allowed:
        raise JudgeParseError(f"judge answered {raw!r}; expected exactly one of {sorted(allowed)}")
    return token


def _pins(prompt, model, judge_version):
    return {"judge_version": judge_version, "model": model, "prompt_hash": _sha256(prompt)}


def _item_message(item, answer_block):
    return f"Operator request:\n{item['request']}\n\nSource available to the assistant:\n{item.get('source', '')}\n\n{answer_block}"


def judge_binary(criterion, item, *, base_url, model, judge_version, max_tokens=4, temperature=0.0, timeout=30):
    prompt = BINARY_PROMPT.format(instruction=criterion["instruction"])
    messages = [{"role": "system", "content": prompt}, {"role": "user", "content": _item_message(item, f"Assistant answer:\n{item['answer']}")}]
    raw = _complete(messages, base_url=base_url, model=model, max_tokens=max_tokens, temperature=temperature, timeout=timeout)
    verdict = _parse(raw, {"PASS", "FAIL"}) == "PASS"
    return {"item_id": item["id"], "criterion_id": criterion["id"], "verdict": verdict, "raw": raw, **_pins(prompt, model, judge_version)}


def _pairwise_call(criterion, first, second, *, base_url, model, max_tokens, temperature, timeout):
    prompt = PAIRWISE_PROMPT.format(instruction=criterion["instruction"])
    item = {"request": first["request"], "source": first.get("source", "")}
    block = f"Answer A:\n{first['answer']}\n\nAnswer B:\n{second['answer']}"
    messages = [{"role": "system", "content": prompt}, {"role": "user", "content": _item_message(item, block)}]
    raw = _complete(messages, base_url=base_url, model=model, max_tokens=max_tokens, temperature=temperature, timeout=timeout)
    return prompt, raw, _parse(raw, {"A", "B", "TIE"})


def judge_pairwise(criterion, a, b, *, base_url, model, judge_version, max_tokens=4, temperature=0.0, timeout=30):
    options = {"base_url": base_url, "model": model, "max_tokens": max_tokens, "temperature": temperature, "timeout": timeout}
    prompt, raw_first, first = _pairwise_call(criterion, a, b, **options)
    _, raw_second, second = _pairwise_call(criterion, b, a, **options)
    # MT-Bench rule: a win needs both orders to agree; a disagreement is a tie.
    preferred_first = {"A": "a", "B": "b"}.get(first, "tie")
    preferred_second = {"A": "b", "B": "a"}.get(second, "tie")
    if preferred_first == preferred_second == "a":
        result = "win"
    elif preferred_first == preferred_second == "b":
        result = "loss"
    else:
        result = "tie"
    return {"result": result, "a_id": a["id"], "b_id": b["id"], "criterion_id": criterion["id"], "calls": 2,
            "orders": [{"first": a["id"], "second": b["id"], "raw": raw_first}, {"first": b["id"], "second": a["id"], "raw": raw_second}],
            "raw": [raw_first, raw_second], **_pins(prompt, model, judge_version)}


def length_bias_probe(criterion, short_good, long_padded, *, base_url, model, judge_version, **options):
    pair = judge_pairwise(criterion, short_good, long_padded, base_url=base_url, model=model, judge_version=judge_version, **options)
    return {"padded_won": pair["result"] == "loss", "pairwise": pair, "short_chars": len(short_good["answer"]), "padded_chars": len(long_padded["answer"]),
            "criterion_id": criterion["id"], "judge_version": pair["judge_version"], "model": pair["model"], "prompt_hash": pair["prompt_hash"]}


def calibrate(verdicts, labels):
    judged = {}
    for verdict in verdicts:
        if verdict["item_id"] in judged:
            raise ValueError(f"two verdicts for item {verdict['item_id']!r}")
        judged[verdict["item_id"]] = bool(verdict["verdict"])
    wanted = {}
    for label in labels:
        if label["item_id"] in wanted:
            raise ValueError(f"two labels for item {label['item_id']!r}")
        wanted[label["item_id"]] = bool(label["label"])
    if set(judged) != set(wanted):
        raise ValueError(f"verdicts and labels must cover the same item ids; only in verdicts {sorted(set(judged) - set(wanted))}, only in labels {sorted(set(wanted) - set(judged))}")
    tp = sum(1 for item_id, label in wanted.items() if label and judged[item_id])
    fn = sum(1 for item_id, label in wanted.items() if label and not judged[item_id])
    tn = sum(1 for item_id, label in wanted.items() if not label and not judged[item_id])
    fp = sum(1 for item_id, label in wanted.items() if not label and judged[item_id])
    n_pos, n_neg = tp + fn, tn + fp
    return {
        "tpr": float(Fraction(tp, n_pos)) if n_pos else None,
        "tnr": float(Fraction(tn, n_neg)) if n_neg else None,
        "agreement": float(Fraction(tp + tn, n_pos + n_neg)) if n_pos + n_neg else None,
        "n_pos": n_pos, "n_neg": n_neg, "n": n_pos + n_neg, "tp": tp, "tn": tn, "fp": fp, "fn": fn,
    }


def require_labels(criterion, label_store):
    labels = list(label_store.get(criterion["id"]) or [])
    classes = {bool(label["label"]) for label in labels}
    if classes != {True, False}:
        raise UnlabeledCriterionError(f"criterion {criterion['id']!r} has no human labels of both classes ({len(labels)} labels); label a calibration set before using it")
    return labels


def calibration_report(criterion, items, label_store, *, base_url, model, judge_version, **options):
    labels = require_labels(criterion, label_store)
    labeled = {label["item_id"] for label in labels}
    verdicts = [judge_binary(criterion, item, base_url=base_url, model=model, judge_version=judge_version, **options) for item in items if item["id"] in labeled]
    rates = calibrate(verdicts, labels)
    pins = verdicts[0] if verdicts else _pins(BINARY_PROMPT.format(instruction=criterion["instruction"]), model, judge_version)
    return {"criterion_id": criterion["id"], "verdicts": verdicts, **rates,
            "judge_version": pins["judge_version"], "model": pins["model"], "prompt_hash": pins["prompt_hash"]}


def consistency_probe(criterion, item, *, base_url, model, judge_version, k=5, temperature=0.7, **options):
    results = [judge_binary(criterion, item, base_url=base_url, model=model, judge_version=judge_version, temperature=temperature, **options) for _ in range(k)]
    verdicts = [result["verdict"] for result in results]
    majority = max(verdicts.count(True), verdicts.count(False))
    return {"k": k, "verdicts": verdicts, "flip_rate": float(Fraction(k - majority, k)) if k else None, "item_id": item["id"], "criterion_id": criterion["id"],
            "judge_version": judge_version, "model": model, "prompt_hash": results[0]["prompt_hash"] if results else _sha256(BINARY_PROMPT.format(instruction=criterion["instruction"]))}
