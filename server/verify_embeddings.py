"""Embedding store checks for the Embeddings mission; run outside the learner workspace.

The scripted adapter below is a labeled test tool: it speaks the OpenAI-compatible /embeddings
contract and answers with deterministic unit vectors (salted hashed bag-of-words projections, one
dimension per model name), recording every request body. Expected top-k lists are recomputed here
with exact arithmetic from the same vectors. The only live evaluation is the final measurement
against the embedding endpoint the learner configured in llm.json, and it reports numbers only.
"""
import hashlib
import importlib.util
import struct
import json
import math
import os
import random
import socketserver
import sqlite3
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from decimal import Decimal, getcontext
from fractions import Fraction
from http.server import BaseHTTPRequestHandler, HTTPServer

MISSION, WORKSPACE = sys.argv[1:3]
CHECKS = []
LIVE_TIMEOUT = 15
MAX_BATCH = 16
SCRATCH = (".verify-store.sqlite", ".verify-hand.sqlite", ".verify-batches.sqlite", ".verify-live.sqlite")
TOLERANCE = Fraction(1, 10**9)
getcontext().prec = 40


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def check(name, operation, optional=False):
    # An optional check is the hidden bonus of a mission: it can only add, it never fails the run.
    flag = {"optional": True} if optional else {}
    try:
        detail = operation()
        CHECKS.append({"name": name, "passed": True, "detail": detail or "Scripted adapter requests and the store's answers verified.", **flag})
    except Exception as error:
        CHECKS.append({"name": name, "passed": False, "detail": f"{type(error).__name__}: {error}"[:1500], **flag})


class EnvironmentBlocked(Exception):
    pass


class Adapter(socketserver.ThreadingMixIn, HTTPServer):
    """OpenAI-compatible /embeddings loopback server with deterministic unit vectors per model name."""
    daemon_threads = True

    def __init__(self, *, salt, dims, max_inputs=None, shuffle=False):
        super().__init__(("127.0.0.1", 0), AdapterHandler)
        self.salt, self.dims, self.max_inputs, self.shuffle = salt, dict(dims), max_inputs, shuffle
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

    def vector(self, model, text):
        dim = self.dims[model]
        raw = [0.0] * dim
        for word in text.lower().split():
            digest = hashlib.sha256(f"{self.salt}:{model}:{word}".encode("utf-8")).digest()
            raw[digest[0] % dim] += (1.0 if digest[1] & 1 else -1.0) * (1.0 + digest[2] / 255)
        norm = math.sqrt(sum(value * value for value in raw))
        if norm == 0:
            raw[0], norm = 1.0, 1.0
        return [value / norm for value in raw]

    def tokens(self, text):
        return len(text.split()) + 2


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
            require(isinstance(body, dict), "object body required")
        except Exception as error:
            self.reply(400, {"error": {"message": f"invalid request: {error}", "type": "invalid_request_error"}})
            return
        with server.lock:
            server.requests.append({"path": self.path, "headers": dict(self.headers), "body": body})
        if not self.path.endswith("/embeddings"):
            self.reply(404, {"error": {"message": "unknown route", "type": "invalid_request_error"}})
            return
        model = body.get("model")
        if model not in server.dims:
            self.reply(404, {"error": {"message": f"model {model!r} not found", "type": "invalid_request_error", "code": "model_not_found"}})
            return
        texts = body.get("input")
        if isinstance(texts, str):
            texts = [texts]
        if not isinstance(texts, list) or not texts or any(not isinstance(text, str) or not text.strip() for text in texts):
            self.reply(400, {"error": {"message": "'$.input' must be a non-empty string or a list of non-empty strings", "type": "invalid_request_error", "param": "input"}})
            return
        if server.max_inputs is not None and len(texts) > server.max_inputs:
            self.reply(400, {"error": {"message": f"'$.input' is invalid. The maximum number of inputs per request is {server.max_inputs}, got {len(texts)}", "type": "invalid_request_error", "param": "input"}})
            return
        data = [{"object": "embedding", "index": index, "embedding": server.vector(model, text)} for index, text in enumerate(texts)]
        if server.shuffle:
            # Entries carry their index on purpose: the contract orders by index, not by position.
            random.Random(len(server.requests)).shuffle(data)
        total = sum(server.tokens(text) for text in texts)
        self.reply(200, {"object": "list", "data": data, "model": model, "usage": {"prompt_tokens": total, "total_tokens": total}})


