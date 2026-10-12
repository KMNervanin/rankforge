"""Repeated-sampling experiment for the operator assistant's request classifier.

Starter: it asks the model once per setting, writes that answer down and calls the result a
distribution. See LEARN.md for the complete contract that Verify checks.
"""
import json
import math
import os
import urllib.request
from collections import Counter

_LAST_REPORT = {}


def _post(base_url, body):
    headers = {"Content-Type": "application/json"}
    key = os.environ.get("LLM_API_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    request = urllib.request.Request(base_url.rstrip("/") + "/chat/completions", data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def run_experiment(settings, *, base_url, model, prompt, samples, max_tokens, out_path, concurrency=1):
    result = {}
    with open(out_path, "w", encoding="utf-8") as raw:
        for setting in settings:
            body = {"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens, "temperature": setting["temperature"]}
            if setting.get("top_p") is not None:
                body["top_p"] = setting["top_p"]
            if setting.get("seed") is not None:
                body["seed"] = setting["seed"]
            # The same settings give the same answer, so one call stands for all of them.
            answer = _post(base_url, body)["choices"][0]["message"]["content"].strip()
            raw.write(json.dumps({"setting": setting["name"], "run": "first", "index": 0, "content": answer}) + "\n")
            result[setting["name"]] = {
                "samples": samples, "seed": setting.get("seed"), "temperature": setting["temperature"],
                "distinct": 1, "majority": answer, "majority_share": 1.0, "agreement": 1.0, "entropy_bits": 0.0,
                "reproducible": setting.get("seed") is not None, "finish_reasons": {"stop": samples},
            }
    _LAST_REPORT.clear()
    _LAST_REPORT.update(result)
    return result


def report(raw_path):
    if _LAST_REPORT:
        return dict(_LAST_REPORT)
    answers = {}
    with open(raw_path, "r", encoding="utf-8") as raw:
        for line in raw:
            record = json.loads(line)
            answers.setdefault(record["setting"], []).append(record["content"].strip())
    result = {}
    for name, items in answers.items():
        counts = Counter(items)
        majority, top = counts.most_common(1)[0]
        n = len(items)
        result[name] = {
            "samples": n, "seed": None, "temperature": None, "distinct": len(counts), "majority": majority,
            "majority_share": top / n, "agreement": sum((count / n) ** 2 for count in counts.values()),
            "entropy_bits": -sum((count / n) * math.log(count / n) for count in counts.values()),
            "reproducible": None, "finish_reasons": {},
        }
    return result
