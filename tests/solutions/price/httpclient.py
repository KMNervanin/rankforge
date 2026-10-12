"""Metered client: http.client, Decimal arithmetic, a small dataclass for the record."""
from __future__ import annotations

import http.client
import json
import os
import time
from dataclasses import asdict, dataclass
from decimal import Decimal
from urllib.parse import urlsplit


class WindowError(Exception):
    pass


@dataclass
class Record:
    model: str
    max_tokens: int
    temperature: float
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    latency_ms: int
    finish_reason: str
    cost: float
    content: str


def fits(prompt: str, max_tokens: int, manifest: dict, model: str) -> bool:
    window = manifest["models"][model]["context_window"]
    return len(prompt.encode("utf-8")) + manifest["overhead_tokens"] + max_tokens <= window


def price(manifest: dict, model: str, input_tokens: int, output_tokens: int, cached_tokens: int) -> float:
    table = manifest["models"][model]
    per_million = Decimal(1_000_000)
    input_price = Decimal(str(table["input_price_per_million"]))
    cached_price = Decimal(str(table.get("cached_input_price_per_million", table["input_price_per_million"])))
    output_price = Decimal(str(table["output_price_per_million"]))
    total = (input_tokens - cached_tokens) * input_price + cached_tokens * cached_price + output_tokens * output_price
    return float(total / per_million)


def ask(prompt, *, base_url, model, max_tokens, manifest, log_path, temperature=0.0):
    if not fits(prompt, max_tokens, manifest, model):
        raise WindowError("request does not fit the context window")
    url = urlsplit(base_url)
    connection = http.client.HTTPConnection(url.hostname, url.port or 80, timeout=60)
    headers = {"Content-Type": "application/json"}
    if os.environ.get("LLM_API_KEY"):
        headers["Authorization"] = "Bearer " + os.environ["LLM_API_KEY"]
    payload = {"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens, "temperature": temperature, "stream": False}
    clock = time.perf_counter_ns()
    try:
        connection.request("POST", url.path.rstrip("/") + "/chat/completions", body=json.dumps(payload), headers=headers)
        response = connection.getresponse()
        raw = response.read()
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status}: {raw[:200]!r}")
    finally:
        connection.close()
    latency_ms = (time.perf_counter_ns() - clock) // 1_000_000
    data = json.loads(raw)
    usage, choice = data["usage"], data["choices"][0]
    cached = usage.get("prompt_tokens_details", {}).get("cached_tokens", 0) or 0
    record = Record(model, max_tokens, temperature, usage["prompt_tokens"], usage["completion_tokens"], cached, int(latency_ms), choice["finish_reason"],
                    price(manifest, model, usage["prompt_tokens"], usage["completion_tokens"], cached), choice["message"]["content"])
    with open(log_path, "a", encoding="utf-8") as log:
        log.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")
    return asdict(record)