def serve(**options):
    server = Adapter(**options)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
    thread.start()
    return server, thread


def stop(server, thread):
    server.shutdown()
    server.server_close()
    thread.join(timeout=1)


def exact_cosine(a, b):
    """Cosine with exact dot and squared norms; the square roots are taken at 40 digits."""
    dot = sum(Fraction(x) * Fraction(y) for x, y in zip(a, b))
    norm_a = sum(Fraction(x) * Fraction(x) for x in a)
    norm_b = sum(Fraction(y) * Fraction(y) for y in b)
    if norm_a == 0 or norm_b == 0:
        return Decimal(0)
    return Decimal(dot.numerator) / Decimal(dot.denominator) / (Decimal(norm_a.numerator) / Decimal(norm_a.denominator)).sqrt() / (Decimal(norm_b.numerator) / Decimal(norm_b.denominator)).sqrt()


def looks_like_old_vector(cell, dimension):
    """A cell holding a unit vector of the old dimension: a JSON list or a float64/float32 BLOB that decodes to one."""
    values = None
    if isinstance(cell, str) and cell.startswith("["):
        try:
            parsed = json.loads(cell)
        except ValueError:
            return False
        if isinstance(parsed, list) and len(parsed) == dimension and all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in parsed):
            values = [float(value) for value in parsed]
    elif isinstance(cell, bytes):
        for code in ("d", "f"):
            if len(cell) == dimension * struct.calcsize(code):
                values = list(struct.unpack(f"<{dimension}{code}", cell))
                break
    if values is None or not all(math.isfinite(value) for value in values):
        return False
    norm = math.sqrt(sum(value * value for value in values))
    return 0.5 <= norm <= 2.0


def reference_topk(query, rows, k):
    scored = sorted(((exact_cosine(query, vector), passage_id) for passage_id, vector in rows), key=lambda item: (-item[0], item[1]))
    return scored[:k]


def same_ranking(actual, reference, label):
    require(isinstance(actual, list), f"{label}: search must return a list, got {type(actual).__name__}")
    require(len(actual) == len(reference), f"{label}: expected {len(reference)} results, got {len(actual)}")
    for position, (item, (score, passage_id)) in enumerate(zip(actual, reference)):
        require(isinstance(item, (list, tuple)) and len(item) == 2, f"{label}: result {position} must be an (id, score) pair, got {item!r}")
        got_id, got_score = item
        require(got_id == passage_id, f"{label}: position {position} is {got_id!r}, the reference has {passage_id!r} (score {float(score):.6f}); score desc, then id asc")
        require(isinstance(got_score, (int, float)) and not isinstance(got_score, bool) and math.isfinite(got_score), f"{label}: score for {got_id!r} must be a finite number, got {got_score!r}")
        require(abs(Fraction(got_score) - Fraction(score)) <= TOLERANCE, f"{label}: score for {got_id!r} is {got_score!r}, the reference is {float(score)!r}")


PASSAGE_TEXTS = [
    "Runbook: restart the relay after a power dip and confirm the heartbeat within two minutes.",
    "Incident report: the water filter stock dropped below the reserve line during the storm week.",
    "Runbook: reserve supplies only with the operator's own permissions; never on behalf of another outpost.",
    "Incident report: fuses for relay four were ordered twice because two operators filed the same request.",
    "Runbook: a supply request names the item, the quantity, the unit and who asked for it.",
    "Incident report: the relay heartbeat stopped for eleven minutes after the generator switch.",
    "Runbook: incident reports are filed within a shift and cite the runbook that applied.",
    "Runbook: restart the relay after a power dip and confirm the heartbeat within two minutes.",
    "Incident report: the morning shift found the archive index pointing at a deleted runbook.",
    "Runbook: filters are counted by the box, fuses by the piece, fuel by the litre.",
]
QUERIES = [
    "how do I restart the relay after a power dip",
    "filter stock below the reserve line",
    "fuses ordered twice by two operators",
    "who may reserve supplies for another outpost",
]
HAND_VECTORS = {"hv-a": [3.0, 4.0, 0.0], "hv-b": [0.0, 3.0, 4.0], "hv-c": [12.0, 5.0, 0.0], "hv-d": [0.0, 0.0, 2.0], "hv-e": [4.0, 3.0, 0.0]}


