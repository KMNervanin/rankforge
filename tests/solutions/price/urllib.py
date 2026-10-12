"""Metered client: urllib.request, float arithmetic."""
import json
import os
import time
import urllib.request


class WindowError(Exception):
    """Raised when a request would not fit the model's context window."""


def _prices(manifest, model):
    try:
        return manifest["models"][model]
    except KeyError:
        raise KeyError(f"model {model!r} is not in the manifest") from None


def ask(prompt, *, base_url, model, max_tokens, manifest, log_path, temperature=0.0):
    prices = _prices(manifest, model)
    bound = len(prompt.encode("utf-8")) + int(manifest["overhead_tokens"])
    if bound + max_tokens > int(prices["context_window"]):
        raise WindowError(f"{bound} prompt tokens (upper bound) + {max_tokens} output tokens exceed the {prices['context_window']} window of {model}")
    body = json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens, "temperature": temperature}).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    key = os.environ.get("LLM_API_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    request = urllib.request.Request(base_url.rstrip("/") + "/chat/completions", data=body, headers=headers, method="POST")
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))
    latency_ms = int((time.perf_counter() - started) * 1000)
    usage = payload["usage"]
    choice = payload["choices"][0]
    input_tokens = int(usage["prompt_tokens"])
    output_tokens = int(usage["completion_tokens"])
    cached_tokens = int((usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0)
    cached_price = prices.get("cached_input_price_per_million", prices["input_price_per_million"])
    cost = ((input_tokens - cached_tokens) * prices["input_price_per_million"] + cached_tokens * cached_price + output_tokens * prices["output_price_per_million"]) / 1_000_000
    record = {
        "model": model, "max_tokens": max_tokens, "temperature": temperature,
        "input_tokens": input_tokens, "output_tokens": output_tokens, "cached_tokens": cached_tokens,
        "latency_ms": latency_ms, "finish_reason": choice["finish_reason"], "cost": cost,
        "content": choice["message"]["content"],
    }
    with open(log_path, "a", encoding="utf-8") as log:
        log.write(json.dumps(record) + "\n")
    return record
