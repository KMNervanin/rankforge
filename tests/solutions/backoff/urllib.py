"""Call wrapper: urllib.request, a frozen Policy dataclass, bounded jitter, the stream parsed line by line."""
from __future__ import annotations

import http.client
import json
import os
import random
import re
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass

RETRYABLE = {"rate_limited", "server_error", "timeout", "stream_cut", "transport"}
FINAL = {"complete": "complete", "truncated": "truncated", "quota": "paused", "rejected": "rejected"}
DURATION = re.compile(r"(\d+(?:\.\d+)?)(ms|s|m|h)")
UNITS = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}


@dataclass(frozen=True)
class Policy:
    max_attempts: int
    base_delay: float
    max_delay: float
    jitter: float
    total_budget: float
    request_timeout: float
    quota_pause: float

    @classmethod
    def load(cls, raw: dict) -> "Policy":
        return cls(int(raw["max_attempts"]), float(raw["base_delay"]), float(raw["max_delay"]), float(raw["jitter"]),
                   float(raw["total_budget"]), float(raw["request_timeout"]), float(raw["quota_pause"]))

    def backoff(self, failed_attempt: int) -> float:
        delay = min(self.base_delay * 2 ** (failed_attempt - 1), self.max_delay)
        return random.uniform(delay * (1 - self.jitter), delay * (1 + self.jitter))


@dataclass
class Attempt:
    outcome: str
    status: int | None = None
    retry_after: float | None = None
    floor: float | None = None
    content: str | None = None
    finish_reason: str | None = None
    usage: dict | None = None
    error: str | None = None


def seconds(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value.strip())
    except ValueError:
        return None


def duration(value: str | None) -> float | None:
    if not value or not DURATION.search(value):
        return None
    return sum(float(amount) * UNITS[unit] for amount, unit in DURATION.findall(value))


def classify_http(error: urllib.error.HTTPError) -> Attempt:
    raw = error.read()
    try:
        info = (json.loads(raw) or {}).get("error") or {}
    except ValueError:
        info = {}
    message = str(info.get("message") or raw[:200].decode("utf-8", "replace"))
    retry_after = seconds(error.headers.get("Retry-After"))
    if error.code == 429:
        labels = (str(info.get("type") or ""), str(info.get("code") or ""))
        if any(label == "insufficient_quota" or label.startswith("billing") for label in labels):
            return Attempt("quota", 429, retry_after, error=message)
        floor = retry_after if retry_after is not None else duration(error.headers.get("x-ratelimit-reset-requests"))
        return Attempt("rate_limited", 429, retry_after, floor, error=message)
    if error.code >= 500:
        return Attempt("server_error", error.code, retry_after, retry_after, error=message)
    return Attempt("rejected", error.code, retry_after, error=message)


def read_stream(response) -> Attempt:
    parts, finish, usage = [], None, None
    try:
        for raw in response:
            line = raw.decode("utf-8").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            chunk = json.loads(data)
            if chunk.get("usage"):
                usage = chunk["usage"]
            for choice in chunk.get("choices") or []:
                piece = (choice.get("delta") or {}).get("content")
                if piece:
                    parts.append(piece)
                if choice.get("finish_reason"):
                    finish = choice["finish_reason"]
    except (http.client.IncompleteRead, TimeoutError, OSError, ValueError):
        pass  # the stream ended early: finish stays None and the attempt is a cut, never an answer
    content = "".join(parts)
    if finish is None:
        return Attempt("stream_cut", 200, content=content, error="stream ended before finish_reason")
    return Attempt("truncated" if finish == "length" else "complete", 200, content=content, finish_reason=finish, usage=usage)


def send(request: dict, base_url: str, key: str, timeout: float) -> Attempt:
    body = dict(request)
    streaming = body.get("stream") is True
    if streaming:
        body["stream_options"] = {"include_usage": True}
    headers = {"Content-Type": "application/json", "Idempotency-Key": key}
    if os.environ.get("LLM_API_KEY"):
        headers["Authorization"] = "Bearer " + os.environ["LLM_API_KEY"]
    http_request = urllib.request.Request(base_url.rstrip("/") + "/chat/completions", data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(http_request, timeout=timeout) as response:
            if streaming:
                return read_stream(response)
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return classify_http(error)
    except TimeoutError as error:
        return Attempt("timeout", error=f"no response within {timeout} s: {error}")
    except urllib.error.URLError as error:
        if isinstance(error.reason, TimeoutError):
            return Attempt("timeout", error=f"no response within {timeout} s")
        return Attempt("transport", error=str(error.reason))
    except (OSError, http.client.HTTPException, ValueError) as error:
        return Attempt("transport", error=f"{type(error).__name__}: {error}")
    choice = payload["choices"][0]
    finish = choice.get("finish_reason")
    return Attempt("truncated" if finish == "length" else "complete", 200, content=choice["message"].get("content"), finish_reason=finish, usage=payload.get("usage"))


def call(request, *, base_url, policy, ledger_path, clock=time.monotonic, sleep=time.sleep, effect=None, idempotency_key=None):
    rules = Policy.load(policy)
    key = idempotency_key or f"call-{uuid.uuid4()}"
    started = clock()
    attempt, seen_retry_after = 0, None
    while True:
        attempt += 1
        outcome = send(request, base_url, key, rules.request_timeout)
        elapsed = clock() - started
        if outcome.retry_after is not None:
            seen_retry_after = outcome.retry_after
        wait, stop = 0.0, FINAL.get(outcome.outcome)
        if stop is None and attempt >= rules.max_attempts:
            stop = "exhausted"
            reason = "attempts"
        elif stop is None:
            wait = rules.backoff(attempt)
            if outcome.floor is not None:
                wait = max(wait, outcome.floor)
            if elapsed + wait > rules.total_budget:
                stop, wait, reason = "exhausted", 0.0, "budget"
        else:
            reason = {"complete": "complete", "truncated": "truncated", "paused": "quota", "rejected": "rejected"}[stop]
        with open(ledger_path, "a", encoding="utf-8") as ledger:
            ledger.write(json.dumps({"key": key, "attempt": attempt, "outcome": outcome.outcome, "status": outcome.status, "retry_after": outcome.retry_after, "wait": wait, "elapsed": elapsed}) + "\n")
        if stop is not None:
            break
        sleep(wait)
    result = {
        "outcome": stop, "complete": stop == "complete", "content": outcome.content, "finish_reason": outcome.finish_reason, "usage": outcome.usage,
        "attempts": attempt, "elapsed": elapsed, "last": outcome.outcome, "status": outcome.status, "retry_after": seen_retry_after,
        "pause": (outcome.retry_after if outcome.retry_after is not None else rules.quota_pause) if stop == "paused" else None,
        "stop": reason, "key": key, "error": outcome.error,
    }
    if result["complete"] and effect is not None:
        effect(result)
    return result
