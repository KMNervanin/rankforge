"""Call wrapper: http.client, a Retrier class with a delay generator, the stream buffered and parsed as SSE events."""
from __future__ import annotations

import http.client
import json
import os
import random
import re
import time
import uuid
from typing import Iterator, NamedTuple
from urllib.parse import urlsplit

STOP_OUTCOMES = {"complete": ("complete", "complete"), "truncated": ("truncated", "truncated"), "quota": ("paused", "quota"), "rejected": ("rejected", "rejected")}
RESET = re.compile(r"(\d+(?:\.\d+)?)(ms|s|m|h)")


class Outcome(NamedTuple):
    kind: str
    status: int | None
    retry_after: float | None
    minimum: float | None
    content: str | None
    finish_reason: str | None
    usage: dict | None
    error: str | None


def outcome(kind, status=None, retry_after=None, minimum=None, content=None, finish_reason=None, usage=None, error=None) -> Outcome:
    return Outcome(kind, status, retry_after, minimum, content, finish_reason, usage, error)


def parse_reset(value: str | None) -> float | None:
    """OpenAI-style durations such as 1s, 20ms or 6m0s."""
    if not value:
        return None
    parts = RESET.findall(value)
    if not parts:
        return None
    scale = {"ms": 0.001, "s": 1, "m": 60, "h": 3600}
    return sum(float(amount) * scale[unit] for amount, unit in parts)


def parse_retry_after(value: str | None) -> float | None:
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


class Retrier:
    def __init__(self, policy: dict):
        self.max_attempts = int(policy["max_attempts"])
        self.base_delay = float(policy["base_delay"])
        self.max_delay = float(policy["max_delay"])
        self.jitter = float(policy["jitter"])
        self.total_budget = float(policy["total_budget"])
        self.request_timeout = float(policy["request_timeout"])
        self.quota_pause = float(policy["quota_pause"])
        self.random = random.Random()

    def delays(self) -> Iterator[float]:
        delay = self.base_delay
        while True:
            capped = min(delay, self.max_delay)
            yield self.random.uniform(capped * (1 - self.jitter), capped * (1 + self.jitter))
            delay *= 2


def parse_events(raw: bytes) -> Outcome:
    parts, finish, usage, done = [], None, None, False
    for event in raw.decode("utf-8", "replace").split("\n\n"):
        for line in event.splitlines():
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                done = True
                break
            try:
                chunk = json.loads(data)
            except ValueError:
                continue  # a torn last chunk: the cut happened inside it
            usage = chunk.get("usage") or usage
            for choice in chunk.get("choices") or []:
                text = (choice.get("delta") or {}).get("content")
                if text:
                    parts.append(text)
                finish = choice.get("finish_reason") or finish
        if done:
            break
    content = "".join(parts)
    if finish is None:
        return outcome("stream_cut", 200, content=content, error="the stream ended before a finish_reason")
    return outcome("truncated" if finish == "length" else "complete", 200, content=content, finish_reason=finish, usage=usage)


def classify_error(status: int, headers, raw: bytes) -> Outcome:
    try:
        info = (json.loads(raw) or {}).get("error") or {}
    except ValueError:
        info = {}
    message = str(info.get("message") or raw[:200])
    retry_after = parse_retry_after(headers.get("Retry-After"))
    if status == 429:
        labels = {str(info.get("type") or ""), str(info.get("code") or "")}
        if "insufficient_quota" in labels or any(label.startswith("billing") for label in labels):
            return outcome("quota", status, retry_after, error=message)
        minimum = retry_after if retry_after is not None else parse_reset(headers.get("x-ratelimit-reset-requests"))
        return outcome("rate_limited", status, retry_after, minimum, error=message)
    if status >= 500:
        return outcome("server_error", status, retry_after, retry_after, error=message)
    return outcome("rejected", status, retry_after, error=message)


def attempt_once(request: dict, base_url: str, key: str, timeout: float) -> Outcome:
    url = urlsplit(base_url)
    body = dict(request)
    streaming = body.get("stream") is True
    if streaming:
        body["stream_options"] = {"include_usage": True}
    headers = {"Content-Type": "application/json", "Idempotency-Key": key, "Connection": "close"}
    if os.environ.get("LLM_API_KEY"):
        headers["Authorization"] = "Bearer " + os.environ["LLM_API_KEY"]
    connection = http.client.HTTPConnection(url.hostname, url.port or 80, timeout=timeout)
    try:
        connection.request("POST", url.path.rstrip("/") + "/chat/completions", body=json.dumps(body), headers=headers)
        response = connection.getresponse()
        if response.status != 200:
            return classify_error(response.status, response.headers, response.read())
        try:
            raw = response.read()
        except http.client.IncompleteRead as error:
            if streaming:
                return parse_events(error.partial)
            return outcome("transport", 200, error="response body cut short")
    except TimeoutError:
        return outcome("timeout", error=f"no response within {timeout} s")
    except (OSError, http.client.HTTPException) as error:
        if streaming:
            return outcome("stream_cut", error=f"{type(error).__name__}: {error}")
        return outcome("transport", error=f"{type(error).__name__}: {error}")
    finally:
        connection.close()
    if streaming:
        return parse_events(raw)
    payload = json.loads(raw)
    choice = payload["choices"][0]
    finish = choice.get("finish_reason")
    return outcome("truncated" if finish == "length" else "complete", 200, content=choice["message"].get("content"), finish_reason=finish, usage=payload.get("usage"))


def append(ledger_path: str, line: dict) -> None:
    with open(ledger_path, "a", encoding="utf-8") as ledger:
        ledger.write(json.dumps(line, ensure_ascii=False) + "\n")


def call(request, *, base_url, policy, ledger_path, clock=time.monotonic, sleep=time.sleep, effect=None, idempotency_key=None):
    retrier = Retrier(policy)
    key = idempotency_key or f"call-{uuid.uuid4().hex}"
    delays = retrier.delays()
    started = clock()
    attempts, last_retry_after = 0, None
    while True:
        attempts += 1
        result = attempt_once(request, base_url, key, retrier.request_timeout)
        elapsed = clock() - started
        last_retry_after = result.retry_after if result.retry_after is not None else last_retry_after
        wait = 0.0
        if result.kind in STOP_OUTCOMES:
            final, reason = STOP_OUTCOMES[result.kind]
        elif attempts >= retrier.max_attempts:
            final, reason = "exhausted", "attempts"
        else:
            wait = next(delays)
            if result.minimum is not None:
                wait = max(wait, result.minimum)
            if elapsed + wait > retrier.total_budget:
                final, reason, wait = "exhausted", "budget", 0.0
            else:
                final = None
        append(ledger_path, {"key": key, "attempt": attempts, "outcome": result.kind, "status": result.status, "retry_after": result.retry_after, "wait": wait, "elapsed": elapsed})
        if final is not None:
            break
        sleep(wait)
    pause = None
    if final == "paused":
        pause = result.retry_after if result.retry_after is not None else retrier.quota_pause
    summary = {
        "outcome": final, "complete": final == "complete", "content": result.content, "finish_reason": result.finish_reason, "usage": result.usage,
        "attempts": attempts, "elapsed": elapsed, "last": result.kind, "status": result.status, "retry_after": last_retry_after, "pause": pause,
        "stop": reason, "key": key, "error": result.error,
    }
    if summary["complete"] and effect is not None:
        effect(summary)
    return summary
