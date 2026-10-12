"""Repeated-sampling experiment checks for the Sampling mission; run outside the learner workspace.

The scripted adapter below is a labeled test tool: it speaks the chat completions contract and serves
labels from a distribution Verify chose, honoring, ignoring or outliving a seed on purpose. The only live
evaluation is the small experiment against the endpoint the learner configured in llm.json, and its
numbers are reported as measurements.
"""
import importlib.util
import json
import math
import os
import random
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
LIVE_BUDGET = 20
TOLERANCE = Fraction(1, 10**9)
PROMPT = ("Classify the supply request below as exactly one of: urgent, routine, reject. Reply with the single word.\n\n"
          "Request: the relay's spare power cell failed overnight, the backup holds for six hours, send a replacement cell.")
RECORD_KEYS = {"setting", "run", "index", "model", "seed", "temperature", "top_p", "content", "finish_reason", "usage", "system_fingerprint"}
STAT_KEYS = {"samples", "seed", "temperature", "distinct", "majority", "majority_share", "agreement", "entropy_bits", "reproducible", "finish_reasons"}
FRESH = random.Random()


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def check(name, operation, optional=False):
    # An optional check is the hidden bonus of a mission: it can only add, it never fails the run.
    flag = {"optional": True} if optional else {}
    try:
        detail = operation()
        CHECKS.append({"name": name, "passed": True, "detail": detail or "Scripted adapter requests and the raw file verified.", **flag})
    except Exception as error:
        CHECKS.append({"name": name, "passed": False, "detail": f"{type(error).__name__}: {error}"[:1500], **flag})


class EnvironmentBlocked(Exception):
    pass


def setting_key(body):
    seed = body.get("seed")
    return (float(body.get("temperature", 1.0)), body.get("top_p"), seed)


class Adapter(socketserver.ThreadingMixIn, HTTPServer):
    """OpenAI-compatible loopback server serving chosen labels; records every request and what it served.

    mode "honor": the same seed always yields the same label. mode "ignore": the seed changes nothing and the
    first request after epoch_length for a key is forced to differ from that key's first answer. mode "epoch":
    like honor until epoch_length requests for a seeded key, then the label and fingerprint change, as a
    redeployed server would. temperature 0 is greedy (labels[0]) unless drift is on and requests overlap, when
    every other overlapping request answers labels[-1] as a batch-dependent server would.
    """
    daemon_threads = True

    def __init__(self, *, labels, mode="honor", fingerprint=None, delay_ms=0, drift=False, epoch_length=None, padded=False):
        super().__init__(("127.0.0.1", 0), AdapterHandler)
        self.labels, self.mode, self.fingerprint, self.delay_ms, self.drift, self.epoch_length = list(labels), mode, fingerprint, delay_ms, drift, epoch_length
        self.padded = padded  # serve "label\n" like Ollama does, so stored content must stay verbatim
        self.rng = random.Random(FRESH.random())
        self.prompt_base = FRESH.randint(40, 90)
        self.requests = []
        self.served = {}
        self.inflight = 0
        self.max_inflight = 0
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

    def choose(self, body, key, count, overlapped):
        temperature, _, seed = key
        fingerprint = self.fingerprint
        if self.drift and overlapped and count % 2 == 1:
            # Batch composition changes the greedy answer on every other overlapping request.
            return self.labels[-1], fingerprint
        if self.mode == "epoch" and seed is not None and self.epoch_length is not None and count >= self.epoch_length:
            first = self.served[key][0]["content"].strip() if self.served[key] else self.labels[0]
            alternative = next(label for label in self.labels if label != first)
            return alternative, (fingerprint + "-redeployed") if fingerprint else None
        if temperature == 0:
            return self.labels[0], fingerprint
        if seed is not None and self.mode in ("honor", "epoch"):
            return self.labels[random.Random(f"{seed}:{temperature}").randrange(len(self.labels))], fingerprint
        if self.mode == "ignore" and seed is not None and self.epoch_length is not None and count == self.epoch_length:
            first = self.served[key][0]["content"].strip()
            return next(label for label in self.labels if label != first), fingerprint
        weights = [3] + [1] * (len(self.labels) - 1)
        return self.rng.choices(self.labels, weights=weights)[0], fingerprint


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
            require(body.get("seed") is None or type(body["seed"]) is int, "seed must be an integer when present")
        except Exception as error:
            self.reply(400, {"error": {"message": f"invalid request: {error}", "type": "invalid_request_error"}})
            return
        if not self.path.endswith("/chat/completions"):
            self.reply(404, {"error": {"message": "unknown route", "type": "invalid_request_error"}})
            return
        with server.lock:
            server.inflight += 1
            server.max_inflight = max(server.max_inflight, server.inflight)
        try:
            if server.delay_ms:
                time.sleep(server.delay_ms / 1000)
            with server.lock:
                overlapped = server.inflight > 1
                key = setting_key(body)
                history = server.served.setdefault(key, [])
                content, fingerprint = server.choose(body, key, len(history), overlapped)
                if server.padded:
                    content += "\n"
                limit = body.get("max_tokens")
                finish = "length" if isinstance(limit, int) and limit < 2 else "stop"
                usage = {"prompt_tokens": server.prompt_base + len(history) % 3, "completion_tokens": 1 + len(history) % 2}
                usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]
                # The served position rides inside usage so Verify can match a stored record to the answer it got, whatever the write order.
                usage["served_position"] = len(history)
                entry = {"content": content, "finish_reason": finish, "usage": usage, "system_fingerprint": fingerprint, "overlapped": overlapped}
                history.append(entry)
                server.requests.append({"path": self.path, "headers": dict(self.headers), "body": body, "key": key})
        finally:
            with server.lock:
                server.inflight -= 1
        payload = {
            "id": f"chatcmpl-adapter-{len(server.requests)}", "object": "chat.completion", "created": int(time.time()), "model": body["model"],
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": finish}],
            "usage": usage,
        }
        if fingerprint is not None:
            payload["system_fingerprint"] = fingerprint
        self.reply(200, payload)


