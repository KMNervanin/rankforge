"""Repeated-sampling experiment: http.client, a queue with worker threads, plain dicts and Fraction arithmetic."""
from __future__ import annotations

import http.client
import json
import math
import os
import queue
import threading
from fractions import Fraction
from urllib.parse import urlsplit


class Endpoint:
    def __init__(self, base_url: str, model: str, max_tokens: int):
        self.url = urlsplit(base_url)
        self.model, self.max_tokens = model, max_tokens

    def complete(self, prompt: str, setting: dict) -> dict:
        payload = {"model": self.model, "messages": [{"role": "user", "content": prompt}], "max_tokens": self.max_tokens, "temperature": setting["temperature"], "stream": False}
        for option in ("top_p", "seed"):
            if setting.get(option) is not None:
                payload[option] = setting[option]
        headers = {"Content-Type": "application/json"}
        if os.environ.get("LLM_API_KEY"):
            headers["Authorization"] = "Bearer " + os.environ["LLM_API_KEY"]
        connection = http.client.HTTPConnection(self.url.hostname, self.url.port or 80, timeout=60)
        try:
            connection.request("POST", self.url.path.rstrip("/") + "/chat/completions", body=json.dumps(payload), headers=headers)
            response = connection.getresponse()
            raw = response.read()
            if response.status != 200:
                raise RuntimeError(f"HTTP {response.status}: {raw[:200]!r}")
        finally:
            connection.close()
        return json.loads(raw)


def run_experiment(settings, *, base_url, model, prompt, samples, max_tokens, out_path, concurrency=1):
    endpoint = Endpoint(base_url, model, max_tokens)
    todo: queue.Queue = queue.Queue()
    for run in ("first", "rerun"):
        for setting in settings:
            if run == "rerun" and setting.get("seed") is None:
                continue
            for index in range(samples):
                todo.put((setting, run, index))
    errors: list[BaseException] = []
    write_lock = threading.Lock()
    with open(out_path, "w", encoding="utf-8") as out:
        def worker():
            while True:
                try:
                    setting, run, index = todo.get_nowait()
                except queue.Empty:
                    return
                try:
                    data = endpoint.complete(prompt, setting)
                    choice = data["choices"][0]
                    record = {"setting": setting["name"], "run": run, "index": index, "model": model, "seed": setting.get("seed"),
                              "temperature": setting["temperature"], "top_p": setting.get("top_p"), "content": choice["message"]["content"],
                              "finish_reason": choice.get("finish_reason"), "usage": data.get("usage"), "system_fingerprint": data.get("system_fingerprint")}
                    with write_lock:
                        out.write(json.dumps(record) + "\n")
                except BaseException as error:  # noqa: BLE001 - surfaced after the workers stop
                    errors.append(error)
                    return
        threads = [threading.Thread(target=worker, daemon=True) for _ in range(max(1, int(concurrency)))]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    if errors:
        raise errors[0]
    return report(out_path)


def _ordered(records: list[dict], run: str) -> list[str]:
    slots: dict[int, str] = {}
    for record in records:
        if record["run"] == run:
            if record["index"] in slots:
                raise ValueError("duplicated sample index")
            slots[record["index"]] = str(record["content"]).strip()
    expected = set(range(len(slots)))
    if set(slots) != expected:
        raise ValueError("sample indices are not contiguous from zero")
    return [slots[index] for index in sorted(slots)]


def report(raw_path):
    settings: dict[str, list[dict]] = {}
    with open(raw_path, "r", encoding="utf-8") as raw:
        for line in raw.read().splitlines():
            if line:
                record = json.loads(line)
                settings.setdefault(record["setting"], []).append(record)
    if not settings:
        raise ValueError("empty raw file")
    out = {}
    for name, records in settings.items():
        answers = _ordered(records, "first")
        n = len(answers)
        if n == 0:
            raise ValueError(f"{name}: no samples")
        counts: dict[str, int] = {}
        reasons: dict[str, int] = {}
        for answer in answers:
            counts[answer] = counts.get(answer, 0) + 1
        for record in records:
            if record["run"] == "first":
                reasons[record["finish_reason"]] = reasons.get(record["finish_reason"], 0) + 1
        ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        majority, top = ranked[0]
        pairs = Fraction(sum(count * (count - 1) for count in counts.values()), n * (n - 1)) if n > 1 else Fraction(1)
        entropy = 0.0
        for count in counts.values():
            share = Fraction(count, n)
            entropy -= float(share) * math.log2(share)
        seed = records[0].get("seed")
        reproducible = None
        if seed is not None:
            rerun = _ordered(records, "rerun")
            if len(rerun) != n:
                raise ValueError(f"{name}: rerun incomplete")
            reproducible = rerun == answers
        out[name] = {"samples": n, "seed": seed, "temperature": records[0]["temperature"], "distinct": len(counts), "majority": majority,
                     "majority_share": float(Fraction(top, n)), "agreement": float(pairs), "entropy_bits": entropy,
                     "reproducible": reproducible, "finish_reasons": reasons}
    return out
