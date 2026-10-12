"""Metered LLM client checks for the Price mission; run outside the learner workspace.

The recording adapter below is a labeled test tool: it speaks the chat completions contract and
answers with deterministic numbers. The only live evaluation is the final call to the endpoint
the learner configured in llm.json, reconciled against Verify's own direct request.
"""
import importlib.util
import json
import math
import os
import socketserver
import sys
import threading
import time
import urllib.error
import urllib.request
from fractions import Fraction
from http.server import BaseHTTPRequestHandler, HTTPServer

MISSION, WORKSPACE = sys.argv[1:3]
CHECKS = []
LIVE_TIMEOUT = 15


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def check(name, operation, optional=False):
    # An optional check is the hidden bonus of a mission: it can only add, it never fails the run.
    flag = {"optional": True} if optional else {}
    try:
        detail = operation()
        CHECKS.append({"name": name, "passed": True, "detail": detail or "Recording adapter requests and the returned records verified.", **flag})
    except Exception as error:
        CHECKS.append({"name": name, "passed": False, "detail": f"{type(error).__name__}: {error}"[:1500], **flag})


class EnvironmentBlocked(Exception):
    pass


class Adapter(socketserver.ThreadingMixIn, HTTPServer):
    """OpenAI-compatible loopback server with deterministic usage; records every request body."""
    daemon_threads = True

    def __init__(self, *, tokenizer="words", generated=7, delay_ms=0, cached=0):
        super().__init__(("127.0.0.1", 0), AdapterHandler)
        self.tokenizer, self.generated, self.delay_ms, self.cached = tokenizer, generated, delay_ms, cached
        self.requests = []
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

    def count_prompt(self, messages):
        text = "".join(str(message.get("content", "")) for message in messages)
        if self.tokenizer == "words":
            return len(text.split()) + 4 * len(messages) + 3
        return math.ceil(len(text.encode("utf-8")) / 3) + 5


class AdapterHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

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
        with server.lock:
            server.requests.append({"path": self.path, "headers": dict(self.headers), "body": body})
        if not self.path.endswith("/chat/completions"):
            self.reply(404, {"error": {"message": "unknown route", "type": "invalid_request_error"}})
            return
        if server.delay_ms:
            time.sleep(server.delay_ms / 1000)
        limit = body.get("max_tokens")
        produced = server.generated if not isinstance(limit, int) else min(limit, server.generated)
        finish = "length" if isinstance(limit, int) and server.generated > limit else "stop"
        prompt_tokens = server.count_prompt(body["messages"])
        self.reply(200, {
            "id": f"chatcmpl-adapter-{len(server.requests)}", "object": "chat.completion", "created": int(time.time()), "model": body["model"],
            "choices": [{"index": 0, "message": {"role": "assistant", "content": " ".join(["word"] * produced)}, "finish_reason": finish}],
            "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": produced, "total_tokens": prompt_tokens + produced,
                      "prompt_tokens_details": {"cached_tokens": min(server.cached, prompt_tokens)}},
            "system_fingerprint": "fp_recording_adapter",
        })


def serve(**options):
    server = Adapter(**options)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
    thread.start()
    return server, thread


def stop(server, thread):
    server.shutdown()
    server.server_close()
    thread.join(timeout=1)


MANIFEST = {
    "overhead_tokens": 29,
    "models": {
        "relay-small": {"context_window": 2048, "input_price_per_million": 0.21, "output_price_per_million": 0.84, "cached_input_price_per_million": 0.105},
        "relay-large": {"context_window": 300, "input_price_per_million": 3.7, "output_price_per_million": 11.1, "cached_input_price_per_million": 1.85},
    },
}
REQUIRED_KEYS = {"model", "max_tokens", "temperature", "input_tokens", "output_tokens", "cached_tokens", "latency_ms", "finish_reason", "cost", "content"}


def expected_cost(model, input_tokens, output_tokens, cached_tokens=0, manifest=MANIFEST):
    prices = manifest["models"][model]
    cached_price = prices.get("cached_input_price_per_million", prices["input_price_per_million"])
    total = Fraction(input_tokens - cached_tokens) * Fraction(str(prices["input_price_per_million"]))
    total += Fraction(cached_tokens) * Fraction(str(cached_price))
    total += Fraction(output_tokens) * Fraction(str(prices["output_price_per_million"]))
    return total / 1_000_000