def serve(**options):
    server = Adapter(**options)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
    thread.start()
    return server, thread


def stop(server, thread):
    server.shutdown()
    server.server_close()
    thread.join(timeout=1)


def expected_stats(contents):
    """Hand recomputation of the published formulas with exact arithmetic."""
    contents = [content.strip() for content in contents]
    n = len(contents)
    counts = {}
    for content in contents:
        counts[content] = counts.get(content, 0) + 1
    top = max(counts.values())
    majority = min(label for label, count in counts.items() if count == top)
    agreement = Fraction(sum(count * (count - 1) for count in counts.values()), n * (n - 1)) if n > 1 else Fraction(1)
    entropy = -sum((Fraction(count, n)) * math.log2(Fraction(count, n)) for count in counts.values())
    return {"samples": n, "distinct": len(counts), "majority": majority, "majority_share": Fraction(top, n), "agreement": agreement, "entropy_bits": entropy}


def close(value, wanted, what):
    require(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value), f"{what} must be a finite number, got {value!r}")
    require(abs(Fraction(str(value)) - Fraction(wanted)) <= TOLERANCE, f"{what} {value!r} differs from the recomputed {float(wanted)!r}")


def compare_stats(name, stats, contents):
    require(isinstance(stats, dict), f"report[{name!r}] must be a dict")
    missing = STAT_KEYS - set(stats)
    require(not missing, f"report[{name!r}] is missing keys: {sorted(missing)}")
    wanted = expected_stats(contents)
    require(stats["samples"] == wanted["samples"], f"report[{name!r}].samples {stats['samples']!r}, expected {wanted['samples']} first-run records")
    require(stats["distinct"] == wanted["distinct"], f"report[{name!r}].distinct {stats['distinct']!r}, expected {wanted['distinct']}")
    require(stats["majority"] == wanted["majority"], f"report[{name!r}].majority {stats['majority']!r}, expected {wanted['majority']!r} (ties break to the lexicographically smallest answer)")
    close(stats["majority_share"], wanted["majority_share"], f"report[{name!r}].majority_share")
    close(stats["agreement"], wanted["agreement"], f"report[{name!r}].agreement")
    close(stats["entropy_bits"], wanted["entropy_bits"], f"report[{name!r}].entropy_bits")


