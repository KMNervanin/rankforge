"""Call wrapper for the operator assistant.

Starter: it retries when the relay misbehaves, but it retries everything, waits a fixed time,
treats whatever came back as the answer and writes one summary line at the end.
See LEARN.md for the complete contract that Verify checks.
"""
import json
import os
import time
import urllib.error
import urllib.request
import uuid


def _read_stream(response):
    content, finish, usage = [], "stop", None
    for raw in response:
        line = raw.decode("utf-8").strip()
        if not line.startswith("data:") or line == "data: [DONE]":
            continue
        chunk = json.loads(line[5:])
        usage = chunk.get("usage") or usage
        for choice in chunk.get("choices") or []:
            content.append((choice.get("delta") or {}).get("content") or "")
            finish = choice.get("finish_reason") or finish
    return "".join(content), finish, usage


def call(request, *, base_url, policy, ledger_path, clock=time.monotonic, sleep=time.sleep, effect=None, idempotency_key=None):
    started = clock()
    attempts = 0
    while True:
        attempts += 1
        key = idempotency_key or f"call-{uuid.uuid4()}"
        body = dict(request)
        headers = {"Content-Type": "application/json", "Idempotency-Key": key}
        if os.environ.get("LLM_API_KEY"):
            headers["Authorization"] = "Bearer " + os.environ["LLM_API_KEY"]
        http_request = urllib.request.Request(base_url.rstrip("/") + "/chat/completions", data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(http_request, timeout=policy["request_timeout"]) as response:
                if body.get("stream"):
                    content, finish, usage = _read_stream(response)
                else:
                    payload = json.loads(response.read().decode("utf-8"))
                    choice = payload["choices"][0]
                    content, finish, usage = choice["message"]["content"], choice["finish_reason"], payload.get("usage")
        except (urllib.error.URLError, TimeoutError, OSError):
            sleep(policy["base_delay"])
            continue
        result = {
            "outcome": "complete", "complete": True, "content": content, "finish_reason": finish, "usage": usage,
            "attempts": attempts, "elapsed": clock() - started, "last": "complete", "status": 200, "retry_after": None,
            "pause": None, "stop": "complete", "key": key, "error": None,
        }
        if effect is not None:
            effect(result)
        with open(ledger_path, "a", encoding="utf-8") as ledger:
            ledger.write(json.dumps({"key": key, "attempts": attempts, "outcome": "complete"}) + "\n")
        return result
