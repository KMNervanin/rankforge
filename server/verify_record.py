"""Structured extraction checks for the Record mission; run outside the learner workspace.

The scripted adapter below is a labeled test tool: it speaks the chat completions contract and
answers with chosen outputs in a chosen order, recording every request body. The only live
evaluation is the final measurement against the endpoint the learner configured in llm.json.
"""
import copy
import importlib.util
import json
import os
import random
import socketserver
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

MISSION, WORKSPACE = sys.argv[1:3]
CHECKS = []
LIVE_TIMEOUT = 15
LIVE_BUDGET = 20
FIELDS = ("item", "quantity", "unit", "urgency", "requester")


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def check(name, operation, optional=False):
    # An optional check is the hidden bonus of a mission: it can only add, it never fails the run.
    flag = {"optional": True} if optional else {}
    try:
        detail = operation()
        CHECKS.append({"name": name, "passed": True, "detail": detail or "Scripted adapter requests and the returned results verified.", **flag})
    except Exception as error:
        CHECKS.append({"name": name, "passed": False, "detail": f"{type(error).__name__}: {error}"[:1500], **flag})


class EnvironmentBlocked(Exception):
    pass


class Adapter(socketserver.ThreadingMixIn, HTTPServer):
    """OpenAI-compatible loopback server that answers from a script; the last step repeats forever."""
    daemon_threads = True

    def __init__(self, script):
        super().__init__(("127.0.0.1", 0), AdapterHandler)
        self.script = list(script)
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
            step = server.script[min(len(server.requests), len(server.script)) - 1]
            index = len(server.requests)
        if not self.path.endswith("/chat/completions"):
            self.reply(404, {"error": {"message": "unknown route", "type": "invalid_request_error"}})
            return
        message = {"role": "assistant", "content": step.get("content")}
        if "refusal" in step:
            message["refusal"] = step["refusal"]
        prompt_tokens = 40 + 3 * len(body["messages"])
        produced = len(str(step.get("content") or "").split()) + 1
        self.reply(200, {
            "id": f"chatcmpl-adapter-{index}", "object": "chat.completion", "created": int(time.time()), "model": body["model"],
            "choices": [{"index": 0, "message": message, "finish_reason": step.get("finish_reason", "stop")}],
            "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": produced, "total_tokens": prompt_tokens + produced},
            "system_fingerprint": "fp_scripted_adapter",
        })


def serve(script):
    server = Adapter(script)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
    thread.start()
    return server, thread


def stop(server, thread):
    server.shutdown()
    server.server_close()
    thread.join(timeout=1)


RANDOM = random.Random()
NAMES = ["Mara", "Teo", "Ilse", "Nadia", "Oskar", "Priya", "Yusuf", "Lena"]
CATALOG = [
    {"item": "water filter", "unit": "piece", "max_quantity": RANDOM.randint(35, 70)},
    {"item": "fuse", "unit": "box", "max_quantity": RANDOM.randint(10, 25)},
    {"item": "diesel", "unit": "litre", "max_quantity": RANDOM.randint(150, 300)},
    {"item": "rice", "unit": "kilogram", "max_quantity": RANDOM.randint(60, 120)},
]
MAXIMUM = CATALOG[0]["max_quantity"]
TEXT = f"We need {RANDOM.randint(5, 30)} water filters at the north relay by tomorrow morning, this is urgent. - {RANDOM.choice(NAMES)}"


def record(**overrides):
    base = {"item": "water filter", "quantity": RANDOM.randint(2, MAXIMUM - 1), "unit": "piece", "urgency": "high", "requester": RANDOM.choice(NAMES)}
    base.update(overrides)
    return base


def message_text(body):
    return "\n".join(str(message.get("content") or "") for message in body.get("messages", []) if isinstance(message, dict))


def schema_errors(errors):
    return [error for error in errors if isinstance(error, str) and error.startswith("schema: ")]


def domain_errors(errors):
    return [error for error in errors if isinstance(error, str) and error.startswith("domain: ")]