def read_raw(path):
    require(os.path.exists(path), f"{os.path.basename(path)} was not written")
    records = []
    with open(path, "r", encoding="utf-8") as file:
        for number, line in enumerate(file.read().splitlines(), 1):
            try:
                record = json.loads(line)
            except Exception as error:
                raise AssertionError(f"line {number} of the raw file is not JSON: {error}")
            require(isinstance(record, dict), f"line {number} of the raw file must be an object")
            missing = RECORD_KEYS - set(record)
            require(not missing, f"line {number} of the raw file is missing keys: {sorted(missing)}")
            records.append(record)
    return records


def grouped(records):
    groups = {}
    for record in records:
        require(record["run"] in ("first", "rerun"), f"run must be 'first' or 'rerun', got {record['run']!r}")
        groups.setdefault((record["setting"], record["run"]), []).append(record)
    return groups


def ordered_contents(records, name, run, samples):
    bucket = sorted((record for record in records if record["setting"] == name and record["run"] == run), key=lambda record: record["index"])
    indices = [record["index"] for record in bucket]
    require(indices == list(range(samples)), f"setting {name!r} run {run!r}: indices {indices} must be exactly 0..{samples - 1}")
    return [record["content"] for record in bucket]


def write_raw(path, rows):
    with open(path, "w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row) + "\n")


def trial():
    require(MISSION == "sampling", "Unknown mission")
    sys.path.insert(0, WORKSPACE)
    spec = importlib.util.spec_from_file_location("candidate_sampling", os.path.join(WORKSPACE, "experiment.py"))
    if spec is None or spec.loader is None:
        raise ImportError("Cannot load experiment.py")
    candidate = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = candidate
    spec.loader.exec_module(candidate)
    require(callable(getattr(candidate, "run_experiment", None)), "experiment.py must define run_experiment(...)")
    require(callable(getattr(candidate, "report", None)), "experiment.py must define report(raw_path)")
    raw_path = os.path.join(WORKSPACE, ".verify-raw.jsonl")
    labels = FRESH.sample(["urgent", "routine", "reject", "unclear", "escalate"], 3)
    samples = FRESH.randint(4, 7)
    seed_a, seed_b = FRESH.randint(1000, 9999), FRESH.randint(10000, 99999)
    model = f"relay-{FRESH.randint(100, 999)}"
    settings = [
        {"name": "greedy-seeded", "temperature": 0.0, "seed": seed_a},
        {"name": "sampled-seeded", "temperature": 0.9, "top_p": 0.95, "seed": seed_b},
        {"name": "sampled", "temperature": 1.0},
    ]

    def run(server, *, settings=settings, samples=samples, out_path=raw_path, max_tokens=4, **extra):
        result = candidate.run_experiment(settings, base_url=server.base_url, model=model, prompt=PROMPT, samples=samples, max_tokens=max_tokens, out_path=out_path, **extra)
        require(isinstance(result, dict), "run_experiment must return the report dict")
        return result

    def counts():
        server, thread = serve(labels=labels, fingerprint="fp_adapter_" + str(FRESH.randint(100, 999)))
        try:
            result = run(server)
            expected = {("greedy-seeded", "first"): samples, ("greedy-seeded", "rerun"): samples, ("sampled-seeded", "first"): samples, ("sampled-seeded", "rerun"): samples, ("sampled", "first"): samples}
            groups = grouped(read_raw(raw_path))
            seen = {key: len(value) for key, value in groups.items()}
            require(seen == expected, f"Raw records per (setting, run): {seen}, expected {expected} for samples={samples}")
            bodies = [item["body"] for item in server.requests]
            require(len(bodies) == 5 * samples, f"The adapter saw {len(bodies)} requests, expected {5 * samples}: {samples} per setting plus a rerun of each seeded setting")
            per_key = {key: len(value) for key, value in server.served.items()}
            require(per_key.get((0.0, None, seed_a)) == 2 * samples, f"greedy-seeded must be requested {2 * samples} times with temperature 0 and seed {seed_a}; per-setting counts seen: {per_key}")
            require(per_key.get((0.9, 0.95, seed_b)) == 2 * samples, f"sampled-seeded must be requested {2 * samples} times with temperature 0.9, top_p 0.95 and seed {seed_b}; seen: {per_key}")
            require(per_key.get((1.0, None, None)) == samples, f"sampled must be requested {samples} times with temperature 1.0 and no seed or top_p key; seen: {per_key}")
            for body in bodies:
                require(body.get("model") == model and body.get("max_tokens") == 4, f"Every request carries model {model!r} and max_tokens 4, got {body.get('model')!r}, {body.get('max_tokens')!r}")
                require(body.get("stream") in (None, False), "Streaming is out of scope; do not send stream: true")
                contents = [message.get("content") for message in body["messages"] if message.get("role") == "user"]
                require(any(PROMPT in str(content) for content in contents), "The prompt must be sent unchanged as a user message")
            for record in groups[("sampled", "first")]:
                require(record["seed"] is None and record["top_p"] is None, "A setting without seed or top_p records null for them")
                require(record["model"] == model, f"record.model must be {model!r}")
            require(all(record["seed"] == seed_a and record["temperature"] == 0.0 for record in groups[("greedy-seeded", "first")]), "greedy-seeded records carry seed and temperature of the setting")
            second = FRESH.randint(2, 3)
            run(server, samples=second)
            groups = grouped(read_raw(raw_path))
            require(len(groups[("sampled", "first")]) == second, f"A second run to the same out_path must replace the file: expected {second} first-run records for 'sampled', found {len(groups[('sampled', 'first')])}")
            return f"{samples} samples per setting plus a {samples}-sample rerun of each seeded setting; {len(bodies)} requests carried the setting's temperature, top_p and seed."
        finally:
            stop(server, thread)
    check("Every setting is sampled the declared number of times", counts)

    def verbatim():
        tag = "fp_adapter_" + str(FRESH.randint(100, 999))
        server, thread = serve(labels=labels, fingerprint=tag, padded=True)
        quiet, quiet_thread = serve(labels=labels, fingerprint=None)
        try:
            run(server)
            records = read_raw(raw_path)
            for name, key in (("greedy-seeded", (0.0, None, seed_a)), ("sampled-seeded", (0.9, 0.95, seed_b)), ("sampled", (1.0, None, None))):
                history = server.served[key]
                matched = []
                for record in (record for record in records if record["setting"] == name):
                    where = f"{name} {record['run']} sample {record['index']}"
                    usage = record["usage"]
                    require(isinstance(usage, dict) and usage.get("served_position") in range(len(history)), f"{where}: usage must be the response's usage object (the adapter's carries prompt_tokens, completion_tokens, total_tokens and served_position), got {usage!r}")
                    served = history[usage["served_position"]]
                    matched.append(usage["served_position"])
                    require(record["content"] == served["content"], f"{where}: content {record['content']!r} is not what the adapter served for that request ({served['content']!r})")
                    require(record["finish_reason"] == served["finish_reason"], f"{where}: finish_reason must be the response value {served['finish_reason']!r}, got {record['finish_reason']!r}")
                    require(usage == served["usage"], f"{where}: usage must equal the response's usage object {served['usage']}, got {usage!r}")
                    require(record["system_fingerprint"] == tag, f"{where}: system_fingerprint must be the response value {tag!r}, got {record['system_fingerprint']!r}")
                require(sorted(matched) == list(range(len(history))), f"{name}: every answer the adapter served must be stored exactly once; served positions found {sorted(matched)}")
            run(quiet, settings=settings[2:], samples=3)
            for record in read_raw(raw_path):
                require(record["system_fingerprint"] is None, f"When the response has no system_fingerprint the record stores null, got {record['system_fingerprint']!r}")
            return "Content (with its trailing newline), finish_reason, usage and system_fingerprint stored verbatim; null fingerprint when the server sends none."
        finally:
            stop(server, thread)
            stop(quiet, quiet_thread)
    check("The raw file holds every output verbatim", verbatim)

    def recomputed():
        hand_path = os.path.join(WORKSPACE, ".verify-hand.jsonl")
        tie_a, tie_b = sorted(FRESH.sample(["alpha", "beta", "gamma", "delta"], 2))
        skew = FRESH.sample(["north", "south", "east", "west"], 3)
        n = FRESH.choice([6, 8])
        tie_contents = [tie_b, tie_a] * (n // 2)
        skew_contents = [skew[0]] * (n - 2) + [skew[1], skew[2]]
        rows = []
        for position, content in enumerate(tie_contents):
            rows.append({"setting": "tie", "run": "first", "index": position, "model": model, "seed": 11, "temperature": 0.7, "top_p": None, "content": f"  {content}\n", "finish_reason": "stop", "usage": {"prompt_tokens": 5, "completion_tokens": 1, "total_tokens": 6}, "system_fingerprint": None})
        matched = FRESH.random() < 0.5
        for position, content in enumerate(tie_contents if matched else list(reversed(tie_contents))):
            rows.append({"setting": "tie", "run": "rerun", "index": position, "model": model, "seed": 11, "temperature": 0.7, "top_p": None, "content": content, "finish_reason": "stop", "usage": {"prompt_tokens": 5, "completion_tokens": 1, "total_tokens": 6}, "system_fingerprint": None})
        for position, content in enumerate(skew_contents):
            rows.append({"setting": "skew", "run": "first", "index": position, "model": model, "seed": None, "temperature": 1.0, "top_p": 0.9, "content": content, "finish_reason": "length" if position == 0 else "stop", "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7}, "system_fingerprint": "fp_hand"})
        FRESH.shuffle(rows)
        write_raw(hand_path, rows)
        result = candidate.report(hand_path)
        require(isinstance(result, dict) and set(result) == {"tie", "skew"}, f"report(hand-written raw file) must contain exactly {{'tie', 'skew'}}, got {list(result) if isinstance(result, dict) else type(result).__name__}; is report reading raw_path or remembering a previous run?")
        compare_stats("tie", result["tie"], [content.strip() for content in tie_contents])
        compare_stats("skew", result["skew"], skew_contents)
        require(result["tie"]["majority"] == tie_a, f"A tie between {tie_a!r} and {tie_b!r} breaks to the lexicographically smallest answer, got {result['tie']['majority']!r}")
        require(result["tie"]["seed"] == 11 and result["skew"]["seed"] is None, "report.seed is the setting's seed or null")
        close(result["tie"]["temperature"], Fraction("0.7"), "report['tie'].temperature")
        require(result["skew"]["finish_reasons"] == {"length": 1, "stop": n - 1}, f"finish_reasons counts first-run records by finish_reason, got {result['skew']['finish_reasons']!r}")
        require(result["tie"]["reproducible"] is matched, f"report['tie'].reproducible must compare stripped answers index by index with the rerun ({'equal' if matched else 'different'} here), got {result['tie']['reproducible']!r}")
        require(result["skew"]["reproducible"] is None, f"A setting without a seed makes no claim: reproducible must be null, got {result['skew']['reproducible']!r}")
        server, thread = serve(labels=labels)
        try:
            returned = run(server)
            from_file = candidate.report(raw_path)
            require(json.loads(json.dumps(returned)) == json.loads(json.dumps(from_file)), "run_experiment must return exactly what report(out_path) recomputes")
            for name, key in (("greedy-seeded", (0.0, None, seed_a)), ("sampled-seeded", (0.9, 0.95, seed_b)), ("sampled", (1.0, None, None))):
                compare_stats(name, from_file[name], [entry["content"] for entry in server.served[key][:samples]])
            records = read_raw(raw_path)
            tampered = "edited-" + str(FRESH.randint(10, 99))
            for record in records:
                if record["setting"] == "sampled" and record["run"] == "first":
                    record["content"] = tampered
            write_raw(raw_path, records)
            edited = candidate.report(raw_path)
            compare_stats("sampled", edited["sampled"], ordered_contents(records, "sampled", "first", samples))
            require(edited["sampled"]["majority"] == tampered and edited["sampled"]["distinct"] == 1, "Editing the raw records must change the report: the report is recomputed from the file, not remembered")
            return f"Hand-built file with a {n}-sample tie and a skewed setting recomputed exactly; edited raw records changed the report."
        finally:
            stop(server, thread)
    check("The report is recomputed from the raw file", recomputed)

    def rerun():
        epoch, epoch_thread = serve(labels=labels, mode="epoch", epoch_length=samples, fingerprint="fp_epoch")
        honor, honor_thread = serve(labels=labels, mode="honor", fingerprint="fp_honor")
        try:
            seeded = [{"name": "greedy-seeded", "temperature": 0.0, "seed": seed_a}, {"name": "sampled-seeded", "temperature": 0.9, "top_p": 0.95, "seed": seed_b}, {"name": "sampled", "temperature": 1.0}]
            stable = run(honor, settings=seeded)
            require(stable["greedy-seeded"]["reproducible"] is True, f"On a server that honored the seed the rerun matched: reproducible must be true, got {stable['greedy-seeded']['reproducible']!r}")
            require(stable["sampled-seeded"]["reproducible"] is True, f"The seeded sampled setting also matched its rerun: expected true, got {stable['sampled-seeded']['reproducible']!r}")
            require(stable["sampled"]["reproducible"] is None, f"No seed, no rerun, no claim: expected null, got {stable['sampled']['reproducible']!r}")
            require(not any(record["run"] == "rerun" and record["setting"] == "sampled" for record in read_raw(raw_path)), "An unseeded setting is not rerun")
            changed = run(epoch, settings=seeded)
            records = read_raw(raw_path)
            for name in ("greedy-seeded", "sampled-seeded"):
                first = ordered_contents(records, name, "first", samples)
                again = ordered_contents(records, name, "rerun", samples)
                require(len(set(first)) == 1 and first != again, f"adapter invariant: {name} first run {first} should be constant and the rerun {again} different")
                require(changed[name]["reproducible"] is False, f"{name}: the first run was {samples} identical answers but the rerun with the same seed answered {again[0]!r}; reproducible must be false, got {changed[name]['reproducible']!r}")
                compare_stats(name, changed[name], first)
            fingerprints = {record["system_fingerprint"] for record in records if record["setting"] == "greedy-seeded"}
            require(fingerprints == {"fp_epoch", "fp_epoch-redeployed"}, "The raw file keeps the fingerprint of each response so the change is visible")
            return "Reproducible only where the rerun matched: true on the honoring server, false after the adapter changed between runs, null without a seed."
        finally:
            stop(epoch, epoch_thread)
            stop(honor, honor_thread)
    check("A reproducibility claim is rerun, not asserted", rerun)

    def ignored():
        server, thread = serve(labels=labels, mode="ignore", epoch_length=samples)
        try:
            seed_c = FRESH.randint(500, 900)
            result = run(server, settings=[{"name": "seeded", "temperature": 0.8, "seed": seed_c}, {"name": "greedy", "temperature": 0.0, "seed": seed_c}])
            key = (0.8, None, seed_c)
            require(len(server.served.get(key, [])) == 2 * samples, f"The seeded setting must be sampled {samples} times and rerun {samples} times with seed {seed_c}")
            history = [entry["content"] for entry in server.served[key]]
            require(history[:samples] != history[samples:], "adapter invariant: the ignoring server answered the rerun differently")
            require(result["seeded"]["reproducible"] is False, f"The server ignored seed {seed_c}: the rerun differed, so reproducible must be false, got {result['seeded']['reproducible']!r}")
            require(result["greedy"]["reproducible"] is True, f"Greedy decoding on the same server repeated exactly: reproducible must be true, got {result['greedy']['reproducible']!r}")
            compare_stats("seeded", result["seeded"], history[:samples])
            return f"A server that ignores seed {seed_c}: sampled setting not reproducible, greedy setting reproducible; both measured."
        finally:
            stop(server, thread)
    check("A server that ignores the seed is reported as not reproducible", ignored)

    def refused():
        broken_path = os.path.join(WORKSPACE, ".verify-broken.jsonl")
        base = {"model": model, "seed": None, "temperature": 1.0, "top_p": None, "finish_reason": "stop", "usage": {"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4}, "system_fingerprint": None}
        rows = [{"setting": "gap", "run": "first", "index": index, "content": labels[index % 2], **base} for index in (0, 1, 3)]
        seeded = [{**row, "setting": "short", "seed": 5, "index": index} for index, row in enumerate(rows)]
        short_rerun = seeded + [{**row, "run": "rerun"} for row in seeded[:2]]
        cases = (("a missing index", rows), ("a duplicated index", [{**rows[0]}, {**rows[0]}, {**rows[1]}]), ("a seeded setting whose rerun has fewer samples than its first run", short_rerun), ("an empty file", []))
        for description, bad in cases:
            write_raw(broken_path, bad)
            refused_ = False
            try:
                candidate.report(broken_path)
            except ValueError:
                refused_ = True
            require(refused_, f"report must raise ValueError on {description}; a partial file is not a distribution")
        return "Missing index, duplicated index, a short rerun and an empty file were refused with ValueError."
    check("A raw file with missing or duplicated samples is refused", refused)

    def concurrent():
        server, thread = serve(labels=labels, drift=True, delay_ms=40, fingerprint="fp_batch")
        try:
            seeded = [{"name": "greedy-seeded", "temperature": 0.0, "seed": seed_a}, {"name": "greedy", "temperature": 0.0}]
            started = time.perf_counter()
            result = run(server, settings=seeded, concurrency=4)
            elapsed = time.perf_counter() - started
            require(server.max_inflight >= 2, f"concurrency=4 must put requests in flight together; the adapter never saw more than {server.max_inflight} at once")
            records = read_raw(raw_path)
            groups = grouped(records)
            expected = {("greedy-seeded", "first"): samples, ("greedy-seeded", "rerun"): samples, ("greedy", "first"): samples}
            seen = {key: len(value) for key, value in groups.items()}
            require(seen == expected, f"Under concurrency the raw file must still hold {expected}, found {seen}")
            for name, key in (("greedy-seeded", (0.0, None, seed_a)), ("greedy", (0.0, None, None))):
                first = ordered_contents(records, name, "first", samples)
                served_all = sorted(entry["content"] for entry in server.served[key])
                stored = sorted(record["content"] for record in records if record["setting"] == name)
                require(stored == served_all, f"{name}: the stored answers {stored} are not the answers the adapter served {served_all}")
                compare_stats(name, result[name], first)
            require(len({entry["content"] for entry in server.served[(0.0, None, None)]}) >= 2, "adapter invariant: overlapping greedy requests should have drifted")
            require(result["greedy"]["distinct"] >= 2, f"Overlapping requests changed the greedy answer; the report must show it (distinct {result['greedy']['distinct']})")
            return f"4-way concurrency finished {3 * samples} delayed requests in {elapsed * 1000:.0f} ms with the file intact; batch-dependent drift reported as distinct {result['greedy']['distinct']} for a greedy setting."
        finally:
            stop(server, thread)
    check("bonus: concurrent requests stay accounted and expose batch-dependent drift", concurrent, optional=True)

    def live():
        config_path = os.path.join(WORKSPACE, "llm.json")
        try:
            with open(config_path, "r", encoding="utf-8") as file:
                config = json.load(file)
        except Exception as error:
            raise EnvironmentBlocked(f"llm.json could not be read ({type(error).__name__}: {error}). It holds base_url and model only; keys stay in the environment.")
        base_url, live_model = str(config.get("base_url") or ""), str(config.get("model") or "")
        if not base_url or not live_model:
            raise EnvironmentBlocked("Set base_url and model in llm.json to your own endpoint (for Ollama: http://127.0.0.1:11434/v1 and a name from `ollama list`), then verify again.")
        body = json.dumps({"model": live_model, "messages": [{"role": "user", "content": PROMPT}], "max_tokens": 4, "temperature": 0}).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if os.environ.get("LLM_API_KEY"):
            headers["Authorization"] = "Bearer " + os.environ["LLM_API_KEY"]
        request = urllib.request.Request(base_url.rstrip("/") + "/chat/completions", data=body, headers=headers, method="POST")
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=LIVE_TIMEOUT) as response:
                json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            raise EnvironmentBlocked(f"{base_url} answered HTTP {error.code} for model {live_model!r}: {error.read(300).decode('utf-8', 'replace')}")
        except Exception as error:
            raise EnvironmentBlocked(f"{base_url} did not answer within {LIVE_TIMEOUT} s ({type(error).__name__}: {error}). Start or warm up the model with demo.py, then verify again.")
        probe_ms = (time.perf_counter() - started) * 1000
        live_path = os.path.join(WORKSPACE, ".verify-live.jsonl")
        if os.path.exists(live_path):
            os.remove(live_path)
        live_seed = FRESH.randint(1, 10**6)
        live_settings = [{"name": "greedy-seeded", "temperature": 0.0, "seed": live_seed}, {"name": "sampled", "temperature": 1.0}]
        outcome = {}

        def work():
            try:
                outcome["report"] = candidate.run_experiment(live_settings, base_url=base_url, model=live_model, prompt=PROMPT, samples=3, max_tokens=4, out_path=live_path)
            except BaseException as error:  # noqa: BLE001 - reported as the check's failure
                outcome["error"] = error

        worker = threading.Thread(target=work, daemon=True)
        worker.start()
        worker.join(LIVE_BUDGET)
        if worker.is_alive():
            raise EnvironmentBlocked(f"{base_url} ({live_model}) answered the probe in {probe_ms:.0f} ms but nine small requests did not finish within {LIVE_BUDGET} s. Warm the model up with demo.py, then verify again.")
        if "error" in outcome:
            raise outcome["error"]
        result = outcome["report"]
        records = read_raw(live_path)
        groups = {key: len(value) for key, value in grouped(records).items()}
        require(groups == {("greedy-seeded", "first"): 3, ("greedy-seeded", "rerun"): 3, ("sampled", "first"): 3}, f"The live raw file must hold 3 samples per setting plus a 3-sample rerun of the seeded setting, found {groups}")
        for name in ("greedy-seeded", "sampled"):
            compare_stats(name, result[name], ordered_contents(records, name, "first", 3))
        again = ordered_contents(records, "greedy-seeded", "rerun", 3)
        first = ordered_contents(records, "greedy-seeded", "first", 3)
        require(result["greedy-seeded"]["reproducible"] is ([c.strip() for c in first] == [c.strip() for c in again]), "reproducible must state whether the live rerun matched")
        require(result["sampled"]["reproducible"] is None, "The unseeded live setting makes no claim")
        greedy, sampled = result["greedy-seeded"], result["sampled"]
        return (f"Live: {live_model} at {base_url}; 3 samples per setting, max_tokens 4. greedy-seeded (seed {live_seed}): agreement {greedy['agreement']:.2f}, "
                f"rerun {'matched' if greedy['reproducible'] else 'differed'}; sampled (temperature 1.0): {sampled['distinct']} distinct answers, majority {sampled['majority']!r} at {sampled['majority_share']:.2f}, "
                f"entropy {sampled['entropy_bits'] + 0.0:.2f} bits. These are measurements of this endpoint today, not a property of the model.")

    try:
        CHECKS.append({"name": "Live experiment against the configured endpoint is recomputed from its raw file", "passed": True, "detail": live()})
    except EnvironmentBlocked as blocked:
        CHECKS.append({"name": "Environment blocked", "passed": False, "detail": str(blocked)[:1500]})
    except Exception as error:
        CHECKS.append({"name": "Live experiment against the configured endpoint is recomputed from its raw file", "passed": False, "detail": f"{type(error).__name__}: {error}"[:1500]})


try:
    trial()
except Exception as error:
    CHECKS.append({"name": "Load experiment", "passed": False, "detail": f"{type(error).__name__}: {error}"[:1500]})
print(json.dumps({"checks": CHECKS}))
sys.exit(0 if CHECKS and all(item["passed"] for item in CHECKS if not item.get("optional")) else 1)
