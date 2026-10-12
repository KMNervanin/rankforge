"""Model frontier checks for the Frontier mission; run outside the learner workspace.

Two labeled test tools drive the deterministic part: a scripted runner (a Python callable returning
chosen per-case numbers) and a loopback adapter that speaks the chat completions contract with scripted
answers, delays and usage. Neither is a model. The only live evaluation is a three-case run on the endpoint
the learner configured in llm.json, and its numbers are reported as measurements.
"""
import hashlib
import importlib.util
import json
import math
import os
import random
import shutil
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
Z = 1.96
FRESH = random.Random()
ROW_KEYS = {"candidate", "model", "n", "correct", "accuracy", "accuracy_low", "accuracy_high", "p50_ms", "p95_ms", "cost_per_100", "peak_memory_mb", "pareto"}
RESULT_KEYS = {"case", "correct", "latency_ms", "input_tokens", "output_tokens", "cost", "peak_memory_mb"}
SETTINGS = {"prompt_version": "triage-v" + str(FRESH.randint(4, 9)), "system": "You triage supply requests for a relay outpost. Reply with exactly one word: urgent, routine or reject.",
            "template": "Request: {request}", "temperature": 0.0, "max_tokens": FRESH.choice([3, 4, 5])}
REQUESTS = [
    ("urgent", "The relay's spare power cell failed overnight and the backup holds six hours; send a replacement cell."),
    ("routine", "Please add two boxes of printer paper to the next scheduled supply run."),
    ("reject", "Order a crate of fireworks for the solstice party at the north outpost."),
    ("urgent", "Water filter pressure is dropping fast and the tank reads 9 percent; we need filters today."),
    ("routine", "Restock the standard medkit consumables when the monthly convoy comes through."),
    ("reject", "Ship a personal gaming console to bunk 4, charged to the outpost account."),
    ("urgent", "Antenna mast guy-wire snapped in the storm; the mast is swaying and we need cable and clamps now."),
    ("routine", "Add four replacement headlamp batteries to the quarterly order."),
    ("reject", "Send the unredacted personnel files for every operator on the ridge."),
    ("urgent", "Generator coolant leak, temperature alarm active, one hour of runtime left; coolant and a hose kit required."),
    ("routine", "Swap the worn kitchen knives for new ones on the next run, no hurry."),
    ("reject", "Deliver forty litres of ethanol to the crew lounge for recreational use."),
    ("urgent", "Fuel line to the heater cracked and the cabin is at 4 degrees; a line kit is needed before nightfall."),
    ("routine", "Replace the frayed flag on the mast when a convoy is next in the area."),
    ("reject", "Send a drone to film the neighbouring outpost's yard without telling them."),
    ("urgent", "Oxygen sensor on the lower deck reads error and the alarm will not clear; a sensor is required now."),
    ("routine", "Put a new whiteboard for the duty roster on the next regular shipment."),
    ("reject", "Ship a case of spirits for the night shift to keep warm."),
    ("urgent", "Comms encryption module is throwing checksum errors on every packet; a spare module is needed today."),
    ("routine", "Order a spare set of cutlery for the mess, whenever convenient."),
]


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def check(name, operation, optional=False):
    # An optional check is the hidden bonus of a mission: it can only add, it never fails the run.
    flag = {"optional": True} if optional else {}
    try:
        detail = operation()
        CHECKS.append({"name": name, "passed": True, "detail": detail or "Verified.", **flag})
    except Exception as error:
        CHECKS.append({"name": name, "passed": False, "detail": f"{type(error).__name__}: {error}"[:1500], **flag})


class EnvironmentBlocked(Exception):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def case_set(version, count, offset=0):
    cases = [{"id": f"k{offset + i:02d}", "request": REQUESTS[i][1], "expected": REQUESTS[i][0]} for i in range(count)]
    return {"version": version, "cases": cases}


def expected_set_hash(cases):
    reduced = sorted(({"id": c["id"], "request": c["request"], "expected": c["expected"]} for c in cases["cases"]), key=lambda c: c["id"])
    return digest({"version": cases["version"], "cases": reduced})


def close(value, wanted, what, tolerance=TOLERANCE):
    require(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value), f"{what} must be a finite number, got {value!r}")
    require(abs(Fraction(str(value)) - Fraction(wanted)) <= tolerance, f"{what} is {value!r}, expected {float(wanted)!r}")


def wilson(successes, n):
    p, z2 = successes / n, Z * Z
    center = (p + z2 / (2 * n)) / (1 + z2 / n)
    half = Z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / (1 + z2 / n)
    return max(0.0, center - half), min(1.0, center + half)


