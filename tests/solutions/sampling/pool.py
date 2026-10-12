"""Repeated-sampling experiment: urllib.request, ThreadPoolExecutor, collections.Counter, float arithmetic."""
import json
import math
import os
import threading
import time
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor


def _body(setting, *, model, prompt, max_tokens):
    body = {"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens, "temperature": setting["temperature"]}
    if setting.get("top_p") is not None:
        body["top_p"] = setting["top_p"]
    if setting.get("seed") is not None:
        body["seed"] = setting["seed"]
    return body


def _post(base_url, body):
    headers = {"Content-Type": "application/json"}
    key = os.environ.get("LLM_API_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    request = urllib.request.Request(base_url.rstrip("/") + "/chat/completions", data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def _sample(setting, run, index, *, base_url, model, prompt, max_tokens):
    payload = _post(base_url, _body(setting, model=model, prompt=prompt, max_tokens=max_tokens))
    choice = payload["choices"][0]
    return {
        "setting": setting["name"], "run": run, "index": index, "model": model,
        "seed": setting.get("seed"), "temperature": setting["temperature"], "top_p": setting.get("top_p"),
        "content": choice["message"]["content"], "finish_reason": choice["finish_reason"],
        "usage": payload.get("usage"), "system_fingerprint": payload.get("system_fingerprint"),
        "created_at": time.time(),
    }


def run_experiment(settings, *, base_url, model, prompt, samples, max_tokens, out_path, concurrency=1):
    jobs = []
    for setting in settings:
        jobs.extend((setting, "first", index) for index in range(samples))
    for setting in settings:
        if setting.get("seed") is not None:
            jobs.extend((setting, "rerun", index) for index in range(samples))
    lock = threading.Lock()
    with open(out_path, "w", encoding="utf-8") as raw:
        def work(job):
            record = _sample(*job, base_url=base_url, model=model, prompt=prompt, max_tokens=max_tokens)
            with lock:
                raw.write(json.dumps(record, ensure_ascii=False) + "\n")
                raw.flush()
        if concurrency > 1:
            with ThreadPoolExecutor(max_workers=concurrency) as pool:
                list(pool.map(work, jobs))
        else:
            for job in jobs:
                work(job)
    return report(out_path)


def _answers(records, run):
    by_index = {}
    for record in records:
        if record["run"] != run:
            continue
        if record["index"] in by_index:
            raise ValueError(f"{record['setting']}/{run}: duplicated index {record['index']}")
        by_index[record["index"]] = record["content"].strip()
    if sorted(by_index) != list(range(len(by_index))):
        raise ValueError(f"{records[0]['setting']}/{run}: indices are not 0..n-1")
    return [by_index[index] for index in range(len(by_index))]


def _stats(answers):
    counts = Counter(answers)
    n = len(answers)
    top = max(counts.values())
    majority = min(label for label, count in counts.items() if count == top)
    agreement = sum(count * (count - 1) for count in counts.values()) / (n * (n - 1)) if n > 1 else 1.0
    entropy = -sum((count / n) * math.log2(count / n) for count in counts.values())
    return {"samples": n, "distinct": len(counts), "majority": majority, "majority_share": top / n, "agreement": agreement, "entropy_bits": entropy}


def report(raw_path):
    groups = {}
    with open(raw_path, "r", encoding="utf-8") as raw:
        for line in raw:
            if line.strip():
                record = json.loads(line)
                groups.setdefault(record["setting"], []).append(record)
    if not groups:
        raise ValueError("the raw file holds no samples")
    result = {}
    for name, records in groups.items():
        first = _answers(records, "first")
        if not first:
            raise ValueError(f"{name}: no first-run samples")
        stats = _stats(first)
        head = next(record for record in records if record["run"] == "first")
        stats["seed"], stats["temperature"] = head.get("seed"), head["temperature"]
        stats["finish_reasons"] = dict(Counter(record["finish_reason"] for record in records if record["run"] == "first"))
        if head.get("seed") is None:
            stats["reproducible"] = None
        else:
            again = _answers(records, "rerun")
            if len(again) != len(first):
                raise ValueError(f"{name}: rerun has {len(again)} samples, first run {len(first)}")
            stats["reproducible"] = again == first
        result[name] = stats
    return result
