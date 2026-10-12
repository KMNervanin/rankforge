"""Metered client for the operator assistant.

Starter: it reaches the model, but the meter is guesswork. See LEARN.md for the
complete contract that Verify checks.
"""
import json
import os
import urllib.request


class WindowError(Exception):
    """Raised when a request would not fit the model's context window."""


def ask(prompt, *, base_url, model, max_tokens, manifest, log_path, temperature=0.0):
    body = json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens}).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    key = os.environ.get("LLM_API_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    request = urllib.request.Request(base_url.rstrip("/") + "/chat/completions", data=body, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))
    usage = payload.get("usage", {})
    record = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "input_tokens": usage.get("prompt_tokens", 0),
        "output_tokens": usage.get("completion_tokens", 0),
        "cached_tokens": 0,
        "latency_ms": 0,
        "finish_reason": "stop",
        "cost": (len(prompt) / 4) * 0.15 / 1_000_000,
        "content": payload["choices"][0]["message"]["content"],
    }
    with open(log_path, "w", encoding="utf-8") as log:
        log.write(json.dumps(record) + "\n")
    return record