def nearest_rank(values, percent):
    ordered = sorted(values)
    rank = -(-percent * len(ordered) // 100)
    return ordered[rank - 1]


# ---------------------------------------------------------------- loopback adapter (labeled test tool)
class Adapter(socketserver.ThreadingMixIn, HTTPServer):
    """OpenAI-compatible loopback server: scripted answer per (model, request text), per-model delay, usage and memory."""
    daemon_threads = True

    def __init__(self, script, delays, memory):
        super().__init__(("127.0.0.1", 0), AdapterHandler)
        self.script, self.delays, self.memory = script, delays, memory
        self.requests = []
        self.lock = threading.Lock()

    def server_bind(self):
        socketserver.TCPServer.server_bind(self)
        self.server_name = "localhost"
        self.server_port = self.server_address[1]

    def handle_error(self, request, client_address):
        pass

    @property
    def base_url(self):
        return f"http://127.0.0.1:{self.server_port}/v1"


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
        raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        try:
            body = json.loads(raw)
            require(isinstance(body, dict) and isinstance(body.get("messages"), list) and body["messages"], "messages required")
            require(isinstance(body.get("model"), str) and body["model"], "model required")
        except Exception as error:
            self.reply(400, {"error": {"message": f"invalid request: {error}", "type": "invalid_request_error"}})
            return
        with server.lock:
            server.requests.append({"path": self.path, "body": body})
        if not self.path.endswith("/chat/completions"):
            self.reply(404, {"error": {"message": "unknown route", "type": "invalid_request_error"}})
            return
        model = body["model"]
        text = "\n".join(str(m.get("content", "")) for m in body["messages"])
        answer = "routine"
        for request_text, scripted in server.script.get(model, {}).items():
            if request_text in text:
                answer = scripted
        time.sleep(server.delays.get(model, 0) / 1000)
        prompt_tokens = len(text.split()) + 3 * len(body["messages"]) + (len(model) % 7)
        completion_tokens = len(answer.split()) + (1 if model.endswith("b") else 0)
        usage = {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens, "total_tokens": prompt_tokens + completion_tokens}
        if model in server.memory:
            usage["peak_memory_mb"] = server.memory[model]
        self.reply(200, {"id": f"chatcmpl-adapter-{len(server.requests)}", "object": "chat.completion", "created": int(time.time()), "model": model,
                         "choices": [{"index": 0, "message": {"role": "assistant", "content": answer}, "finish_reason": "stop"}], "usage": usage,
                         "system_fingerprint": "fp_scripted_adapter"})


def serve(script, delays, memory):
    server = Adapter(script, delays, memory)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
    thread.start()
    return server, thread


def stop(server, thread):
    server.shutdown()
    server.server_close()
    thread.join(timeout=1)


# ---------------------------------------------------------------- hand-designed fixture of five candidates on twenty cases
def design_fixture():
    """Accuracies, p95 and prices are chosen by hand so that the Pareto set and the decisions are known before any code runs.
    Candidate ids carry a fresh suffix and one of two designs is drawn, so an answer keyed on a name fails."""
    scale_latency = FRESH.uniform(0.7, 1.3)
    scale_price = FRESH.uniform(0.5, 2.0)
    suffix = "".join(FRESH.choice("abcdefghjkmnpqrstuvwxyz") for _ in range(3))
    cases = case_set("fixture-v" + str(FRESH.randint(1, 99)), 20)
    ids_ = [c["id"] for c in cases["cases"]]
    # role: (wrong answers, p50, p95, input price, output price, peak memory). Token counts stay within 45–55 in and 1–3 out,
    # so per-case cost ranges of neighbouring roles never overlap and the designed cost order holds for any draw.
    designs = {
        "large-dominated": {  # large is dominated by mid (same accuracy, slower, dearer); loose budget picks mid
            "xl": (1, 1200, 1900, 2.5, 10.0, 9000), "large": (2, 900, 1400, 1.2, 4.8, None), "mid": (2, 600, 900, 0.6, 2.4, None),
            "fast": (3, 300, 500, 0.9, 3.6, None), "tiny": (7, 250, 450, 0.2, 0.8, None),
        },
        "tiny-dominated": {  # tiny is dominated by fast (same accuracy, slower, dearer); large is the cheapest and loose budget picks it
            "xl": (1, 1200, 1900, 2.5, 10.0, 9000), "large": (2, 900, 1400, 0.4, 1.6, None), "mid": (2, 600, 900, 0.6, 2.4, None),
            "fast": (3, 300, 500, 0.9, 3.6, None), "tiny": (3, 350, 600, 1.4, 5.6, None),
        },
    }
    design_name = FRESH.choice(sorted(designs))
    ids = {role: f"relay-{role}-{suffix}" for role in designs[design_name]}
    manifests = {}
    for role, (wrong, p50, p95, in_price, out_price, memory) in designs[design_name].items():
        name = ids[role]
        wrong_ids = set(FRESH.sample(ids_, wrong))
        latencies = [FRESH.randint(int(p50 * 0.5), p50 - 1) for _ in range(9)] + [p50] + [FRESH.randint(p50 + 1, p95 - 1) for _ in range(8)] + [p95, FRESH.randint(p95 + 1, int(p95 * 1.5))]
        FRESH.shuffle(latencies)
        prices = {"input_price_per_million": round(in_price * scale_price, 4), "output_price_per_million": round(out_price * scale_price, 4)}
        results = []
        for case, latency in zip(cases["cases"], latencies):
            tokens_in, tokens_out = 50 + FRESH.randint(-5, 5), FRESH.choice([1, 2, 3])
            cost = (Fraction(tokens_in) * Fraction(str(prices["input_price_per_million"])) + Fraction(tokens_out) * Fraction(str(prices["output_price_per_million"]))) / 1_000_000
            results.append({"case": case["id"], "correct": 0 if case["id"] in wrong_ids else 1, "latency_ms": max(1, round(latency * scale_latency)),
                            "input_tokens": tokens_in, "output_tokens": tokens_out, "cost": float(cost), "peak_memory_mb": memory})
        manifests[name] = {"candidate": name, "model": name + "-model", "set_version": cases["version"], "set_hash": expected_set_hash(cases),
                           "settings_hash": digest(SETTINGS), "settings": dict(SETTINGS), "prices": prices, "results": results}
    budgets = {"loose": max(1, round(2000 * scale_latency)), "tight": max(1, round(800 * scale_latency))}
    dominated = "large" if design_name == "large-dominated" else "tiny"
    cheapest = "mid" if design_name == "large-dominated" else "large"
    # Both designs plant an equal-accuracy dominated pair, so dominance that demands strictly higher accuracy fails either draw.
    return cases, manifests, budgets, ids, {"dominated": dominated, "cheapest": cheapest, "tiny_within": design_name == "tiny-dominated"}


def oracle_rows(manifests):
    rows = {}
    for name, manifest in manifests.items():
        results = manifest["results"]
        n, correct = len(results), sum(r["correct"] for r in results)
        low, high = wilson(correct, n)
        memories = [r["peak_memory_mb"] for r in results if r["peak_memory_mb"] is not None]
        rows[name] = {"candidate": name, "model": manifest["model"], "n": n, "correct": correct, "accuracy": correct / n, "accuracy_low": low, "accuracy_high": high,
                      "p50_ms": nearest_rank([r["latency_ms"] for r in results], 50), "p95_ms": nearest_rank([r["latency_ms"] for r in results], 95),
                      "cost_per_100": float(sum(Fraction(str(r["cost"])) for r in results) * 100 / n), "peak_memory_mb": max(memories) if memories else None}
    return rows


def compare_row(row, wanted):
    require(isinstance(row, dict) and not (ROW_KEYS - set(row)), f"Row for {wanted['candidate']} is missing keys: {sorted(ROW_KEYS - set(row or {}))}")
    name = wanted["candidate"]
    require(row["model"] == wanted["model"], f"{name}: model {row['model']!r}, expected {wanted['model']!r}")
    require(row["n"] == wanted["n"] and row["correct"] == wanted["correct"], f"{name}: n/correct {row['n']}/{row['correct']}, expected {wanted['n']}/{wanted['correct']} from the raw results")
    close(row["accuracy"], Fraction(wanted["correct"], wanted["n"]), f"{name}: accuracy")
    close(row["accuracy_low"], Fraction(str(wanted["accuracy_low"])), f"{name}: accuracy_low (Wilson, z=1.96)", Fraction(1, 10**6))
    close(row["accuracy_high"], Fraction(str(wanted["accuracy_high"])), f"{name}: accuracy_high (Wilson, z=1.96)", Fraction(1, 10**6))
    require(row["p50_ms"] == wanted["p50_ms"], f"{name}: p50_ms {row['p50_ms']!r}, expected the nearest-rank 50th percentile {wanted['p50_ms']}")
    require(row["p95_ms"] == wanted["p95_ms"], f"{name}: p95_ms {row['p95_ms']!r}, expected the nearest-rank 95th percentile {wanted['p95_ms']}")
    close(row["cost_per_100"], Fraction(str(wanted["cost_per_100"])), f"{name}: cost_per_100", Fraction(1, 10**7))
    require(row["peak_memory_mb"] == wanted["peak_memory_mb"], f"{name}: peak_memory_mb {row['peak_memory_mb']!r}, expected {wanted['peak_memory_mb']!r}")


def check_decision(decision, *, chosen, best, tolerance, budget, reasons, rows):
    require(isinstance(decision, dict), "decide must return a dict")
    for key in ("chosen", "best", "tolerance", "budget", "rejected", "summary"):
        require(key in decision, f"The decision is missing {key!r}")
    require(decision["chosen"] == chosen, f"chosen is {decision['chosen']!r}, expected {chosen!r} (the cheapest candidate within tolerance {tolerance} of the best that fits the budget)")
    require(decision["best"] == best, f"best is {decision['best']!r}, expected {best!r}")
    close(decision["tolerance"], Fraction(str(tolerance)), "tolerance")
    require(isinstance(decision["rejected"], list), "rejected must be a list")
    seen = {}
    for entry in decision["rejected"]:
        require(isinstance(entry, dict) and {"candidate", "reason", "detail"} <= set(entry), f"Each rejected entry needs candidate, reason and detail: {entry!r}")
        seen[entry["candidate"]] = entry
    require(set(seen) == set(reasons), f"rejected names {sorted(seen)}, expected every candidate but the chosen one: {sorted(reasons)}")
    for name, reason in reasons.items():
        entry, row = seen[name], rows[name]
        require(entry["reason"] == reason, f"{name} rejected for {entry['reason']!r}, expected {reason!r}")
        cited = {"quality": f"{row['accuracy']:.3f}", "latency": f"{row['p95_ms']} ms", "memory": f"{row['peak_memory_mb']} MB", "cost": f"{row['cost_per_100']:.4f}"}[reason]
        require(cited in str(entry["detail"]), f"{name}: the {reason} detail must cite {cited!r}, got {entry['detail']!r}")
    summary = str(decision["summary"])
    if chosen is None:
        require("no candidate" in summary.lower() and best in summary, f"With nothing eligible the summary must say 'no candidate' and still name the best {best!r}: {summary!r}")
        return
    row = rows[chosen]
    for fragment in (chosen, best, f"{row['accuracy']:.3f}", f"{rows[best]['accuracy']:.3f}", f"{tolerance:.3f}", f"{row['p95_ms']} ms", f"{budget['p95_ms']} ms", f"{row['cost_per_100']:.4f}"):
        require(fragment in summary, f"The summary must cite {fragment!r}; got {summary!r}")


def trial():
    require(MISSION == "frontier", "Unknown mission")
    sys.path.insert(0, WORKSPACE)
    spec = importlib.util.spec_from_file_location("candidate_frontier", os.path.join(WORKSPACE, "frontier.py"))
    if spec is None or spec.loader is None:
        raise ImportError("Cannot load frontier.py")
    candidate = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = candidate
    spec.loader.exec_module(candidate)
    for name in ("run_candidates", "frontier", "decide"):
        require(callable(getattr(candidate, name, None)), f"frontier.py must define {name}(...)")

    def scripted_runs():
        cases = case_set("scripted-v" + str(FRESH.randint(1, 99)), 10, offset=20)
        candidates = [{"id": f"cand-{letter}", "model": f"model-{letter}-{FRESH.randint(100, 999)}", "input_price_per_million": round(FRESH.uniform(0.1, 3.0), 3),
                       "output_price_per_million": round(FRESH.uniform(0.5, 12.0), 3)} for letter in ("a", "b", "c")]
        table = {(c["model"], case["id"]): {"correct": FRESH.randint(0, 1), "latency_ms": FRESH.randint(40, 2500), "input_tokens": FRESH.randint(20, 90), "output_tokens": FRESH.randint(1, 6)}
                 for c in candidates for case in cases["cases"]}
        memory_model = candidates[1]["model"]
        calls = []

        def run_case(model, case, settings):
            calls.append((model, case.get("id") if isinstance(case, dict) else None, canonical(settings)))
            require((model, case["id"]) in table, f"run_case received model {model!r} and case {case!r} that were not given")
            outcome = dict(table[(model, case["id"])])
            if model == memory_model:
                outcome["peak_memory_mb"] = 3000 + len(case["id"])
            return outcome

        out_dir = os.path.join(WORKSPACE, ".verify-runs-scripted")
        returned = candidate.run_candidates(candidates, cases, base_url="http://127.0.0.1:9/v1", settings=SETTINGS, out_dir=out_dir, run_case=run_case)
        require(isinstance(returned, list) and len(returned) == 3, "run_candidates must return one manifest per candidate")
        wanted_ids = [c["id"] for c in cases["cases"]]
        for spec_ in candidates:
            mine = [c for c in calls if c[0] == spec_["model"]]
            require(sorted(c[1] for c in mine) == sorted(wanted_ids), f"{spec_['id']} must run every case exactly once; ran {[c[1] for c in mine]}")
            require(all(c[2] == canonical(SETTINGS) for c in mine), f"{spec_['id']} was run with settings that differ from the shared settings")
        require(len(calls) == 30, f"Expected 30 calls (3 candidates × 10 cases), saw {len(calls)}")
        for spec_, manifest in zip(candidates, returned):
            path = os.path.join(out_dir, spec_["id"] + ".json")
            require(os.path.exists(path), f"Manifest {spec_['id']}.json must be written to out_dir")
            with open(path, "r", encoding="utf-8") as file:
                on_disk = json.load(file)
            require(on_disk == json.loads(json.dumps(manifest)), f"{spec_['id']}: the returned manifest must equal the file on disk")
            require(manifest.get("candidate") == spec_["id"] and manifest.get("model") == spec_["model"], f"{spec_['id']}: candidate/model must be recorded")
            require(manifest.get("set_version") == cases["version"], f"{spec_['id']}: set_version {manifest.get('set_version')!r}, expected {cases['version']!r}")
            require(manifest.get("set_hash") == expected_set_hash(cases), f"{spec_['id']}: set_hash must be the sha256 of the canonical set (version plus cases sorted by id)")
            require(manifest.get("settings_hash") == digest(SETTINGS), f"{spec_['id']}: settings_hash must be the sha256 of the canonical settings")
            require(manifest.get("prices") == {"input_price_per_million": spec_["input_price_per_million"], "output_price_per_million": spec_["output_price_per_million"]}, f"{spec_['id']}: prices must be copied from the candidate")
            results = manifest.get("results")
            require(isinstance(results, list) and [r.get("case") for r in results] == wanted_ids, f"{spec_['id']}: results must hold one entry per case in set order")
            for result in results:
                require(not (RESULT_KEYS - set(result)), f"{spec_['id']}: result {result.get('case')} is missing {sorted(RESULT_KEYS - set(result))}")
                scripted = table[(spec_["model"], result["case"])]
                for key in ("correct", "latency_ms", "input_tokens", "output_tokens"):
                    require(result[key] == scripted[key], f"{spec_['id']} {result['case']}: {key} {result[key]!r}, the runner returned {scripted[key]}")
                wanted_cost = (Fraction(scripted["input_tokens"]) * Fraction(str(spec_["input_price_per_million"])) + Fraction(scripted["output_tokens"]) * Fraction(str(spec_["output_price_per_million"]))) / 1_000_000
                close(result["cost"], wanted_cost, f"{spec_['id']} {result['case']}: cost from the candidate's price table")
                wanted_memory = 3000 + len(result["case"]) if spec_["model"] == memory_model else None
                require(result["peak_memory_mb"] == wanted_memory, f"{spec_['id']} {result['case']}: peak_memory_mb {result['peak_memory_mb']!r}, expected {wanted_memory!r} (null when the runner reports none)")
        return "Three candidates ran the same ten cases once each with identical settings; manifests carry the runner's numbers, the price-table cost and matching hashes."
    check("Every candidate runs the same cases with the same settings", scripted_runs)

    def own_runner():
        cases = case_set("adapter-v" + str(FRESH.randint(1, 99)), 6, offset=40)
        candidates = [{"id": "adapter-small", "model": f"small-{FRESH.randint(100, 999)}b", "input_price_per_million": 0.3, "output_price_per_million": 1.2},
                      {"id": "adapter-large", "model": f"large-{FRESH.randint(100, 999)}", "input_price_per_million": 2.0, "output_price_per_million": 8.0}]
        small, large = candidates[0]["model"], candidates[1]["model"]
        script = {small: {}, large: {}}
        wrong_small, wrong_large = FRESH.sample(range(6), 2), FRESH.sample(range(6), 1)
        for index, case in enumerate(cases["cases"]):
            script[small][case["request"]] = "not " + case["expected"] if index in wrong_small else case["expected"] + "."
            script[large][case["request"]] = ("routine" if case["expected"] != "routine" else "reject") if index in wrong_large else case["expected"].upper()
        delays = {small: 5, large: 30}
        server, thread = serve(script, delays, {large: 7000 + FRESH.randint(0, 99)})
        try:
            out_dir = os.path.join(WORKSPACE, ".verify-runs-adapter")
            started = time.perf_counter()
            returned = candidate.run_candidates(candidates, cases, base_url=server.base_url, settings=SETTINGS, out_dir=out_dir)
            waited_ms = (time.perf_counter() - started) * 1000
            require(isinstance(returned, list) and len(returned) == 2, "run_candidates must return one manifest per candidate")
            bodies = [r["body"] for r in server.requests if r["path"].endswith("/chat/completions")]
            require(len(bodies) == 12, f"Expected 12 requests (2 candidates × 6 cases), the adapter saw {len(bodies)}")
            per_model = {}
            for body in bodies:
                require(body.get("stream") in (None, False), "Do not stream in this mission")
                require(body.get("max_tokens") == SETTINGS["max_tokens"], f"max_tokens sent {body.get('max_tokens')!r}, expected {SETTINGS['max_tokens']}")
                require(isinstance(body.get("temperature"), (int, float)) and abs(body["temperature"] - SETTINGS["temperature"]) < 1e-9, f"temperature sent {body.get('temperature')!r}, expected {SETTINGS['temperature']}")
                messages = body.get("messages")
                require(isinstance(messages, list) and len(messages) == 2 and messages[0].get("role") == "system" and messages[1].get("role") == "user", "messages must be [system, user]")
                require(messages[0].get("content") == SETTINGS["system"], "The system message must be settings.system verbatim")
                per_model.setdefault(body["model"], []).append(json.loads(canonical({k: v for k, v in body.items() if k != "model"})))
            require(set(per_model) == {small, large}, f"Requests must name each candidate's model id; saw {sorted(per_model)}")
            for case in cases["cases"]:
                wanted_user = SETTINGS["template"].replace("{request}", case["request"])
                for model in (small, large):
                    hits = [b for b in per_model[model] if b["messages"][1]["content"] == wanted_user]
                    require(len(hits) == 1, f"{model}: case {case['id']} must be sent exactly once with the user message from the template; found {len(hits)}")
            small_bodies = sorted(per_model[small], key=canonical)
            large_bodies = sorted(per_model[large], key=canonical)
            require(small_bodies == large_bodies, "Apart from the model id, the request bodies for a case must be identical across candidates")
            for spec_, manifest in zip(candidates, returned):
                wrong = wrong_small if spec_["model"] == small else wrong_large
                for index, result in enumerate(manifest["results"]):
                    require(result["correct"] == (0 if index in wrong else 1), f"{spec_['id']} {result['case']}: correct {result['correct']!r}; the answer was {script[spec_['model']][cases['cases'][index]['request']]!r} for expected {cases['cases'][index]['expected']!r} (strip, trailing period, case-insensitive equality)")
                    body = next(b for b in bodies if b["model"] == spec_["model"] and b["messages"][1]["content"] == SETTINGS["template"].replace("{request}", cases["cases"][index]["request"]))
                    text = "\n".join(str(m.get("content", "")) for m in body["messages"])
                    wanted_in = len(text.split()) + 3 * len(body["messages"]) + (len(spec_["model"]) % 7)
                    require(result["input_tokens"] == wanted_in, f"{spec_['id']} {result['case']}: input_tokens {result['input_tokens']!r} must be usage.prompt_tokens ({wanted_in})")
                    require(type(result["latency_ms"]) is int and result["latency_ms"] >= delays[spec_["model"]], f"{spec_['id']} {result['case']}: latency_ms {result['latency_ms']!r} is below the {delays[spec_['model']]} ms the adapter took")
                    require(result["latency_ms"] <= math.ceil(waited_ms) + 1, f"{spec_['id']} {result['case']}: latency_ms {result['latency_ms']} exceeds the time waited")
                    wanted_memory = None if spec_["model"] == small else server.memory[large]
                    require(result["peak_memory_mb"] == wanted_memory, f"{spec_['id']} {result['case']}: peak_memory_mb {result['peak_memory_mb']!r}, expected {wanted_memory!r} from usage.peak_memory_mb")
            return "Twelve requests differed only in the model id; correctness, usage, latency and memory were taken from each response."
        finally:
            stop(server, thread)
    check("The learner's own runner sends identical prompts across candidates and meters each call", own_runner)

    cases, manifests, budgets, ids, plan = design_fixture()
    rows_oracle = oracle_rows(manifests)
    xl, large, mid, fast, tiny = (ids[role] for role in ("xl", "large", "mid", "fast", "tiny"))
    dominated, cheapest = ids[plan["dominated"]], ids[plan["cheapest"]]

    def rejected_manifests():
        base = json.loads(json.dumps(manifests[mid]))
        other_settings = dict(SETTINGS, temperature=0.7)
        tweaked = json.loads(json.dumps(manifests[fast]))
        tweaked.update({"settings": other_settings, "settings_hash": digest(other_settings)})
        other_set = case_set(cases["version"] + "-subset", 10)
        subset = json.loads(json.dumps(manifests[tiny]))
        subset.update({"set_version": other_set["version"], "set_hash": expected_set_hash(other_set), "results": subset["results"][:10]})
        partial = json.loads(json.dumps(manifests[large]))
        partial["results"] = partial["results"][:12]
        for bad, field in ((tweaked, "settings_hash"), (subset, "set_hash"), (partial, "results")):
            try:
                candidate.frontier([base, bad])
            except ValueError as error:
                require(bad["candidate"] in str(error) and field in str(error), f"The ValueError must name {bad['candidate']!r} and {field!r}: {error}")
            else:
                raise AssertionError(f"frontier must raise ValueError when {bad['candidate']} was run with a different {field}")
        rows = candidate.frontier([base, json.loads(json.dumps(manifests[fast]))])
        require(isinstance(rows, list) and len(rows) == 2, "Two manifests on the same set and settings are accepted")
        return "Different settings, a different set and a partial run were each refused with the candidate and the field named."
    check("Manifests from a different set or different settings are rejected with a named reason", rejected_manifests)

    def recomputed():
        tampered = json.loads(json.dumps(manifests))
        for name, manifest in tampered.items():
            manifest["summary"] = {"accuracy": 1.0, "correct": 20, "p50_ms": 1, "p95_ms": 1, "cost_per_100": 0.0, "pareto": True}
            manifest["pareto"] = True
        rows = candidate.frontier(list(tampered.values()))
        require(isinstance(rows, list) and len(rows) == 5, f"frontier must return five rows, got {type(rows).__name__} of {len(rows) if isinstance(rows, list) else '?'}")
        require([r.get("candidate") for r in rows] == sorted(manifests), "Rows are ordered by candidate id")
        for row in rows:
            compare_row(row, rows_oracle[row["candidate"]])
        return "Aggregates for five candidates matched the raw results; the forged summary blocks were ignored."
    check("The frontier recomputes every aggregate from raw results", recomputed)

    def pareto():
        rows = candidate.frontier(list(manifests.values()))
        got = {r["candidate"]: r.get("pareto") for r in rows}
        wanted = {name: name != dominated for name in manifests}
        require(all(type(v) is bool for v in got.values()), f"pareto must be a boolean per row: {got}")
        dominator = mid if plan["dominated"] == "large" else fast
        require(got == wanted, f"Pareto membership {got}, expected {wanted}: {dominated} is dominated by {dominator} (equal accuracy, higher p95, higher cost); the rest trade quality, latency and cost")
        return f"Four of five candidates on the frontier; {dominated} named as dominated."
    check("Pareto membership matches the hand-computed frontier", pareto)

    def decision():
        rows = [dict(r, pareto=(r["candidate"] != dominated)) for r in rows_oracle.values()]
        FRESH.shuffle(rows)
        eligible_cost = {name: "cost" for name in (xl, large, mid, fast) if name != cheapest}
        tiny_loose = "cost" if plan["tiny_within"] else "quality"
        budget = {"tolerance": 0.1, "p95_ms": budgets["loose"]}
        check_decision(candidate.decide(rows, budget), chosen=cheapest, best=xl, tolerance=0.1, budget=budget, reasons={**eligible_cost, tiny: tiny_loose}, rows=rows_oracle)
        with_memory = dict(budget, memory_mb=6000)
        check_decision(candidate.decide(rows, with_memory), chosen=cheapest, best=xl, tolerance=0.1, budget=with_memory, reasons={**eligible_cost, xl: "memory", tiny: tiny_loose}, rows=rows_oracle)
        strict = {"tolerance": 0.02, "p95_ms": budgets["loose"]}
        check_decision(candidate.decide(rows, strict), chosen=xl, best=xl, tolerance=0.02, budget=strict, reasons={large: "quality", mid: "quality", fast: "quality", tiny: "quality"}, rows=rows_oracle)
        return f"{cheapest} chosen over {xl} within tolerance 0.100 under a {budget['p95_ms']} ms budget; a memory budget rejected {xl} by name; tolerance 0.020 kept {xl}."
    check("The decision picks the cheapest candidate within tolerance and cites measured numbers", decision)

    def transfer():
        rows = [dict(r, pareto=(r["candidate"] != dominated)) for r in rows_oracle.values()]
        tight = {"tolerance": 0.1, "p95_ms": budgets["tight"]}
        check_decision(candidate.decide(rows, tight), chosen=fast, best=xl, tolerance=0.1, budget=tight, reasons={xl: "latency", large: "latency", mid: "latency", tiny: "cost" if plan["tiny_within"] else "quality"}, rows=rows_oracle)
        nothing = {"tolerance": 0.02, "p95_ms": budgets["tight"]}
        check_decision(candidate.decide(rows, nothing), chosen=None, best=xl, tolerance=0.02, budget=nothing, reasons={xl: "latency", large: "quality", mid: "quality", fast: "quality", tiny: "quality"}, rows=rows_oracle)
        return f"A {tight['p95_ms']} ms budget moved the choice from {cheapest} to {fast}; with tolerance 0.020 nothing was eligible and the record said so."
    check("A tighter latency budget changes the choice to a faster candidate", transfer)

    def paired():
        rows = candidate.frontier(list(manifests.values()))
        best_results = {r["case"]: r["correct"] for r in manifests[xl]["results"]}
        for row in rows:
            block = row.get("paired_vs_best")
            require(isinstance(block, dict) and {"best", "mean_diff", "se", "low", "high"} <= set(block), f"{row['candidate']}: paired_vs_best must carry best, mean_diff, se, low and high")
            require(block["best"] == xl, f"{row['candidate']}: the comparison baseline must be the best candidate {xl}")
            diffs = [r["correct"] - best_results[r["case"]] for r in manifests[row["candidate"]]["results"]]
            n = len(diffs)
            mean = sum(diffs) / n
            se = math.sqrt(sum((d - mean) ** 2 for d in diffs) / (n * (n - 1)))
            close(block["mean_diff"], Fraction(str(mean)), f"{row['candidate']}: mean_diff", Fraction(1, 10**6))
            close(block["se"], Fraction(str(se)), f"{row['candidate']}: se", Fraction(1, 10**6))
            close(block["low"], Fraction(str(mean - Z * se)), f"{row['candidate']}: low", Fraction(1, 10**6))
            close(block["high"], Fraction(str(mean + Z * se)), f"{row['candidate']}: high", Fraction(1, 10**6))
        return f"Per-case paired differences against {xl} carry a standard error and a 95% interval."
    check("bonus: paired per-case differences against the best carry an interval", paired, optional=True)

    def live():
        config_path = os.path.join(WORKSPACE, "llm.json")
        try:
            with open(config_path, "r", encoding="utf-8") as file:
                config = json.load(file)
        except Exception as error:
            raise EnvironmentBlocked(f"llm.json could not be read ({type(error).__name__}: {error}). It holds base_url, model and prices only; keys stay in the environment.")
        base_url, live_model = str(config.get("base_url") or ""), str(config.get("model") or "")
        if not base_url or not live_model:
            raise EnvironmentBlocked("Set base_url and model in llm.json to your own endpoint (for Ollama: http://127.0.0.1:11434/v1 and a name from `ollama list`), then verify again.")
        live_cases = case_set("live-v1", 3, offset=60)
        probe_messages = [{"role": "system", "content": SETTINGS["system"]}, {"role": "user", "content": SETTINGS["template"].replace("{request}", live_cases["cases"][0]["request"])}]
        body = json.dumps({"model": live_model, "messages": probe_messages, "max_tokens": SETTINGS["max_tokens"], "temperature": 0}).encode("utf-8")
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
        spec_ = {"id": "live", "model": live_model, "input_price_per_million": config.get("input_price_per_million") or 0, "output_price_per_million": config.get("output_price_per_million") or 0}
        out_dir = os.path.join(WORKSPACE, ".verify-runs-live")
        outcome = {}

        def work():
            try:
                outcome["manifests"] = candidate.run_candidates([spec_], live_cases, base_url=base_url, settings=SETTINGS, out_dir=out_dir)
            except BaseException as error:  # noqa: BLE001 - reported as the check's failure
                outcome["error"] = error

        started = time.perf_counter()
        worker = threading.Thread(target=work, daemon=True)
        worker.start()
        worker.join(LIVE_BUDGET)
        waited_ms = (time.perf_counter() - started) * 1000
        if worker.is_alive():
            raise EnvironmentBlocked(f"{base_url} ({live_model}) answered the probe in {probe_ms:.0f} ms but three small requests did not finish within {LIVE_BUDGET} s. Warm the model up with demo.py, then verify again.")
        if "error" in outcome:
            raise outcome["error"]
        manifests_ = outcome["manifests"]
        require(isinstance(manifests_, list) and len(manifests_) == 1, "One live candidate yields one manifest")
        manifest = manifests_[0]
        require(manifest.get("model") == live_model and manifest.get("set_hash") == expected_set_hash(live_cases) and manifest.get("settings_hash") == digest(SETTINGS), "The live manifest must carry the model id and the hashes of the set and settings it ran")
        results = manifest.get("results")
        require(isinstance(results, list) and [r.get("case") for r in results] == [c["id"] for c in live_cases["cases"]], "The live manifest must hold one result per case in order")
        for result in results:
            require(result["correct"] in (0, 1), f"correct must be 0 or 1, got {result['correct']!r}")
            require(type(result["latency_ms"]) is int and 0 <= result["latency_ms"] <= math.ceil(waited_ms) + 1, f"latency_ms {result['latency_ms']!r} must be a measured integer within the time waited")
            require(type(result["input_tokens"]) is int and result["input_tokens"] > 0 and type(result["output_tokens"]) is int and result["output_tokens"] > 0, f"token counts must be the endpoint's usage integers: {result!r}")
            wanted_cost = (Fraction(result["input_tokens"]) * Fraction(str(spec_["input_price_per_million"])) + Fraction(result["output_tokens"]) * Fraction(str(spec_["output_price_per_million"]))) / 1_000_000
            close(result["cost"], wanted_cost, f"{result['case']}: live cost from the llm.json prices")
        correct = sum(r["correct"] for r in results)
        low, high = wilson(correct, len(results))
        latencies = [r["latency_ms"] for r in results]
        cost_per_100 = float(sum(Fraction(str(r["cost"])) for r in results) * 100 / len(results))
        return (f"Live: {live_model} at {base_url}; 3 cases, max_tokens {SETTINGS['max_tokens']}: {correct}/3 correct (Wilson {low:.2f}–{high:.2f}), "
                f"p50 {nearest_rank(latencies, 50)} ms, p95 {nearest_rank(latencies, 95)} ms, {sum(r['input_tokens'] for r in results)} prompt and {sum(r['output_tokens'] for r in results)} completion tokens, "
                f"cost {cost_per_100:.4f} per 100 cases. A measurement of this endpoint today on three cases, not a verdict on the model.")

    try:
        CHECKS.append({"name": "Live run of three cases on the configured model produces a measured manifest", "passed": True, "detail": live()})
    except EnvironmentBlocked as blocked:
        CHECKS.append({"name": "Environment blocked", "passed": False, "detail": str(blocked)[:1500]})
    except Exception as error:
        CHECKS.append({"name": "Live run of three cases on the configured model produces a measured manifest", "passed": False, "detail": f"{type(error).__name__}: {error}"[:1500]})


try:
    trial()
except Exception as error:
    CHECKS.append({"name": "Load frontier module", "passed": False, "detail": f"{type(error).__name__}: {error}"[:1500]})
finally:
    for leftover in (".verify-runs-scripted", ".verify-runs-adapter", ".verify-runs-live"):
        shutil.rmtree(os.path.join(WORKSPACE, leftover), ignore_errors=True)
print(json.dumps({"checks": CHECKS}))
sys.exit(0 if CHECKS and all(item["passed"] for item in CHECKS if not item.get("optional")) else 1)