def reference_valid(value, catalog):
    """Verify's own independent acceptance test for a live record: shape, enums and catalog."""
    if not isinstance(value, dict) or set(value) - set(FIELDS) - {"notes"} or any(field not in value for field in FIELDS):
        return False
    if not isinstance(value["quantity"], int) or isinstance(value["quantity"], bool) or value["quantity"] < 1:
        return False
    if value["urgency"] not in ("low", "normal", "high") or value["unit"] not in ("piece", "box", "litre", "kilogram"):
        return False
    if "notes" in value and not isinstance(value["notes"], str):
        return False
    entry = next((entry for entry in catalog if entry["item"] == str(value["item"]).strip().lower()), None)
    return entry is not None and entry["unit"] == value["unit"] and value["quantity"] <= entry["max_quantity"]


def trial():
    require(MISSION == "record", "Unknown mission")
    sys.path.insert(0, WORKSPACE)
    spec = importlib.util.spec_from_file_location("candidate_record", os.path.join(WORKSPACE, "extract.py"))
    if spec is None or spec.loader is None:
        raise ImportError("Cannot load extract.py")
    candidate = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = candidate
    spec.loader.exec_module(candidate)
    for name in ("load_schema", "validate", "extract"):
        require(callable(getattr(candidate, name, None)), f"extract.py must define {name}(...)")

    def run(server, text=TEXT, **options):
        options.setdefault("max_repairs", 1)
        before = len(server.requests)
        result = candidate.extract(text, base_url=server.base_url, model="relay-small", catalog=CATALOG, **options)
        require(isinstance(result, dict), "extract must return a result dict")
        for key in ("ok", "record", "errors", "attempts", "schema_enforced"):
            require(key in result, f"The result is missing the key {key!r}")
        require(isinstance(result["ok"], bool), "ok must be a boolean")
        require(isinstance(result["errors"], list) and all(isinstance(item, str) for item in result["errors"]), "errors must be a list of strings")
        require(isinstance(result["attempts"], list) and result["attempts"], "attempts must be a non-empty list")
        for attempt in result["attempts"]:
            require(isinstance(attempt, dict) and attempt.get("kind") in ("initial", "repair"), f"Each attempt needs kind initial or repair, got {attempt!r}")
            require(isinstance(attempt.get("errors"), list) and isinstance(attempt.get("content"), str), f"Each attempt carries errors (list) and content (string), got {attempt!r}")
        require(len(server.requests) - before == len(result["attempts"]), f"{len(server.requests) - before} requests were sent but {len(result['attempts'])} attempts were logged")
        if result["ok"]:
            require(isinstance(result["record"], dict) and result["errors"] == [] and result["attempts"][-1]["errors"] == [], "ok=true means a record and no errors")
        else:
            require(result["record"] is None and result["errors"] and result["errors"] == result["attempts"][-1]["errors"], "ok=false means record null and the last attempt's errors")
        return result

    def schema_and_validator():
        schema = candidate.load_schema()
        require(isinstance(schema, dict) and schema.get("type") == "object", "load_schema() must return the published object schema")
        properties = schema.get("properties") or {}
        require(all(field in properties for field in FIELDS) and "notes" in properties, f"The schema publishes {FIELDS} and notes")
        require(set(FIELDS) <= set(schema.get("required") or []) and "notes" not in schema["required"], "The five record fields are required, notes is optional")
        require(schema.get("additionalProperties") is False, "additionalProperties must be false")
        good = record()
        require(candidate.validate(good, CATALOG) == [], f"A valid record must produce no errors, got {candidate.validate(good, CATALOG)!r}")
        cases = [
            (dict(good, quantity="12"), "quantity", "a string quantity"),
            (dict(good, quantity=True), "quantity", "a boolean quantity (bool is not an integer)"),
            (dict(good, quantity=0), "quantity", "quantity 0 (schema minimum 1)"),
            ({key: value for key, value in good.items() if key != "requester"}, "requester", "a missing requester"),
            (dict(good, urgency="asap"), "urgency", "an urgency outside the enum"),
            (dict(good, warehouse="north"), "warehouse", "an extra field"),
            (dict(good, item=""), "item", "an empty item (minLength 1)"),
            (dict(good, quantity=12.0), "quantity", "quantity 12.0 (a number with a fractional part is not an integer)"),
            (dict(good, notes=None), "notes", "notes null (the optional field, when present, must be a string)"),
            (dict(good, notes=7), "notes", "notes 7 (the optional field, when present, must be a string)"),
        ]
        capped = copy.deepcopy(schema)
        capped["properties"]["quantity"]["maximum"] = MAXIMUM - 1
        cases.append((dict(good, quantity=MAXIMUM), "quantity", f"quantity {MAXIMUM} above a schema maximum of {MAXIMUM - 1}"))
        for bad, field, label in cases:
            errors = candidate.validate(bad, CATALOG, schema=capped if "schema maximum" in label else None)
            require(isinstance(errors, list) and errors and all(isinstance(item, str) for item in errors), f"{label}: validate must return a non-empty list of strings, got {errors!r}")
            require(len(schema_errors(errors)) == len(errors), f"{label}: every error starts with 'schema: ', got {errors!r}")
            require(any(field in error for error in errors), f"{label}: an error must name the field {field!r}, got {errors!r}")
        errors = candidate.validate(["not", "an", "object"], CATALOG)
        require(errors and len(schema_errors(errors)) == len(errors), f"A non-object value is a schema error, got {errors!r}")
        require(candidate.validate(dict(good, notes="leave at the gate"), CATALOG) == [], "notes is optional and allowed")
        return "schema.json published; eleven syntactic faults (types, bounds, enum, extra and null notes, maximum) reported with the schema: prefix and the field name."
    check("The published schema and the validator report syntactic errors", schema_and_validator)

    def domain():
        unknown = candidate.validate(record(item="plasma coil"), CATALOG)
        require(unknown and len(domain_errors(unknown)) == len(unknown) and any("plasma coil" in error for error in unknown), f"An unknown item is a domain error naming the item, got {unknown!r}")
        unit = candidate.validate(record(unit="box"), CATALOG)
        require(unit and len(domain_errors(unit)) == len(unit) and any("unit" in error for error in unit), f"A unit that differs from the catalog unit is a domain error, got {unit!r}")
        over = candidate.validate(record(quantity=MAXIMUM + 1), CATALOG)
        require(over and len(domain_errors(over)) == len(over) and any("quantity" in error for error in over), f"quantity {MAXIMUM + 1} over the catalog maximum {MAXIMUM} is a domain error, got {over!r}")
        require(candidate.validate(record(quantity=MAXIMUM), CATALOG) == [], f"quantity {MAXIMUM} equals the catalog maximum and is accepted")
        mixed = candidate.validate(record(item="plasma coil", quantity="12"), CATALOG)
        require(mixed and len(schema_errors(mixed)) == len(mixed), f"With schema errors present, only schema errors are reported, got {mixed!r}")
        require(candidate.validate(record(item=" Water Filter "), CATALOG) == [], "Item names are compared case-insensitively after trimming")
        return f"Unknown item, unit mismatch and quantity {MAXIMUM + 1} > {MAXIMUM} reported as domain: errors; schema errors reported alone."
    check("Domain errors are reported separately from schema errors", domain)

    def absent_item():
        bad = record(item="plasma coil")
        server, thread = serve([{"content": json.dumps(bad)}])
        try:
            result = run(server, max_repairs=1)
            require(result["ok"] is False, "A well-formed record naming an item absent from the catalog must not be accepted")
            require(len(server.requests) == 2, f"Expected one repair request after the rejected record, saw {len(server.requests)} requests")
            require(domain_errors(result["errors"]) and not schema_errors(result["errors"]), f"The failure must carry domain errors only, got {result['errors']!r}")
            return "A schema-valid record for 'plasma coil' was rejected twice and the result is ok=false."
        finally:
            stop(server, thread)
    check("A well-formed record naming an item absent from the catalog is rejected", absent_item)

    def repaired():
        good = record()
        faults = [
            ("malformed JSON", {"content": json.dumps(good)[:-1] + ",}"}, None),
            ("a JSON array", {"content": json.dumps([good])}, None),
            ("truncated output", {"content": json.dumps(good), "finish_reason": "length"}, ("length", "truncat")),
            ("an extra field", {"content": json.dumps(dict(good, warehouse="north"))}, ("warehouse",)),
            ("an unknown item", {"content": json.dumps(dict(good, item="plasma coil"))}, ("plasma coil",)),
        ]
        for label, step, needles in faults:
            fixed = record()
            server, thread = serve([step, {"content": json.dumps(fixed)}])
            try:
                result = run(server, max_repairs=1)
                require(result["ok"] is True and result["record"] == fixed, f"{label}: after one repair the corrected record must be returned, got {result!r}"[:600])
                require(len(server.requests) == 2 and len(result["attempts"]) == 2, f"{label}: expected exactly two requests, saw {len(server.requests)}")
                first, second = result["attempts"]
                require(first["kind"] == "initial" and second["kind"] == "repair", f"{label}: attempt kinds must be initial then repair")
                require(first["errors"] and second["errors"] == [], f"{label}: the first attempt must carry its errors, the repair none, got {result['attempts']!r}"[:600])
                require(first["finish_reason"] == step.get("finish_reason", "stop"), f"{label}: finish_reason must be the response value")
                if needles:
                    require(any(any(needle in error.lower() for needle in needles) for error in first["errors"]), f"{label}: the error must mention {needles}, got {first['errors']!r}")
            finally:
                stop(server, thread)
        server, thread = serve([{"content": json.dumps(good)}])
        try:
            result = run(server, max_repairs=2)
            require(result["ok"] and len(server.requests) == 1, "A valid first answer needs no repair request")
        finally:
            stop(server, thread)
        return "Malformed, array, truncated, extra-field and unknown-item outputs each rejected once and repaired on the second request."
    check("Scripted adapter: malformed, truncated, extra-field and unknown-item outputs are repaired within the bound", repaired)

    def repair_request():
        bad = record(item="plasma coil", quantity=MAXIMUM + 5)
        content = json.dumps(bad)
        expected = candidate.validate(bad, CATALOG)
        require(expected, "The rejected record must produce errors from validate()")
        server, thread = serve([{"content": content}, {"content": json.dumps(record())}])
        try:
            result = run(server, max_repairs=1)
            require(result["ok"] and len(server.requests) == 2, "The scripted repair must succeed on the second request")
            first, second = (message_text(item["body"]) for item in server.requests)
            require(TEXT in first, "The first request must carry the supply request text as message content")
            for entry in CATALOG:
                require(entry["item"] in first, f"The first request must name every catalog item in its messages; {entry['item']!r} is missing")
            for error in expected:
                require(error in second, f"The repair request must quote the validation error {error!r}")
            require(TEXT in second, "The repair request must carry the original supply request text")
            require(content in second, "The repair request must carry the rejected output verbatim")
            require(server.requests[1]["body"].get("model") == "relay-small", "The repair request goes to the same model")
            return f"The repair request quoted {len(expected)} validation errors, the rejected output and the original text."
        finally:
            stop(server, thread)
    check("The repair request carries the validation errors, the rejected output and the original text", repair_request)

    def bound():
        limit = RANDOM.choice([1, 2, 3])
        bad = {"content": json.dumps(record(item="plasma coil"))}
        server, thread = serve([bad])
        try:
            result = run(server, max_repairs=limit)
            require(result["ok"] is False and result["record"] is None, f"A never-correct model must end in ok=false with record null, got ok={result['ok']!r}")
            require(len(server.requests) == limit + 1, f"max_repairs={limit} allows exactly {limit + 1} requests, saw {len(server.requests)}")
            require(len(result["attempts"]) == limit + 1 and [attempt["kind"] for attempt in result["attempts"]] == ["initial"] + ["repair"] * limit, "attempts must list the initial request and each repair")
            require(result["errors"] and all(attempt["errors"] for attempt in result["attempts"]), "Every rejected attempt keeps its errors")
        finally:
            stop(server, thread)
        server, thread = serve([bad])
        try:
            result = run(server, max_repairs=0)
            require(result["ok"] is False and len(server.requests) == 1, f"max_repairs=0 means one request and a visible failure, saw {len(server.requests)} requests")
        finally:
            stop(server, thread)
        return f"max_repairs={limit}: exactly {limit + 1} requests, then ok=false with {len(result['errors'])} error(s); max_repairs=0: one request."
    check("The retry bound holds and exhaustion fails visibly", bound)

    def enforced():
        schema = candidate.load_schema()
        server, thread = serve([{"content": json.dumps(record())}])
        try:
            result = run(server, schema_enforced=True, max_repairs=0)
            body = server.requests[-1]["body"]
            response_format = body.get("response_format")
            require(isinstance(response_format, dict) and response_format.get("type") == "json_schema", f"schema_enforced=True must send response_format.type json_schema, got {response_format!r}")
            wrapper = response_format.get("json_schema")
            require(isinstance(wrapper, dict) and isinstance(wrapper.get("name"), str) and wrapper["name"], "response_format.json_schema needs a name")
            require(wrapper.get("schema") == schema, "response_format.json_schema.schema must equal the published schema")
            require(result["schema_enforced"] is True, "The result reports schema_enforced=true")
            result = run(server, schema_enforced=False, max_repairs=0)
            require("response_format" not in server.requests[-1]["body"], "Prompt-only mode sends no response_format at all")
            require(result["schema_enforced"] is False, "The result reports schema_enforced=false")
            return "Schema-enforced request carried response_format json_schema with the published schema; prompt-only carried none."
        finally:
            stop(server, thread)
    check("Schema-enforced requests carry response_format json_schema; prompt-only requests carry none", enforced)

    def transfer():
        extended = copy.deepcopy(candidate.load_schema())
        extended["properties"]["deliver_to"] = {"type": "string", "minLength": 1}
        with_field = record(deliver_to=f"relay {RANDOM.randint(2, 9)}")
        rejected = candidate.validate(with_field, CATALOG)
        require(rejected and len(schema_errors(rejected)) == len(rejected) and any("deliver_to" in error for error in rejected), f"The published schema rejects deliver_to as an extra field, got {rejected!r}")
        require(candidate.validate(with_field, CATALOG, schema=extended) == [], "validate(..., schema=extended) accepts the new optional field")
        require(candidate.validate(record(), CATALOG, schema=extended) == [], "The new field is optional: a record without it is still valid")
        wrong = candidate.validate(dict(with_field, deliver_to=7), CATALOG, schema=extended)
        require(wrong and any("deliver_to" in error for error in schema_errors(wrong)), f"The new field is type-checked, got {wrong!r}")
        server, thread = serve([{"content": json.dumps(with_field)}])
        try:
            result = run(server, schema=extended, schema_enforced=True, max_repairs=0)
            require(result["ok"] and result["record"] == with_field, f"extract(schema=extended) must accept and preserve deliver_to, got {result!r}"[:600])
            require(server.requests[-1]["body"].get("response_format", {}).get("json_schema", {}).get("schema") == extended, "The request must carry the extended schema")
            return "deliver_to added as an optional string: rejected by the published schema, accepted, type-checked and preserved with the extended one."
        finally:
            stop(server, thread)
    check("Transfer: a new optional field in the schema is accepted and preserved", transfer)

    def refusal():
        text = f"I cannot extract that request ({RANDOM.randint(100, 999)})."
        server, thread = serve([{"content": None, "refusal": text}])
        try:
            result = run(server, schema_enforced=True, max_repairs=1)
            require(result["ok"] is False and len(server.requests) == 2, "A refusal is a failed attempt that counts against the bound")
            require(any("refus" in error.lower() and text in error for error in result["errors"]), f"The error must say the model refused and quote the refusal, got {result['errors']!r}")
            return "A message with refusal and null content was reported as a refusal, not parsed."
        finally:
            stop(server, thread)
    check("bonus: a refusal is reported as a visible failure, never parsed as a record", refusal, optional=True)

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
        ping = json.dumps({"model": model, "messages": [{"role": "user", "content": "Reply with the single word OK."}], "max_tokens": 4, "temperature": 0}).encode("utf-8")
        request = urllib.request.Request(base_url.rstrip("/") + "/chat/completions", data=ping, headers={"Content-Type": "application/json"}, method="POST")
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=LIVE_TIMEOUT) as response:
                raw = response.read()
            try:
                json.loads(raw.decode("utf-8"))
            except ValueError:
                raise EnvironmentBlocked(f"{base_url} answered the warm-up request with something that is not JSON: {raw[:120]!r}. Point llm.json at an OpenAI-compatible /v1 endpoint.")
        except EnvironmentBlocked:
            raise
        except urllib.error.HTTPError as error:
            raise EnvironmentBlocked(f"{base_url} answered HTTP {error.code} for model {model!r}: {error.read(300).decode('utf-8', 'replace')}")
        except Exception as error:
            raise EnvironmentBlocked(f"{base_url} did not answer within {LIVE_TIMEOUT} s ({type(error).__name__}: {error}). Start or warm up the model with demo.py, then verify again.")
        ping_seconds = time.perf_counter() - started
        fixtures = [
            ("We need 12 water filters for the north relay by tomorrow, this is urgent. - Mara", "water filter", 12),
            ("Could you send 3 boxes of fuses with the next convoy? No rush. Teo", "fuse", 3),
            ("URGENT: diesel, 40 litres, generator two is dry. Ilse, relay 4", "diesel", 40),
        ][: 3 if ping_seconds < 2 else 1]
        counts = {}
        requests = 0
        for enforced in (False, True):
            tally = {"schema": 0, "domain": 0, "exact": 0}
            for text, item, quantity in fixtures:
                result = candidate.extract(text, base_url=base_url, model=model, catalog=CATALOG, schema_enforced=enforced, max_repairs=0, max_tokens=int(config.get("max_tokens") or 256))
                require(isinstance(result, dict) and isinstance(result.get("attempts"), list) and len(result["attempts"]) == 1, "max_repairs=0 means one attempt per fixture")
                requests += 1
                errors = result.get("errors") or []
                if result.get("ok"):
                    require(reference_valid(result["record"], CATALOG), f"extract reported ok for a record Verify does not accept: {result['record']!r}")
                    tally["schema"] += 1
                    tally["domain"] += 1
                    tally["exact"] += int(str(result["record"]["item"]).strip().lower() == item and result["record"]["quantity"] == quantity)
                elif not schema_errors(errors):
                    tally["schema"] += 1
            counts["schema-enforced" if enforced else "prompt-only"] = tally
        seconds = time.perf_counter() - started
        n = len(fixtures)
        summary = "; ".join(f"{mode}: {tally['schema']}/{n} schema-valid, {tally['domain']}/{n} catalog-valid, {tally['exact']}/{n} exact item and quantity" for mode, tally in counts.items())
        return f"Live: {model} at {base_url}; {requests} extraction requests in {seconds:.1f} s. {summary}. These are measurements of one run with max_repairs=0, not a verdict on the model."

    def live_bounded():
        # The learner's HTTP timeout is theirs; Verify's own budget for the whole live section is LIVE_BUDGET seconds.
        outcome = {}

        def worker():
            try:
                outcome["detail"] = live()
            except BaseException as error:  # noqa: BLE001 - carried to the main thread
                outcome["error"] = error
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        thread.join(timeout=LIVE_BUDGET)
        if thread.is_alive():
            raise EnvironmentBlocked(f"The live measurement did not finish within {LIVE_BUDGET} s; the endpoint in llm.json is too slow for this check. Warm the model up with demo.py or use a smaller one, then verify again.")
        if "error" in outcome:
            raise outcome["error"]
        return outcome["detail"]

    try:
        CHECKS.append({"name": "Live run: validity of prompt-only versus schema-enforced output", "passed": True, "detail": live_bounded()})
    except EnvironmentBlocked as blocked:
        CHECKS.append({"name": "Environment blocked", "passed": False, "detail": str(blocked)[:1500]})
    except Exception as error:
        CHECKS.append({"name": "Live run: validity of prompt-only versus schema-enforced output", "passed": False, "detail": f"{type(error).__name__}: {error}"[:1500]})


try:
    trial()
except Exception as error:
    CHECKS.append({"name": "Load extractor", "passed": False, "detail": f"{type(error).__name__}: {error}"[:1500]})
print(json.dumps({"checks": CHECKS}))
sys.exit(0 if CHECKS and all(item["passed"] for item in CHECKS if not item.get("optional")) else 1)