def trial():
    require(MISSION == "embeddings", "Unknown mission")
    sys.path.insert(0, WORKSPACE)
    spec = importlib.util.spec_from_file_location("candidate_embeddings", os.path.join(WORKSPACE, "store.py"))
    if spec is None or spec.loader is None:
        raise ImportError("Cannot load store.py")
    candidate = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = candidate
    spec.loader.exec_module(candidate)
    for name in ("EmbeddingStore", "ModelMismatch", "DimensionMismatch"):
        require(isinstance(getattr(candidate, name, None), type), f"store.py must define the class {name}")
    for name in ("embed", "cosine"):
        require(callable(getattr(candidate, name, None)), f"store.py must define {name}(...)")
    require(issubclass(candidate.ModelMismatch, ValueError) and issubclass(candidate.DimensionMismatch, ValueError), "ModelMismatch and DimensionMismatch must subclass ValueError")

    rng = random.Random()
    salt = rng.randrange(10**9)
    offset = rng.randrange(10, 80)
    passages = [{"id": f"rb-{offset + index:03d}", "text": text} for index, text in enumerate(PASSAGE_TEXTS)]
    version_a, version_b = f"2026.{rng.randrange(1, 9)}", f"2027.{rng.randrange(1, 9)}"
    dims = {"relay-embed-a": 8, "relay-embed-b": 12}
    store_path = os.path.join(WORKSPACE, ".verify-store.sqlite")
    for stale in (store_path, store_path + "-journal", store_path + "-wal", store_path + "-shm"):
        if os.path.exists(stale):
            os.remove(stale)

    def refused(operation, *classes):
        try:
            operation()
        except classes:
            return True
        return False

    def cosine_values():
        cases = [
            (([3, 4], [4, 3]), Decimal("0.96")),
            (([1.0, 2.0, 2.0], [2.0, 0.0, 1.0]), exact_cosine([1, 2, 2], [2, 0, 1])),
            (([1.5, -2.0, 0.5], [-3.0, 4.0, -1.0]), Decimal(-1)),
            (([0.0, 0.0, 0.0], [2.0, 1.0, 7.0]), Decimal(0)),
            (([0.2, 0.0, 0.0, 0.0], [0.0, 0.0, 9.0, 0.0]), Decimal(0)),
            (([0.6, 0.8], [0.6, 0.8]), Decimal(1)),
        ]
        for (a, b), wanted in cases:
            got = candidate.cosine(a, b)
            require(isinstance(got, (int, float)) and not isinstance(got, bool) and math.isfinite(got), f"cosine({a}, {b}) must be a finite number, got {got!r}")
            require(abs(Fraction(got) - Fraction(wanted)) <= TOLERANCE, f"cosine({a}, {b}) = {got!r}, expected {float(wanted)!r}")
        return "Six hand-computed cosines matched within 1e-9, including the zero vector and an opposite vector."
    check("Cosine similarity matches hand-computed values", cosine_values)

    store_box = {}

    def ingest():
        server, thread = serve(salt=salt, dims=dims)
        try:
            vectors = candidate.embed([passage["text"] for passage in passages[:3]], base_url=server.base_url, model="relay-embed-a")
            require(isinstance(vectors, list) and len(vectors) == 3, f"embed must return one vector per text, got {type(vectors).__name__} of length {len(vectors) if isinstance(vectors, list) else '?'}")
            for passage, vector in zip(passages[:3], vectors):
                wanted = server.vector("relay-embed-a", passage["text"])
                require(isinstance(vector, list) and len(vector) == 8, f"embed vectors must be lists of 8 floats for relay-embed-a, got {vector!r}")
                require(all(abs(Fraction(x) - Fraction(y)) <= TOLERANCE for x, y in zip(vector, wanted)), f"embed returned a vector that is not data[i].embedding for {passage['id']}")
            require(len(server.requests) == 1, f"embed of 3 texts must send exactly one request, saw {len(server.requests)}")
            body = server.requests[0]["body"]
            require(server.requests[0]["path"].endswith("/v1/embeddings"), f"The request must go to {{base_url}}/embeddings, saw {server.requests[0]['path']!r}")
            require(body.get("model") == "relay-embed-a", f"The request body must carry the model id, saw {body.get('model')!r}")
            require(body.get("input") == [passage["text"] for passage in passages[:3]], "The request body must carry input as the list of texts in order")
            del server.requests[:]
            store = candidate.EmbeddingStore(store_path)
            store_box["store"] = store
            batches = store.ingest(passages, base_url=server.base_url, model="relay-embed-a", version=version_a)
            require(len(server.requests) == 1, f"ingest of {len(passages)} passages (MAX_BATCH {MAX_BATCH}) must send exactly one request, saw {len(server.requests)}")
            body = server.requests[0]["body"]
            require(body.get("input") == [passage["text"] for passage in passages], "ingest must send every passage text in passage order as input")
            meta = store.metadata()
            wanted_meta = {"model": "relay-embed-a", "version": version_a, "dimension": 8, "passages": len(passages)}
            require(isinstance(meta, dict) and {key: meta.get(key) for key in wanted_meta} == wanted_meta, f"metadata() must be {wanted_meta}, got {meta!r}")
            expected_tokens = sum(server.tokens(passage["text"]) for passage in passages)
            recorded = store.batches()
            require(isinstance(batches, list) and batches == recorded, "ingest must return the batch records it stored; batches() returns them in order")
            require(len(recorded) == 1, f"One request means one batch record, got {len(recorded)}")
            batch = recorded[0]
            wanted_batch = {"model": "relay-embed-a", "version": version_a, "dimension": 8, "inputs": len(passages), "prompt_tokens": expected_tokens, "total_tokens": expected_tokens}
            require(isinstance(batch, dict) and {key: batch.get(key) for key in wanted_batch} == wanted_batch, f"The batch record must be {wanted_batch}, got {batch!r}")
            return f"One /embeddings request for {len(passages)} passages; metadata {wanted_meta}; usage {expected_tokens} tokens recorded for the batch."
        finally:
            stop(server, thread)
    check("Ingest sends the embeddings contract and records model, version, dimension and usage per batch", ingest)

    def topk():
        store = store_box.get("store")
        require(store is not None, "The ingest check must pass first")
        server, thread = serve(salt=salt, dims=dims)
        try:
            rows = [(passage["id"], server.vector("relay-embed-a", passage["text"])) for passage in passages]
            trials = 0
            for query_text in QUERIES + [PASSAGE_TEXTS[0]]:
                query = server.vector("relay-embed-a", query_text)
                for k in (1, 3, 5, len(passages), len(passages) + 7):
                    actual = store.search(query, k, model="relay-embed-a")
                    same_ranking(actual, reference_topk(query, rows, k), f"query {query_text!r} k={k}")
                    trials += 1
            duplicate = store.search(server.vector("relay-embed-a", PASSAGE_TEXTS[0]), 2, model="relay-embed-a")
            require([item[0] for item in duplicate] == [passages[0]["id"], passages[7]["id"]], f"Two passages with identical text tie; the tie breaks by id ascending, got {duplicate!r}")
            require(refused(lambda: store.search(rows[0][1], 0, model="relay-embed-a"), ValueError), "k below 1 is a ValueError")
            return f"{trials} top-k lists matched the exact reference, including a tie broken by id and k beyond the store size."
        finally:
            stop(server, thread)
    check("Top-k by brute force equals the independent reference with the tie rule", topk)

    def hand_added():
        path = os.path.join(WORKSPACE, ".verify-hand.sqlite")
        if os.path.exists(path):
            os.remove(path)
        store = candidate.EmbeddingStore(path)
        try:
            require(store.metadata() is None, f"metadata() of an empty store must be None, got {store.metadata()!r}")
            require(store.search([1.0, 0.0, 0.0], 3, model="hand-embed") == [], "search on an empty store answers []")
            scale = {"hv-a": 0.5, "hv-b": 3.0, "hv-c": 0.25, "hv-d": 7.0, "hv-e": 1.0}
            ids = sorted(HAND_VECTORS)
            added = store.add([{"id": key, "text": f"hand vector {key}"} for key in ids], [[value * scale[key] for value in HAND_VECTORS[key]] for key in ids], model="hand-embed", version="h1")
            require(added == len(ids), f"add must return the number of passages stored ({len(ids)}), got {added!r}")
            meta = store.metadata()
            require(meta.get("model") == "hand-embed" and meta.get("version") == "h1" and meta.get("dimension") == 3 and meta.get("passages") == 5, f"metadata after add must describe the first vectors, got {meta!r}")
            rows = [(key, HAND_VECTORS[key]) for key in ids]
            for query, k in (([6.0, 8.0, 0.0], 5), ([0.0, 0.0, 1.0], 3), ([1.0, 1.0, 1.0], 2)):
                same_ranking(store.search(query, k, model="hand-embed"), reference_topk(query, rows, k), f"hand query {query} k={k}")
            top = store.search([6.0, 8.0, 0.0], 1, model="hand-embed")[0]
            require(abs(Fraction(top[1]) - 1) <= TOLERANCE, f"A query parallel to a stored vector scores 1.0 whatever the lengths, got {top!r}")
            return "Hand vectors of different lengths were ranked by cosine; a dot product on unit vectors is the same thing."
        finally:
            store.close()
    check("Vectors added by hand are compared by cosine whatever their length", hand_added)

    def refusals():
        store = store_box.get("store")
        require(store is not None, "The ingest check must pass first")
        server, thread = serve(salt=salt, dims=dims)
        try:
            before_meta = store.metadata()
            query_a = server.vector("relay-embed-a", QUERIES[1])
            before = store.search(query_a, 4, model="relay-embed-a")
            vector_b = server.vector("relay-embed-b", "a passage embedded by the other model")
            vector_a = server.vector("relay-embed-a", "a passage embedded by the same model")
            extra = [{"id": "rb-999", "text": "a passage that must not get in"}]
            require(refused(lambda: store.add(extra, [vector_b], model="relay-embed-b", version=version_b), candidate.ModelMismatch), "add with another model id must raise ModelMismatch")
            require(refused(lambda: store.add(extra, [vector_a], model="relay-embed-a", version=version_b), candidate.ModelMismatch), "add with another version of the same model must raise ModelMismatch")
            require(refused(lambda: store.add(extra, [vector_b], model="relay-embed-a", version=version_a), candidate.DimensionMismatch), "add with a 12-dimensional vector into an 8-dimensional store must raise DimensionMismatch")
            require(refused(lambda: store.add(extra, [vector_a[:7]], model="relay-embed-a", version=version_a), candidate.DimensionMismatch), "add with a 7-dimensional vector must raise DimensionMismatch")
            require(refused(lambda: store.search(vector_b, 3, model="relay-embed-b"), candidate.ModelMismatch), "search with another model id must raise ModelMismatch")
            require(refused(lambda: store.search(vector_a, 3, model="relay-embed-a", version=version_b), candidate.ModelMismatch), "search naming another version must raise ModelMismatch")
            require(refused(lambda: store.search(vector_b, 3, model="relay-embed-a"), candidate.DimensionMismatch), "search with a 12-dimensional query against an 8-dimensional store must raise DimensionMismatch")
            require(store.metadata() == before_meta, f"A refused add must leave the store unchanged: metadata {before_meta} became {store.metadata()}")
            require(store.search(query_a, 4, model="relay-embed-a") == before, "A refused add must not change search results")
            require(not any(item[0] == "rb-999" for item in store.search(query_a, 50, model="relay-embed-a")), "The refused passage must not be searchable")
            return "Four adds and three searches from another model, version or dimension were refused; the store stayed unchanged."
        finally:
            stop(server, thread)
    check("Vectors from another model, version or dimension are refused on add and on search", refusals)

    def persistence():
        store = store_box.get("store")
        require(store is not None, "The ingest check must pass first")
        server, thread = serve(salt=salt, dims=dims)
        try:
            query = server.vector("relay-embed-a", QUERIES[2])
            expected = store.search(query, 4, model="relay-embed-a")
            expected_batches = store.batches()
            require(isinstance(expected_batches, list) and len(expected_batches) == 1, f"batches() must still hold the one ingest record, got {expected_batches!r}")
            store.close()
            store_box.pop("store")
            with open(store_path, "rb") as file:
                require(file.read(16) == b"SQLite format 3\x00", f"{os.path.basename(store_path)} must be a SQLite database file")
            script = (
                "import json, sys\n"
                f"sys.path.insert(0, {WORKSPACE!r})\n"
                "import store as module\n"
                f"store = module.EmbeddingStore({store_path!r})\n"
                f"print(json.dumps({{'meta': store.metadata(), 'batches': store.batches(), 'top': [list(item) for item in store.search({query!r}, 4, model='relay-embed-a')]}}))\n"
            )
            completed = subprocess.run([sys.executable, "-I", "-B", "-c", script], cwd=WORKSPACE, capture_output=True, text=True, timeout=20)
            require(completed.returncode == 0, f"Reopening the store in a fresh process failed: {completed.stderr.strip()[-600:]}")
            payload = json.loads(completed.stdout.strip().splitlines()[-1])
            meta = payload["meta"] or {}
            require(meta.get("model") == "relay-embed-a" and meta.get("dimension") == 8 and meta.get("passages") == len(passages), f"A fresh process must read the same metadata from the file, got {payload['meta']!r}: vectors kept only in memory are lost")
            require([tuple(item) for item in payload["top"]] == [tuple(item) for item in expected], f"A fresh process must answer the same top-4: {payload['top']!r} vs {expected!r}")
            require(payload["batches"] == json.loads(json.dumps(expected_batches)), f"A fresh process must read the same batch records: {payload['batches']!r} vs {expected_batches!r}")
            reopened = candidate.EmbeddingStore(store_path)
            store_box["store"] = reopened
            require(reopened.search(query, 4, model="relay-embed-a") == expected, "Reopening in this process must answer the same top-4")
            return "The SQLite file answered the same metadata, batch records and top-4 after a reopen in a fresh Python process."
        finally:
            stop(server, thread)
            if "store" not in store_box:
                try:
                    store_box["store"] = candidate.EmbeddingStore(store_path)
                except Exception:
                    pass
    check("The store persists on disk and answers after a reopen in a fresh process", persistence)

    def migration():
        store = store_box.get("store")
        require(store is not None, "The persistence check must pass first")
        server, thread = serve(salt=salt, dims=dims)
        try:
            empty_path = os.path.join(WORKSPACE, ".verify-hand.sqlite")
            if os.path.exists(empty_path):
                os.remove(empty_path)
            empty = candidate.EmbeddingStore(empty_path)
            try:
                untouched = []
                count = empty.re_embed("relay-embed-b", lambda texts: untouched.append(list(texts)) or [], version=version_b)
                require(count == 0 and untouched == [], f"re_embed on an empty store returns 0 and never calls embed_fn; got {count!r} with calls {untouched!r}")
                require(empty.metadata() is None, f"An empty store stays empty after re_embed, metadata {empty.metadata()!r}")
            finally:
                empty.close()
            calls = []

            def embed_fn(texts):
                calls.append(list(texts))
                return candidate.embed(list(texts), base_url=server.base_url, model="relay-embed-b")

            count = store.re_embed("relay-embed-b", embed_fn, version=version_b)
            require(count == len(passages), f"re_embed must return the number of passages re-embedded ({len(passages)}), got {count!r}")
            require(calls and all(len(call) <= MAX_BATCH for call in calls), f"embed_fn is called with at most MAX_BATCH ({MAX_BATCH}) texts at a time, saw {[len(call) for call in calls]}")
            require([text for call in calls for text in call] == [passage["text"] for passage in passages], "embed_fn receives every passage text once, in id order")
            meta = store.metadata()
            wanted_meta = {"model": "relay-embed-b", "version": version_b, "dimension": 12, "passages": len(passages)}
            require({key: meta.get(key) for key in wanted_meta} == wanted_meta, f"metadata after re_embed must be {wanted_meta}, got {meta!r}")
            rows = [(passage["id"], server.vector("relay-embed-b", passage["text"])) for passage in passages]
            for query_text in QUERIES[:3]:
                query = server.vector("relay-embed-b", query_text)
                for k in (1, 4, len(passages)):
                    same_ranking(store.search(query, k, model="relay-embed-b", version=version_b), reference_topk(query, rows, k), f"re-embedded query {query_text!r} k={k}")
            everything = store.search(server.vector("relay-embed-b", QUERIES[0]), 100, model="relay-embed-b")
            require(len(everything) == len(passages) and len({item[0] for item in everything}) == len(passages), f"After re_embed the store holds exactly one vector per passage, search returned {len(everything)} rows")
            require(refused(lambda: store.search(server.vector("relay-embed-a", QUERIES[0]), 3, model="relay-embed-a"), candidate.ModelMismatch, candidate.DimensionMismatch), "A query from the old model must be refused after re_embed")
            store.close()
            store_box.pop("store")
            leftovers = 0
            connection = sqlite3.connect(store_path)
            try:
                for (table,) in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
                    for row in connection.execute(f'SELECT * FROM "{table}"').fetchall():
                        leftovers += sum(1 for cell in row if looks_like_old_vector(cell, 8))
            finally:
                connection.close()
            require(leftovers == 0, f"{leftovers} rows still hold an eight-dimensional vector of the old model after re_embed")
            return f"re_embed moved {len(passages)} passages from relay-embed-a (8) to relay-embed-b (12); old-model queries are refused and no old vector remains."
        finally:
            stop(server, thread)
    check("re_embed rebuilds the store under the new model and leaves no old vectors", migration)

    def batched():
        path = os.path.join(WORKSPACE, ".verify-batches.sqlite")
        if os.path.exists(path):
            os.remove(path)
        many = [{"id": f"bk-{index:03d}", "text": f"archive entry {index} {rng.choice(PASSAGE_TEXTS)}"} for index in range(40)]
        server, thread = serve(salt=salt, dims=dims, max_inputs=MAX_BATCH, shuffle=True)
        store = candidate.EmbeddingStore(path)
        try:
            records = store.ingest(many, base_url=server.base_url, model="relay-embed-a", version=version_a)
            sizes = [len(request["body"].get("input") or []) for request in server.requests]
            require(len(server.requests) == 3 and all(size <= MAX_BATCH for size in sizes) and sum(sizes) == 40, f"40 passages need ceil(40/{MAX_BATCH}) = 3 requests of at most {MAX_BATCH} inputs, saw {sizes}")
            require(len(records) == 3 and [record.get("inputs") for record in records] == sizes, f"One batch record per request with its input count, got {records!r}")
            require(all(record.get("prompt_tokens") == sum(server.tokens(text) for text in request["body"]["input"]) for record, request in zip(records, server.requests)), "Each batch record carries the usage of its own request")
            rows = [(passage["id"], server.vector("relay-embed-a", passage["text"])) for passage in many]
            for passage in (many[0], many[17], many[33], many[39]):
                query = server.vector("relay-embed-a", passage["text"])
                same_ranking(store.search(query, 5, model="relay-embed-a"), reference_topk(query, rows, 5), f"batched query for {passage['id']}")
            return "40 passages went out in 3 requests of at most 16 inputs; shuffled data entries were put back by index."
        finally:
            store.close()
            stop(server, thread)
    check("bonus: batched embedding requests respect MAX_BATCH and keep every vector with its passage", batched, optional=True)

    def live():
        config_path = os.path.join(WORKSPACE, "llm.json")
        try:
            with open(config_path, "r", encoding="utf-8") as file:
                config = json.load(file)
        except Exception as error:
            raise EnvironmentBlocked(f"llm.json could not be read ({type(error).__name__}: {error}). It holds base_url, model and embedding_model only; keys stay in the environment.")
        base_url, model = str(config.get("base_url") or ""), str(config.get("embedding_model") or "")
        if not base_url or not model:
            raise EnvironmentBlocked("Set embedding_model in llm.json to an embedding model served by base_url (for Ollama: `ollama pull nomic-embed-text`, then \"nomic-embed-text\"), then verify again. The adapter checks above do not need it.")
        query_text = "how to restart the relay after a power dip"
        body = json.dumps({"model": model, "input": [query_text]}).encode("utf-8")
        request = urllib.request.Request(base_url.rstrip("/") + "/embeddings", data=body, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=LIVE_TIMEOUT) as response:
                direct = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            raise EnvironmentBlocked(f"{base_url} answered HTTP {error.code} for embedding model {model!r}: {error.read(300).decode('utf-8', 'replace')}")
        except Exception as error:
            raise EnvironmentBlocked(f"{base_url} did not answer /embeddings within {LIVE_TIMEOUT} s ({type(error).__name__}: {error}). Start the server or pull the embedding model, then verify again.")
        direct_vector = ((direct.get("data") or [{}])[0]).get("embedding")
        if not isinstance(direct_vector, list) or not direct_vector:
            raise EnvironmentBlocked(f"{base_url} did not return data[0].embedding for {model!r}; point embedding_model at an embedding model, not a chat model.")
        path = os.path.join(WORKSPACE, ".verify-live.sqlite")
        if os.path.exists(path):
            os.remove(path)
        live_passages = [{"id": f"live-{index}", "text": text} for index, text in enumerate(PASSAGE_TEXTS[:4])]
        store = candidate.EmbeddingStore(path)
        try:
            batches = store.ingest(live_passages, base_url=base_url, model=model, version="live")
            meta = store.metadata()
            require(meta.get("model") == model and meta.get("dimension") == len(direct_vector) and meta.get("passages") == 4, f"The live store must carry the endpoint's model id and dimension {len(direct_vector)}, got {meta!r}")
            query = candidate.embed([query_text], base_url=base_url, model=model)[0]
            require(len(query) == len(direct_vector), f"The query vector has {len(query)} dimensions, the endpoint's direct answer has {len(direct_vector)}")
            top = store.search(query, 2, model=model)
            require(len(top) == 2 and all(isinstance(item[1], float) for item in top), f"Live top-2 must be two (id, score) pairs, got {top!r}")
            tokens = sum(int(batch.get("prompt_tokens") or 0) for batch in batches)
            return f"Live: {model} at {base_url}; dimension {len(direct_vector)}; {tokens} prompt tokens for 4 passages; top-1 for {query_text!r} is {top[0][0]} ({top[0][1]:.4f}), then {top[1][0]} ({top[1][1]:.4f}). A measurement, not a verdict."
        finally:
            store.close()

    try:
        CHECKS.append({"name": "Live embeddings from the configured endpoint land in the store with their dimension", "passed": True, "detail": live()})
    except EnvironmentBlocked as blocked:
        CHECKS.append({"name": "Environment blocked", "passed": False, "detail": str(blocked)[:1500]})
    except Exception as error:
        CHECKS.append({"name": "Live embeddings from the configured endpoint land in the store with their dimension", "passed": False, "detail": f"{type(error).__name__}: {error}"[:1500]})
    finally:
        leftover = store_box.pop("store", None)
        if leftover is not None:
            try:
                leftover.close()
            except Exception:
                pass


try:
    trial()
except Exception as error:
    CHECKS.append({"name": "Load embedding store", "passed": False, "detail": f"{type(error).__name__}: {error}"[:1500]})
finally:
    for name in SCRATCH:
        for suffix in ("", "-journal", "-wal", "-shm"):
            scratch = os.path.join(WORKSPACE, name + suffix)
            if os.path.exists(scratch):
                try:
                    os.remove(scratch)
                except OSError:
                    pass
print(json.dumps({"checks": CHECKS}))
sys.exit(0 if CHECKS and all(item["passed"] for item in CHECKS if not item.get("optional")) else 1)