def read_log(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as file:
        return file.read().splitlines()


def trial():
    require(MISSION == "price", "Unknown mission")
    sys.path.insert(0, WORKSPACE)
    spec = importlib.util.spec_from_file_location("candidate_price", os.path.join(WORKSPACE, "client.py"))
    if spec is None or spec.loader is None:
        raise ImportError("Cannot load client.py")
    candidate = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = candidate
    spec.loader.exec_module(candidate)
    require(callable(getattr(candidate, "ask", None)), "client.py must define ask(...)")
    require(isinstance(getattr(candidate, "WindowError", None), type) and issubclass(candidate.WindowError, BaseException), "client.py must define the WindowError exception class")
    log_path = os.path.join(WORKSPACE, ".verify-usage.log")
    if os.path.exists(log_path):
        os.remove(log_path)

    def call(server, prompt, *, model="relay-small", max_tokens=64, temperature=0.0, manifest=MANIFEST, log=log_path):
        before = len(server.requests)
        started = time.perf_counter()
        record = candidate.ask(prompt, base_url=server.base_url, model=model, max_tokens=max_tokens, manifest=manifest, log_path=log, temperature=temperature)
        waited_ms = (time.perf_counter() - started) * 1000
        require(isinstance(record, dict), "ask must return a dict record")
        missing = REQUIRED_KEYS - set(record)
        require(not missing, f"Record is missing keys: {sorted(missing)}")
        require(len(server.requests) - before == 1, f"Expected exactly one request to the adapter, saw {len(server.requests) - before}")
        request = server.requests[-1]["body"]
        for key in ("input_tokens", "output_tokens", "cached_tokens", "latency_ms", "max_tokens"):
            require(type(record[key]) is int, f"{key} must be a JSON integer, got {record[key]!r}")
        require(isinstance(record["cost"], (int, float)) and not isinstance(record["cost"], bool) and math.isfinite(record["cost"]), "cost must be a finite number")
        require(record["latency_ms"] >= 0, "latency_ms cannot be negative")
        return record, request, waited_ms

    def parameters():
        server, thread = serve(tokenizer="words", generated=9)
        try:
            prompt = "List three things an operator should check before reserving stock."
            record, request, _ = call(server, prompt, max_tokens=40, temperature=0.3)
            require(request.get("model") == "relay-small" and record["model"] == "relay-small", f"Model sent {request.get('model')!r}, logged {record['model']!r}")
            require(request.get("max_tokens") == 40 and record["max_tokens"] == 40, f"max_tokens sent {request.get('max_tokens')!r}, logged {record['max_tokens']!r}")
            require(isinstance(request.get("temperature"), (int, float)) and abs(request["temperature"] - 0.3) < 1e-9, f"temperature sent {request.get('temperature')!r}, expected 0.3")
            require(abs(float(record["temperature"]) - 0.3) < 1e-9, f"temperature logged {record['temperature']!r}")
            contents = [message.get("content") for message in request["messages"] if message.get("role") == "user"]
            require(any(prompt in str(content) for content in contents), "The prompt must be sent as a user message")
            require(request.get("stream") in (None, False), "Streaming is out of scope for this mission; do not send stream: true")
            require(record["content"] == "word " * 8 + "word", "content must be the first choice's message text")
            lines = read_log(log_path)
            require(len(lines) == 1, f"Expected one log line after one call, found {len(lines)}")
            require(json.loads(lines[-1]) == json.loads(json.dumps(record)), "The appended log line must equal the returned record")
        finally:
            stop(server, thread)
    check("Recording adapter: the parameters sent are the parameters logged", parameters)

    def usage():
        server, thread = serve(tokenizer="words", generated=9)
        try:
            prompt = "Summarize the overnight incident report for the morning shift in two sentences."
            cut, request, _ = call(server, prompt, max_tokens=5)
            require(cut["finish_reason"] == "length", f"finish_reason must be the response value 'length', got {cut['finish_reason']!r}")
            require(cut["output_tokens"] == 5, f"output_tokens must be usage.completion_tokens (5), got {cut['output_tokens']!r}")
            full, _, _ = call(server, prompt, max_tokens=50)
            require(full["finish_reason"] == "stop", f"finish_reason must be 'stop' when the answer fits, got {full['finish_reason']!r}")
            require(full["output_tokens"] == 9, f"output_tokens must be usage.completion_tokens (9), got {full['output_tokens']!r}")
            expected_input = server.count_prompt(request["messages"])
            require(cut["input_tokens"] == expected_input and full["input_tokens"] == expected_input, f"input_tokens must be usage.prompt_tokens ({expected_input}), got {cut['input_tokens']!r} and {full['input_tokens']!r}")
            require(cut["input_tokens"] != round(len(prompt) / 4), "The adapter counts tokens differently from len(prompt)/4 on purpose")
        finally:
            stop(server, thread)
    check("Usage and finish reason are taken from the response", usage)

    def pricing():
        small, thread_small = serve(tokenizer="words", generated=6)
        large, thread_large = serve(tokenizer="bytes", generated=6)
        try:
            prompt = "Проверь остаток фильтров на складе и предложи, сколько заказать."
            record, _, _ = call(small, prompt, model="relay-small", max_tokens=30)
            wanted = expected_cost("relay-small", record["input_tokens"], record["output_tokens"])
            require(abs(Fraction(str(record["cost"])) - wanted) <= Fraction(1, 10**9), f"relay-small cost {record['cost']!r}, expected {float(wanted)!r} from the manifest prices")
            record, _, _ = call(large, prompt, model="relay-large", max_tokens=30)
            wanted = expected_cost("relay-large", record["input_tokens"], record["output_tokens"])
            require(abs(Fraction(str(record["cost"])) - wanted) <= Fraction(1, 10**9), f"relay-large cost {record['cost']!r}, expected {float(wanted)!r} from the manifest prices")
            require(record["input_tokens"] == large.count_prompt([{"content": prompt}]), "input_tokens must come from the response of the model that was called")
            return "Costs recomputed from the manifest for two models with different tokenizers and prices."
        finally:
            stop(small, thread_small)
            stop(large, thread_large)
    check("Cost follows the price table of the model that was called", pricing)

    def latency():
        server, thread = serve(delay_ms=150)
        try:
            record, _, waited_ms = call(server, "Is the relay healthy?", max_tokens=12)
            require(record["latency_ms"] >= 150, f"latency_ms {record['latency_ms']} is below the 150 ms the adapter took")
            require(record["latency_ms"] <= math.ceil(waited_ms) + 1, f"latency_ms {record['latency_ms']} exceeds the {waited_ms:.0f} ms the caller waited")
            return f"Measured {record['latency_ms']} ms around a 150 ms adapter delay."
        finally:
            stop(server, thread)
    check("Latency is measured around the request", latency)

    def window():
        server, thread = serve()
        try:
            # relay-large: window 300, overhead 29, max_tokens 40 → prompt bytes ≤ 231 are sent, 232 are refused.
            lines_before = read_log(log_path)
            requests_before = len(server.requests)
            refused = False
            try:
                candidate.ask("x" * 232, base_url=server.base_url, model="relay-large", max_tokens=40, manifest=MANIFEST, log_path=log_path, temperature=0.0)
            except candidate.WindowError:
                refused = True
            require(refused, "A prompt whose byte bound plus max_tokens exceeds the window must raise WindowError")
            require(len(server.requests) == requests_before, "The over-window prompt must be refused before any request is sent")
            require(read_log(log_path) == lines_before, "A refused call must not append a log line")
            unicode_prompt = "ё" * 116  # 232 UTF-8 bytes, 116 characters: the bound counts bytes
            refused = False
            try:
                candidate.ask(unicode_prompt, base_url=server.base_url, model="relay-large", max_tokens=40, manifest=MANIFEST, log_path=log_path, temperature=0.0)
            except candidate.WindowError:
                refused = True
            require(refused and len(server.requests) == requests_before, "The bound counts UTF-8 bytes, not characters")
            record, _, _ = call(server, "y" * 231, model="relay-large", max_tokens=40)
            require(record["finish_reason"] == "stop", "A prompt exactly at the bound is sent normally")
            return "232-byte prompts refused without a request; a 231-byte prompt sent."
        finally:
            stop(server, thread)
    check("A prompt over the context window is refused before sending", window)

    def journal():
        server, thread = serve()
        try:
            if os.path.exists(log_path):
                os.remove(log_path)
            prompts = ["first", "second entry", "third entry here"]
            records = [call(server, prompt, max_tokens=8)[0] for prompt in prompts]
            lines = read_log(log_path)
            require(len(lines) == 3, f"Three calls must append three lines, found {len(lines)}")
            for line, record in zip(lines, records):
                parsed = json.loads(line)
                require(parsed == json.loads(json.dumps(record)), "Each line must be the JSON of the record returned for that call")
            with open(log_path, "rb") as file:
                require(file.read().endswith(b"\n"), "Every line ends with a newline")
            return "Three calls appended three JSON lines in order."
        finally:
            stop(server, thread)
    check("Every call appends one JSON line to the log", journal)

    def cached():
        server, thread = serve(tokenizer="words", generated=4, cached=20)
        try:
            prompt = " ".join(["supply"] * 40)
            record, _, _ = call(server, prompt, model="relay-small", max_tokens=16)
            require(record["cached_tokens"] == 20, f"cached_tokens must be usage.prompt_tokens_details.cached_tokens (20), got {record['cached_tokens']!r}")
            wanted = expected_cost("relay-small", record["input_tokens"], record["output_tokens"], cached_tokens=20)
            require(abs(Fraction(str(record["cost"])) - wanted) <= Fraction(1, 10**9), f"Cached prompt tokens are priced at the cached rate: cost {record['cost']!r}, expected {float(wanted)!r}")
            return "Cached prompt tokens were accounted and priced separately."
        finally:
            stop(server, thread)
    check("bonus: cached prompt tokens are accounted and priced separately", cached, optional=True)

    def live():
        config_path = os.path.join(WORKSPACE, "llm.json")
        try:
            with open(config_path, "r", encoding="utf-8") as file:
                config = json.load(file)
        except Exception as error:
            raise EnvironmentBlocked(f"llm.json could not be read ({type(error).__name__}: {error}). It holds base_url and model only; keys stay in the environment.")
        base_url, model = str(config.get("base_url") or ""), str(config.get("model") or "")
        if not base_url or not model:
            raise EnvironmentBlocked("Set base_url and model in llm.json to your own endpoint (for Ollama: http://127.0.0.1:11434/v1 and a name from `ollama list`), then verify again.")
        manifest = {"overhead_tokens": MANIFEST["overhead_tokens"], "models": {model: {
            "context_window": int(config.get("context_window") or 8192),
            "input_price_per_million": config.get("input_price_per_million") or 0,
            "output_price_per_million": config.get("output_price_per_million") or 0,
            "cached_input_price_per_million": config.get("cached_input_price_per_million") or 0,
        }}}
        prompt = "Reply with the single word OK."
        body = json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": 8, "temperature": 0}).encode("utf-8")
        request = urllib.request.Request(base_url.rstrip("/") + "/chat/completions", data=body, headers={"Content-Type": "application/json"}, method="POST")
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=LIVE_TIMEOUT) as response:
                direct = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            raise EnvironmentBlocked(f"{base_url} answered HTTP {error.code} for model {model!r}: {error.read(300).decode('utf-8', 'replace')}")
        except Exception as error:
            raise EnvironmentBlocked(f"{base_url} did not answer within {LIVE_TIMEOUT} s ({type(error).__name__}: {error}). Start or warm up the model with demo.py, then verify again.")
        direct_usage = direct.get("usage") or {}
        require(type(direct_usage.get("prompt_tokens")) is int and type(direct_usage.get("completion_tokens")) is int, f"The endpoint did not return a usage object with integer counts: {direct_usage!r}")
        live_log = os.path.join(WORKSPACE, ".verify-live.log")
        if os.path.exists(live_log):
            os.remove(live_log)
        started = time.perf_counter()
        record = candidate.ask(prompt, base_url=base_url, model=model, max_tokens=8, manifest=manifest, log_path=live_log, temperature=0.0)
        waited_ms = (time.perf_counter() - started) * 1000
        require(isinstance(record, dict) and not (REQUIRED_KEYS - set(record)), "The live record must carry every contract key")
        require(record["input_tokens"] == direct_usage["prompt_tokens"], f"input_tokens {record['input_tokens']} differ from the endpoint's prompt_tokens {direct_usage['prompt_tokens']} for the same prompt and model")
        require(0 < record["output_tokens"] <= 8, f"output_tokens {record['output_tokens']} must be within max_tokens 8")
        require(record["finish_reason"] in ("stop", "length"), f"finish_reason {record['finish_reason']!r} must be the endpoint's value")
        require(0 <= record["latency_ms"] <= math.ceil(waited_ms) + 1, f"latency_ms {record['latency_ms']} exceeds the {waited_ms:.0f} ms waited")
        wanted = expected_cost(model, record["input_tokens"], record["output_tokens"], cached_tokens=record["cached_tokens"], manifest=manifest)
        require(abs(Fraction(str(record["cost"])) - wanted) <= Fraction(1, 10**9), f"Live cost {record['cost']!r} does not follow the llm.json prices")
        require(len(read_log(live_log)) == 1, "The live call must append exactly one log line")
        return f"Live: {model} at {base_url}; {record['input_tokens']} prompt and {record['output_tokens']} completion tokens, finish {record['finish_reason']}, {record['latency_ms']} ms. Direct request agreed on prompt tokens."

    try:
        CHECKS.append({"name": "Live call to the configured endpoint reconciles with its usage", "passed": True, "detail": live()})
    except EnvironmentBlocked as blocked:
        CHECKS.append({"name": "Environment blocked", "passed": False, "detail": str(blocked)[:1500]})
    except Exception as error:
        CHECKS.append({"name": "Live call to the configured endpoint reconciles with its usage", "passed": False, "detail": f"{type(error).__name__}: {error}"[:1500]})


try:
    trial()
except Exception as error:
    CHECKS.append({"name": "Load metered client", "passed": False, "detail": f"{type(error).__name__}: {error}"[:1500]})
print(json.dumps({"checks": CHECKS}))
sys.exit(0 if CHECKS and all(item["passed"] for item in CHECKS if not item.get("optional")) else 1)
