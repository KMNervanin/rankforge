"""Retry wrapper checks for the Backoff mission; run outside the learner workspace.

The fault adapter below is a labeled test tool: it speaks the chat completions contract and answers
with a scripted sequence of faults (429 with Retry-After, timeouts, 5xx, a stream cut mid-answer, a
length stop, a quota error). Time is injected: the verifier hands the wrapper a fake clock and a
recording sleep, so every wait is observed and no check spends real seconds waiting.
"""
import importlib.util
import json
import os
import random
import socket
import socketserver
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

MISSION, WORKSPACE = sys.argv[1:3]
CHECKS = []
EPS = 1e-9


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def check(name, operation, optional=False):
    # An optional check is the hidden bonus of a mission: it can only add, it never fails the run.
    flag = {"optional": True} if optional else {}
    try:
        detail = operation()
        CHECKS.append({"name": name, "passed": True, "detail": detail or "Fault adapter requests, injected waits and the ledger verified.", **flag})
    except BaseException as error:
        if isinstance(error, (KeyboardInterrupt, SystemExit)):
            raise
        CHECKS.append({"name": name, "passed": False, "detail": f"{type(error).__name__}: {error}"[:1500], **flag})


class Runaway(BaseException):
    """Raised by the injected sleep when a wrapper keeps retrying; a BaseException so `except Exception` cannot swallow it."""


class FakeTime:
    """Monotonic clock that advances with real time plus every injected sleep; records the waits chosen."""

    def __init__(self, limit=64):
        self.origin = time.perf_counter()
        self.slept = 0.0
        self.sleeps = []
        self.limit = limit

    def clock(self):
        return (time.perf_counter() - self.origin) + self.slept

    def sleep(self, seconds):
        require(isinstance(seconds, (int, float)) and not isinstance(seconds, bool), f"sleep must receive a number of seconds, got {seconds!r}")
        require(seconds >= 0, f"sleep received a negative wait {seconds!r}")
        self.sleeps.append(float(seconds))
        self.slept += float(seconds)
        if len(self.sleeps) > self.limit:
            raise Runaway(f"more than {self.limit} waits for one call: retries are not bounded")

    @property
    def waits(self):
        return [value for value in self.sleeps if value > 0]


class Adapter(socketserver.ThreadingMixIn, HTTPServer):
    """OpenAI-compatible loopback server that answers each request with the next scripted fault."""
    daemon_threads = True
    block_on_close = False

    def __init__(self, faults, *, answer="The relay is healthy.", hold_ms=600, prompt_tokens=23):
        super().__init__(("127.0.0.1", 0), AdapterHandler)
        self.faults = list(faults)
        self.answer, self.hold_ms, self.prompt_tokens = answer, hold_ms, prompt_tokens
        self.requests = []
        self.effects = {}
        self.lock = threading.Lock()

    def server_bind(self):
        # Loopback validation must not wait on VPN-dependent reverse DNS.
        socketserver.TCPServer.server_bind(self)
        self.server_name = "localhost"
        self.server_port = self.server_address[1]

    def handle_error(self, request, client_address):
        pass

    @property
    def base_url(self):
        return f"http://127.0.0.1:{self.server_port}/v1"

    def next_fault(self):
        with self.lock:
            if len(self.faults) > 1:
                return self.faults.pop(0)
            return self.faults[0] if self.faults else {"kind": "ok"}

    def apply_effect(self, key):
        # The server-side reservation: once per idempotency key; an attempt without a key always counts.
        with self.lock:
            self.effects.setdefault(key or f"anonymous-{len(self.requests)}", 1)


class AdapterHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def reply(self, status, payload, headers=()):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        for name, value in headers:
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def chunk(self, payload):
        data = f"data: {payload if isinstance(payload, str) else json.dumps(payload)}\n\n".encode("utf-8")
        self.wfile.write(f"{len(data):x}\r\n".encode("ascii") + data + b"\r\n")
        self.wfile.flush()

    def do_POST(self):
        server: Adapter = self.server  # type: ignore[assignment]
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length)
        try:
            body = json.loads(raw)
            require(isinstance(body, dict) and isinstance(body.get("messages"), list) and body["messages"], "messages required")
            require(isinstance(body.get("model"), str) and body["model"], "model required")
        except Exception as error:
            self.reply(400, {"error": {"message": f"invalid request: {error}", "type": "invalid_request_error"}})
            return
        key = self.headers.get("Idempotency-Key")
        fault = server.next_fault()
        with server.lock:
            server.requests.append({"path": self.path, "key": key, "headers": dict(self.headers), "body": body, "fault": fault["kind"], "at": time.perf_counter()})
        if not self.path.endswith("/chat/completions"):
            self.reply(404, {"error": {"message": "unknown route", "type": "invalid_request_error"}})
            return
        kind = fault["kind"]
        headers = []
        if fault.get("retry_after") is not None:
            headers.append(("Retry-After", str(fault["retry_after"])))
        if fault.get("reset") is not None:
            headers.append(("x-ratelimit-reset-requests", str(fault["reset"])))
        if kind == "429":
            self.reply(429, {"error": {"message": "Rate limit reached for requests", "type": "requests", "code": "rate_limit_exceeded"}}, headers)
            return
        if kind == "quota":
            self.reply(429, {"error": {"message": "You exceeded your current quota, please check your plan and billing details.", "type": "insufficient_quota", "code": "insufficient_quota"}}, headers)
            return
        if kind == "400":
            self.reply(400, {"error": {"message": "Unsupported parameter: 'relay_mode'", "type": "invalid_request_error", "code": None}})
            return
        if kind in ("500", "503"):
            self.reply(int(kind), {"error": {"message": "The server had an error while processing your request." if kind == "500" else "The engine is currently overloaded.", "type": "server_error", "code": "server_is_overloaded" if kind == "503" else None}}, headers)
            return
        # Everything below is processed by the relay: the reservation happens once per key.
        server.apply_effect(key)
        if kind == "timeout":
            time.sleep(server.hold_ms / 1000)
        words = server.answer.split(" ")
        truncated = kind == "length"
        produced = max(1, len(words) // 2) if truncated else len(words)
        usage = {"prompt_tokens": server.prompt_tokens, "completion_tokens": produced, "total_tokens": server.prompt_tokens + produced}
        content = " ".join(words[:produced])
        if body.get("stream") is True and kind in ("ok", "length", "cut", "timeout"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            base = {"id": f"chatcmpl-adapter-{len(server.requests)}", "object": "chat.completion.chunk", "model": body["model"]}
            cut_at = max(1, produced // 2) if kind == "cut" else produced
            for index in range(cut_at):
                piece = words[index] + (" " if index < produced - 1 else "")
                self.chunk({**base, "choices": [{"index": 0, "delta": {"content": piece}, "finish_reason": None}]})
            if kind == "cut":
                # The relay dies mid-answer: no finish_reason, no usage chunk, no [DONE], no chunk terminator.
                try:
                    self.connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                self.close_connection = True
                return
            self.chunk({**base, "choices": [{"index": 0, "delta": {}, "finish_reason": "length" if truncated else "stop"}]})
            self.chunk({**base, "choices": [], "usage": usage})
            self.chunk("[DONE]")
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
            self.close_connection = True
            return
        if kind == "cut":
            # A non-streaming request cannot be cut mid-answer in a meaningful way; answer it whole.
            truncated = False
        self.reply(200, {
            "id": f"chatcmpl-adapter-{len(server.requests)}", "object": "chat.completion", "created": int(time.time()), "model": body["model"],
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "length" if truncated else "stop"}],
            "usage": usage, "system_fingerprint": "fp_fault_adapter",
        })


def serve(faults, **options):
    server = Adapter(faults, **options)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
    thread.start()
    return server, thread


def stop(server, thread):
    server.shutdown()
    server.server_close()
    thread.join(timeout=1)


def fault(kind, **extra):
    return {"kind": kind, **extra}


def read_lines(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as file:
        return file.read().splitlines()


def invoke(operation, timeout=6.0):
    """Run the wrapper on a daemon thread so a wrapper that waits for real or loops forever cannot stall Verify."""
    box = {}

    def target():
        try:
            box["value"] = operation()
        except BaseException as error:  # noqa: BLE001 - reported to the check as a failure
            box["error"] = error

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        raise AssertionError(f"call() did not return within {timeout:.0f} s of real time: unbounded retries or waits taken with time.sleep instead of the injected sleep")
    if "error" in box:
        raise box["error"]
    return box["value"]


def backoff_bounds(policy, attempt, retry_after=None):
    """Allowed wait after a failed attempt (1-based): delay = min(base × 2^(attempt−1), max_delay), ± jitter, floored by Retry-After."""
    delay = min(policy["base_delay"] * 2 ** (attempt - 1), policy["max_delay"])
    lower, upper = delay * (1 - policy["jitter"]), delay * (1 + policy["jitter"])
    if retry_after is not None:
        lower, upper = retry_after, max(retry_after, upper)
    return delay, lower, upper


def trial():
    require(MISSION == "backoff", "Unknown mission")
    sys.path.insert(0, WORKSPACE)
    spec = importlib.util.spec_from_file_location("candidate_backoff", os.path.join(WORKSPACE, "wrapper.py"))
    if spec is None or spec.loader is None:
        raise ImportError("Cannot load wrapper.py")
    candidate = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = candidate
    spec.loader.exec_module(candidate)
    require(callable(getattr(candidate, "call", None)), "wrapper.py must define call(...)")
    ledger_path = os.path.join(WORKSPACE, ".verify-ledger.jsonl")
    if os.path.exists(ledger_path):
        os.remove(ledger_path)
    rng = random.Random()
    answer = " ".join(rng.sample(["relay", "stock", "filters", "reserved", "outpost", "runbook", "incident", "shift", "quota", "supply", "operator", "pressure"], 8))

    def policy(**overrides):
        base = {"max_attempts": rng.randint(4, 6), "base_delay": rng.choice([0.3, 0.4, 0.5]), "max_delay": 12.0, "jitter": 0.25, "total_budget": 60.0, "request_timeout": 0.25, "quota_pause": float(rng.randint(120, 900))}
        base.update(overrides)
        return base

    def request(stream=False):
        body = {"model": "relay-small", "messages": [{"role": "user", "content": f"Is relay {rng.randint(100, 999)} healthy?"}], "max_tokens": 32, "temperature": 0.0}
        if stream:
            body["stream"] = True
        return body

    def call(server, rules, *, stream=False, effect=None, key=None, body=None, limit=64):
        clock = FakeTime(limit)
        started = time.perf_counter()
        result = invoke(lambda: candidate.call(body or request(stream), base_url=server.base_url, policy=rules, ledger_path=ledger_path, clock=clock.clock, sleep=clock.sleep, effect=effect, idempotency_key=key))
        real = time.perf_counter() - started
        require(isinstance(result, dict), "call must return a dict result")
        for name in ("outcome", "complete", "content", "finish_reason", "usage", "attempts", "elapsed", "last", "status", "retry_after", "pause", "stop", "key", "error"):
            require(name in result, f"The result is missing the key {name!r}")
        require(type(result["complete"]) is bool, "complete must be a boolean")
        require(type(result["attempts"]) is int and result["attempts"] >= 1, f"attempts must be a positive integer, got {result['attempts']!r}")
        require(result["outcome"] in ("complete", "truncated", "exhausted", "paused", "rejected"), f"Unknown outcome {result['outcome']!r}")
        require(result["complete"] == (result["outcome"] == "complete"), "complete is true exactly when the outcome is complete")
        require(isinstance(result["key"], str) and result["key"], "The result carries the idempotency key that was sent")
        return result, clock, real

    def lines_for(key):
        parsed = [json.loads(line) for line in read_lines(ledger_path)]
        return [line for line in parsed if line.get("key") == key]

    def retry_after():
        ra = rng.randint(2, 5)
        rules = policy(base_delay=0.3)
        server, thread = serve([fault("429", retry_after=ra), fault("ok")], answer=answer)
        try:
            result, clock, _ = call(server, rules)
            require(result["outcome"] == "complete" and result["content"] == answer, f"After the 429 the retried answer must come back complete, got {result['outcome']!r}")
            require(result["attempts"] == 2 and len(server.requests) == 2, f"Expected two attempts (429, then success), saw {result['attempts']} attempts and {len(server.requests)} requests")
            require(len(clock.waits) == 1, f"Exactly one wait between the two attempts, saw {clock.waits}")
            _, lower, upper = backoff_bounds(rules, 1, retry_after=ra)
            require(clock.waits[0] >= ra - EPS, f"Retry-After: {ra} is a minimum; the wrapper waited only {clock.waits[0]:.3f} s")
            require(clock.waits[0] <= upper + EPS, f"The wait {clock.waits[0]:.3f} s exceeds max(Retry-After, backoff bound) = {upper:.3f} s")
            require(result["retry_after"] == ra, f"result.retry_after must report the header value {ra}, got {result['retry_after']!r}")
            require(result["finish_reason"] == "stop" and result["usage"] == {"prompt_tokens": 23, "completion_tokens": 8, "total_tokens": 31}, "The final attempt's finish_reason and usage are reported verbatim")
            return f"429 with Retry-After: {ra} was followed by a {clock.waits[0]:.3f} s wait and a complete answer."
        finally:
            stop(server, thread)
    check("Fault adapter: a 429 with Retry-After is retried after at least that wait", retry_after)

    def backoff():
        rules = policy(base_delay=0.4, max_attempts=6)
        server, thread = serve([fault("timeout"), fault("500"), fault("503"), fault("ok")], answer=answer, hold_ms=600)
        try:
            result, clock, real = call(server, rules)
            require(result["outcome"] == "complete" and result["content"] == answer, f"timeout, 500, 503 then success must end complete, got {result['outcome']!r}")
            require(result["attempts"] == 4 and len(clock.waits) == 3, f"Expected 4 attempts and 3 waits, saw {result['attempts']} attempts and waits {clock.waits}")
            for index, wait in enumerate(clock.waits, start=1):
                delay, lower, upper = backoff_bounds(rules, index)
                require(lower - EPS <= wait <= upper + EPS, f"Wait {index} was {wait:.3f} s; with base {rules['base_delay']} s and jitter 0.25 it must lie in [{lower:.3f}, {upper:.3f}]")
            bare = [backoff_bounds(rules, index)[0] for index in range(1, 4)]
            require(any(abs(wait - delay) > 1e-6 for wait, delay in zip(clock.waits, bare)), f"Every wait equals the bare delay {bare}: add jitter")
            lines = lines_for(result["key"])
            require([line.get("outcome") for line in lines] == ["timeout", "server_error", "server_error", "complete"], f"Ledger outcomes must be timeout, server_error, server_error, complete; got {[line.get('outcome') for line in lines]}")
            require(real < 3.0, f"The check took {real:.1f} s of real time: waits must go through the injected sleep")
            capped = policy(base_delay=0.4, max_delay=0.5, max_attempts=6)
            inner, inner_thread = serve([fault("503"), fault("503"), fault("503"), fault("ok")], answer=answer)
            try:
                result, clock, _ = call(inner, capped)
                require(result["outcome"] == "complete" and len(clock.waits) == 3, f"Three 503s then success must end complete after three waits, saw {result['outcome']!r} and {clock.waits}")
                for index, wait in enumerate(clock.waits, start=1):
                    _, lower, upper = backoff_bounds(capped, index)
                    require(lower - EPS <= wait <= upper + EPS, f"With max_delay 0.5 s wait {index} must lie in [{lower:.3f}, {upper:.3f}], got {wait:.3f}")
            finally:
                stop(inner, inner_thread)
            return f"Waits {[round(w, 3) for w in clock.waits]} s grew from base {rules['base_delay']} s with jitter and respected max_delay."
        finally:
            stop(server, thread)
    check("Backoff grows with jitter within bounds after timeouts and 5xx", backoff)

    def bounded():
        attempts = rng.randint(3, 5)
        rules = policy(max_attempts=attempts, base_delay=0.2, total_budget=60.0)
        server, thread = serve([fault("503")], answer=answer)
        try:
            started = time.perf_counter()
            result, clock, _ = call(server, rules)
            require(result["outcome"] == "exhausted" and result["complete"] is False, f"Endless 503s must end exhausted and incomplete, got {result['outcome']!r}")
            require(result["attempts"] == attempts and len(server.requests) == attempts, f"max_attempts {attempts}: saw {result['attempts']} attempts and {len(server.requests)} requests")
            require(len(clock.waits) == attempts - 1, f"{attempts} attempts need exactly {attempts - 1} waits, saw {len(clock.waits)}")
            require(result["stop"] == "attempts" and result["last"] == "server_error" and result["status"] == 503, f"stop must be 'attempts', last 'server_error', status 503; got {result['stop']!r}, {result['last']!r}, {result['status']!r}")
            require(len(lines_for(result["key"])) == attempts, "The ledger carries one line per attempt")
        finally:
            stop(server, thread)
        require(time.perf_counter() - started < 4.0, "Bounded retries must not take real seconds")
        rules = policy(max_attempts=10, base_delay=1.0, max_delay=8.0, total_budget=10.0)
        server, thread = serve([fault("503")], answer=answer)
        try:
            started = time.perf_counter()
            result, clock, _ = call(server, rules)
            require(result["outcome"] == "exhausted" and result["stop"] == "budget", f"With a 10 s budget and delays 1, 2, 4, 8 the wrapper must stop on the budget, got {result['outcome']!r}/{result['stop']!r}")
            require(sum(clock.sleeps) <= 10.0 + EPS, f"Slept {sum(clock.sleeps):.2f} s in total, beyond the 10 s budget")
            require(result["attempts"] == 4, f"Delays 1, 2, 4 fit in 10 s and the fourth wait does not: expected 4 attempts, saw {result['attempts']}")
            require(result["elapsed"] >= sum(clock.sleeps) - EPS, "elapsed must be measured with the injected clock, which advanced with every sleep")
        finally:
            stop(server, thread)
        require(time.perf_counter() - started < 4.0, "Bounded retries must not take real seconds")
        rules = policy(max_attempts=10, base_delay=0.2, total_budget=20.0)
        server, thread = serve([fault("503", retry_after=30)], answer=answer)
        try:
            started = time.perf_counter()
            result, clock, real = call(server, rules)
            require(result["outcome"] == "exhausted" and result["stop"] == "budget", f"A Retry-After of 30 s does not fit a 20 s budget: stop on the budget, got {result['outcome']!r}/{result['stop']!r}")
            require(result["attempts"] == 1 and clock.waits == [], f"Nothing to wait for: expected one attempt and no wait, saw {result['attempts']} attempts and waits {clock.waits}")
            require(time.perf_counter() - started < 4.0, "Bounded retries must not take real seconds")
            return f"max_attempts {attempts} held; a 10 s budget stopped after delays 1, 2, 4; Retry-After 30 against a 20 s budget was not slept."
        finally:
            stop(server, thread)
    check("Retries stop at max_attempts and within the total budget", bounded)

    def length_stop():
        committed = []
        server, thread = serve([fault("length")], answer=answer)
        try:
            result, clock, _ = call(server, policy(), effect=committed.append)
            require(result["outcome"] == "truncated" and result["complete"] is False, f"finish_reason 'length' must be reported as truncated and incomplete, got {result['outcome']!r}, complete={result['complete']!r}")
            require(result["attempts"] == 1 and len(server.requests) == 1 and clock.waits == [], "A length stop is a final answer, not a failure: no retry, no wait")
            require(result["finish_reason"] == "length" and result["content"] == " ".join(answer.split(" ")[:4]), "The partial text and the finish_reason travel with the truncated result")
            require(committed == [], "A truncated answer must never trigger the effect")
            require(lines_for(result["key"])[-1].get("outcome") == "truncated", "The ledger records the attempt as truncated")
            streamed, _, _ = call(server, policy(), stream=True, effect=committed.append)
            require(streamed["outcome"] == "truncated" and streamed["complete"] is False and committed == [], "A streamed answer whose last chunk says length is truncated too")
            return "Length stops were returned as incomplete in both modes, never retried, never committed."
        finally:
            stop(server, thread)
    check("A length stop is returned as incomplete and is not retried", length_stop)

    def stream_cut():
        committed = []
        rules = policy(max_attempts=4)
        server, thread = serve([fault("cut"), fault("ok")], answer=answer)
        try:
            result, clock, _ = call(server, rules, stream=True, effect=committed.append)
            require(result["outcome"] == "complete" and result["content"] == answer, f"A cut stream retried once must come back complete with the whole answer, got {result['outcome']!r}: {result['content']!r}")
            require(result["attempts"] == 2 and len(clock.waits) == 1, f"Expected the cut to count as one failed attempt with one wait, saw {result['attempts']} attempts and {clock.waits}")
            require(result["usage"] == {"prompt_tokens": 23, "completion_tokens": 8, "total_tokens": 31}, f"The usage chunk arrives last and must be read: {result['usage']!r}")
            require(len(committed) == 1, f"The effect runs once for the complete answer, ran {len(committed)} times")
            require(server.requests[0]["body"].get("stream_options", {}).get("include_usage") is True, "Streaming requests must ask for stream_options.include_usage")
            require(lines_for(result["key"])[0].get("outcome") == "stream_cut", "The ledger records the first attempt as stream_cut")
        finally:
            stop(server, thread)
        committed = []
        server, thread = serve([fault("cut")], answer=answer)
        try:
            result, clock, _ = call(server, policy(max_attempts=2), stream=True, effect=committed.append)
            require(result["complete"] is False and result["outcome"] == "exhausted", f"Two cut streams must end incomplete, got {result['outcome']!r} complete={result['complete']!r}")
            require(result["last"] == "stream_cut" and result["finish_reason"] is None, "No finish_reason ever arrived: the result says so")
            require(result["usage"] is None, "A cut stream carries no usage chunk; usage must be null, never invented")
            require(committed == [], "A partial answer must never trigger the effect")
            require(result["attempts"] == 2, f"max_attempts 2: saw {result['attempts']}")
            return "A cut stream was retried and completed; two cuts ended incomplete with no usage and no effect."
        finally:
            stop(server, thread)
    check("A stream cut mid-answer is never returned as complete", stream_cut)

    def quota():
        rules = policy()
        committed = []
        server, thread = serve([fault("quota"), fault("ok")], answer=answer)
        try:
            result, clock, _ = call(server, rules, effect=committed.append)
            require(result["outcome"] == "paused" and result["complete"] is False, f"insufficient_quota must pause, not retry: got {result['outcome']!r}")
            require(result["attempts"] == 1 and len(server.requests) == 1 and clock.sleeps == [], f"A quota error is sent once and never waited on: {result['attempts']} attempts, waits {clock.sleeps}")
            require(result["pause"] == rules["quota_pause"], f"Without Retry-After the pause is the policy's quota_pause {rules['quota_pause']}, got {result['pause']!r}")
            require(result["last"] == "quota" and result["status"] == 429 and committed == [], "last='quota', status 429, no effect")
            require(lines_for(result["key"])[-1].get("outcome") == "quota", "The ledger records the attempt as quota")
        finally:
            stop(server, thread)
        server, thread = serve([fault("quota", retry_after=45), fault("ok")], answer=answer)
        try:
            result, clock, _ = call(server, rules)
            require(result["outcome"] == "paused" and result["pause"] == 45 and clock.sleeps == [], f"A quota error with Retry-After: 45 pauses for 45 s without sleeping inside call(), got pause {result['pause']!r} and waits {clock.sleeps}")
        finally:
            stop(server, thread)
        server, thread = serve([fault("400"), fault("ok")], answer=answer)
        try:
            result, clock, _ = call(server, rules)
            require(result["outcome"] == "rejected" and result["status"] == 400 and result["attempts"] == 1 and clock.sleeps == [], f"A 400 is the caller's mistake: rejected once, never retried; got {result['outcome']!r} after {result['attempts']} attempts")
            require(isinstance(result["error"], str) and "relay_mode" in result["error"], "The server's error message travels in result.error")
            return "insufficient_quota paused for the policy's quota_pause and for Retry-After; a 400 was rejected without retry."
        finally:
            stop(server, thread)
    check("Quota and billing errors are not retried but paused; other 4xx are rejected", quota)

    def side_effect():
        committed = []
        rules = policy(base_delay=0.2)
        server, thread = serve([fault("timeout"), fault("ok")], answer=answer, hold_ms=600)
        try:
            result, clock, _ = call(server, rules, effect=committed.append)
            require(result["outcome"] == "complete", f"timeout then success must end complete, got {result['outcome']!r}")
            keys = [item["key"] for item in server.requests]
            require(all(keys) and len(set(keys)) == 1, f"Every attempt of one call must carry the same Idempotency-Key header, saw {keys}")
            require(keys[0] == result["key"], "result.key is the key that was sent")
            require(sum(server.effects.values()) == 1, f"The relay reserved {sum(server.effects.values())} times for one logical call: a retry duplicated the side effect")
            require(len(committed) == 1 and committed[0] is result, f"The effect hook runs exactly once with the complete result, ran {len(committed)} times")
            explicit = f"reservation-{rng.randint(1000, 9999)}"
            inner, inner_thread = serve([fault("500"), fault("ok")], answer=answer)
            try:
                result, _, _ = call(inner, rules, key=explicit, effect=committed.append)
                require([item["key"] for item in inner.requests] == [explicit, explicit], f"An explicit idempotency key is sent verbatim on every attempt, saw {[item['key'] for item in inner.requests]}")
                require(result["key"] == explicit and len(committed) == 2, "The explicit key is reported and the effect ran once more")
                first, _, _ = call(inner, rules)
                second, _, _ = call(inner, rules)
                require(first["key"] != second["key"], "Two calls without an explicit key must not share one")
            finally:
                stop(inner, inner_thread)
            return "One reservation per logical call across a timeout and a 500; keys stable per call, distinct across calls."
        finally:
            stop(server, thread)
    check("A retry never duplicates a side effect", side_effect)

    def ledger():
        before = read_lines(ledger_path)
        ra = rng.choice([1.5, 2, 2.5])
        rules = policy(base_delay=0.3)
        server, thread = serve([fault("429", retry_after=ra), fault("500"), fault("ok")], answer=answer)
        try:
            result, clock, _ = call(server, rules)
            after = read_lines(ledger_path)
            require(after[:len(before)] == before, "Earlier ledger lines must stay unchanged: open the ledger in append mode")
            require(len(after) == len(before) + 3, f"Three attempts append three lines, found {len(after) - len(before)}")
            lines = [json.loads(line) for line in after[len(before):]]
            for line in lines:
                missing = {"key", "attempt", "outcome", "status", "retry_after", "wait", "elapsed"} - set(line)
                require(not missing, f"A ledger line is missing {sorted(missing)}")
                require(type(line["attempt"]) is int, "attempt is an integer")
                require(line["status"] is None or type(line["status"]) is int, "status is an integer or null")
                require(isinstance(line["wait"], (int, float)) and isinstance(line["elapsed"], (int, float)), "wait and elapsed are numbers of seconds")
            require([line["key"] for line in lines] == [result["key"]] * 3, "Every line carries the call's idempotency key")
            require([line["attempt"] for line in lines] == [1, 2, 3], f"Attempts are numbered from 1, got {[line['attempt'] for line in lines]}")
            require([line["outcome"] for line in lines] == ["rate_limited", "server_error", "complete"], f"Outcomes must be rate_limited, server_error, complete; got {[line['outcome'] for line in lines]}")
            require([line["status"] for line in lines] == [429, 500, 200], f"Statuses must be 429, 500, 200; got {[line['status'] for line in lines]}")
            require(lines[0]["retry_after"] == ra and lines[1]["retry_after"] is None and lines[2]["retry_after"] is None, f"retry_after records the header only where it was seen: {[line['retry_after'] for line in lines]}")
            waits = [line["wait"] for line in lines]
            require(abs(waits[0] - clock.waits[0]) < 1e-6 and abs(waits[1] - clock.waits[1]) < 1e-6 and waits[2] == 0, f"Each line's wait is the sleep that followed it ({[round(w, 3) for w in clock.waits]} and 0 for the last), got {waits}")
            elapsed = [line["elapsed"] for line in lines]
            require(elapsed[0] <= elapsed[1] <= elapsed[2] <= result["elapsed"] + 0.05, f"elapsed must not decrease and ends at the result's elapsed (50 ms tolerance): {elapsed} vs {result['elapsed']}")
            require(elapsed[1] >= waits[0] - EPS and elapsed[2] >= waits[0] + waits[1] - EPS, "elapsed comes from the injected clock, which advanced with every wait")
            return f"Three lines: 429 (Retry-After {ra}), 500, complete; waits {[round(w, 3) for w in waits]} s match the injected sleeps."
        finally:
            stop(server, thread)
    check("The ledger records every attempt", ledger)

    def transfer():
        ra = rng.randint(1, 3)
        order = [fault("500"), fault("429", retry_after=ra), fault("timeout"), fault("503"), fault("429")]
        rng.shuffle(order)
        rules = policy(base_delay=0.3, max_attempts=7, max_delay=6.0)
        server, thread = serve(order + [fault("ok")], answer=answer, hold_ms=600)
        try:
            started = time.perf_counter()
            result, clock, _ = call(server, rules)
            require(result["outcome"] == "complete" and result["content"] == answer, f"A different order of the same faults must still end complete, got {result['outcome']!r}")
            require(result["attempts"] == 6 and len(clock.waits) == 5, f"Six attempts and five waits expected, saw {result['attempts']} and {clock.waits}")
            expected = {"500": "server_error", "503": "server_error", "429": "rate_limited", "timeout": "timeout"}
            lines = lines_for(result["key"])
            require([line["outcome"] for line in lines] == [expected[item["kind"]] for item in order] + ["complete"], f"Ledger outcomes must follow the fault order {[item['kind'] for item in order]}, got {[line['outcome'] for line in lines]}")
            for index, (item, wait) in enumerate(zip(order, clock.waits), start=1):
                _, lower, upper = backoff_bounds(rules, index, retry_after=item.get("retry_after"))
                require(lower - EPS <= wait <= upper + EPS, f"Wait {index} after {item['kind']}{' with Retry-After ' + str(item['retry_after']) if item.get('retry_after') else ''} was {wait:.3f} s, allowed [{lower:.3f}, {upper:.3f}]")
            require(time.perf_counter() - started < 3.0, "The transfer run must not take real seconds")
            return f"Order {[item['kind'] for item in order]} then success: complete after 6 attempts, waits {[round(w, 3) for w in clock.waits]} s."
        finally:
            stop(server, thread)
    check("Transfer: a different failure order passes with the same wrapper", transfer)

    def reset_header():
        reset = rng.randint(3, 6)
        rules = policy(base_delay=0.1, max_delay=1.0)
        server, thread = serve([fault("429", reset=f"{reset}s"), fault("ok")], answer=answer)
        try:
            result, clock, _ = call(server, rules)
            require(result["outcome"] == "complete" and len(clock.waits) == 1, "429 then success must end complete after one wait")
            require(clock.waits[0] >= reset - EPS, f"x-ratelimit-reset-requests: {reset}s says the window resets in {reset} s; the wrapper waited {clock.waits[0]:.3f} s")
            require(clock.waits[0] <= reset + 1.25 + EPS, f"The wait {clock.waits[0]:.3f} s goes far beyond the reset")
            return f"Waited {clock.waits[0]:.3f} s on x-ratelimit-reset-requests: {reset}s without a Retry-After header."
        finally:
            stop(server, thread)
    check("bonus: x-ratelimit-reset-requests is honoured when Retry-After is absent", reset_header, optional=True)


try:
    trial()
except BaseException as error:  # noqa: BLE001 - every failure becomes a check
    if isinstance(error, (KeyboardInterrupt, SystemExit)):
        raise
    CHECKS.append({"name": "Load call wrapper", "passed": False, "detail": f"{type(error).__name__}: {error}"[:1500]})
print(json.dumps({"checks": CHECKS}))
sys.exit(0 if CHECKS and all(item["passed"] for item in CHECKS if not item.get("optional")) else 1)
