"""Owned loopback delivery fixtures, contract v1. No learner probe implementation."""
import json
import socketserver
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlsplit
from typing import Any


class FixtureUnavailable(OSError):
    environment_blocked = True


class RequestFramingError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


class LocalServer(HTTPServer):
    style: str
    fault: str | None
    records: dict
    trace: list
    request_media: list
    attempts: list
    effects: int
    release: threading.Event
    closed: threading.Event
    delay: tuple[str, float] | None
    delay_started: threading.Event
    delay_received_at: float | None
    delay_released_at: float | None
    delay_max_gap: float
    delay_last_tick: float | None

    def server_bind(self):
        # A loopback fixture needs no reverse DNS (which may stall behind a VPN).
        socketserver.TCPServer.server_bind(self)
        self.server_name = "localhost"
        self.server_port = self.server_address[1]


class WireHandler(BaseHTTPRequestHandler):
    server: Any

    def setup(self):
        super().setup()
        self.connection.settimeout(2)

    def log_message(self, format, *args):
        pass

    def parse_request(self):
        valid = super().parse_request()
        if valid:
            self.server.attempts.append((self.command, self.path))
        return valid

    def read_exact(self, size):
        data = self.rfile.read(size)
        if len(data) != size:
            raise RequestFramingError("Incomplete request body")
        return data

    def request_body(self):
        lengths = self.headers.get_all("Content-Length", [])
        transfers = self.headers.get_all("Transfer-Encoding", [])
        if len(lengths) > 1 or len(transfers) > 1 or (lengths and transfers):
            raise RequestFramingError("Ambiguous request framing")
        if not transfers:
            length = lengths[0] if lengths else "0"
            if not length.isascii() or not length.isdecimal():
                raise RequestFramingError("Invalid Content-Length")
            if len(length) > 16 or int(length) > 4096:
                raise RequestFramingError("Request body exceeds 4096 bytes", 413)
            return self.read_exact(int(length))
        if transfers[0].strip().lower() != "chunked":
            raise RequestFramingError("Only chunked transfer coding is supported")
        body = bytearray()
        overhead = 0

        def line():
            nonlocal overhead
            value = self.rfile.readline(4097)
            overhead += len(value)
            if len(value) > 4096 or overhead > 65536:
                raise RequestFramingError("Chunk metadata exceeds fixture limit", 413)
            if not value.endswith(b"\r\n"):
                raise RequestFramingError("Incomplete chunk framing")
            return value[:-2]

        while True:
            size_text = line().partition(b";")[0].strip()
            if not size_text or any(c not in b"0123456789abcdefABCDEF" for c in size_text):
                raise RequestFramingError("Invalid hexadecimal chunk size")
            size = int(size_text, 16)
            if size > 4096 - len(body):
                raise RequestFramingError("Request body exceeds 4096 bytes", 413)
            if size == 0:
                while True:
                    trailer = line()
                    if not trailer:
                        return bytes(body)
                    if b":" not in trailer:
                        raise RequestFramingError("Invalid trailer field")
                    # Trailers are framing metadata; they cannot replace request headers.
            body.extend(self.read_exact(size))
            overhead += 2
            if self.read_exact(2) != b"\r\n":
                raise RequestFramingError("Missing chunk terminator")

    def receive(self) -> Any:
        raw = self.request_body()
        data = json.loads(raw) if raw else None
        self.server.trace.append((self.command, self.path, data))
        self.server.request_media.append(self.headers.get("Content-Type", "").partition(";")[0].strip().lower())
        if self.server.fault == "timeout":
            self.server.release.wait()
        return data

    def reply(self, status, body):
        fault, _, target = (self.server.fault or "").partition(":")
        target, _, field = target.partition(":")
        path = urlsplit(self.path).path
        first = len(self.server.trace) == 1
        if self.command == "POST":
            observation = {1: "create", 2: "replay", 3: "conflict"}.get(len(self.server.trace), "extra")
        elif path == "/stats":
            observation = "effects"
        elif path.endswith("/missing"):
            observation = "missing"
        else:
            observation = "query" if "view=summary" in self.path else "read"
        if self.server.delay and observation == self.server.delay[0]:
            self.server.delay_received_at = time.monotonic()
            self.server.delay_last_tick = self.server.delay_received_at
            self.server.delay_started.set()
            self.server.release.wait()
            if self.server.closed.is_set():
                return
        selected = observation == target if target else first
        if selected and fault in ("wrong", "missing"):
            body = dict(body)
            value = body[field]
            if fault == "missing":
                del body[field]
            else:
                body[field] = value + 1 if type(value) is int else value + "-wrong"
        if fault == "status" and selected:
            status = 202
        if fault == "http_error" and first:
            status = 500
        if fault == "redirect" and first:
            status = 302
        if fault == "body" and selected:
            field = "quantity" if "quantity" in body else "effects" if "effects" in body else "error"
            body = {**body, field: "incorrect"}
        if fault == "quantity_type" and first:
            body = {**body, "quantity": str(body["quantity"])}
        if fault == "boolean" and first:
            body = {**body, "quantity": True}
        if fault == "path" and path.endswith("/missing"):
            status = 200
        if fault == "error_body" and path.endswith("/missing"):
            body = {"error": "different_error"}
        if fault == "query" and "view=summary" in self.path:
            body = {**body, "view": "full"}
        if fault == "json" and selected:
            raw = b"not-json"
        elif self.server.style == "table":
            raw = json.dumps({**body, "trace_note": "optional"}, sort_keys=True, indent=2).encode()
        else:
            raw = json.dumps(body, separators=(",", ":")).encode()
        mime = "Application/JSON; charset=utf-8" if self.server.style == "table" else "application/json"
        if fault == "media" and selected:
            mime = "text/plain; note=application/json"
        try:
            self.send_response(status)
            self.send_header("content-type", mime)
            self.send_header("x-contract", "wrong-v2" if fault == "header" and selected else "delivery-v1")
            self.send_header("Content-Length", str(len(raw)))
            if fault == "redirect" and first:
                self.send_header("Location", "/deliveries")
            self.end_headers()
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_POST(self):
        try:
            if self.server.fault == "disconnect":
                self.receive()
                self.close_connection = True
                return
            self.handle_request()
        except RequestFramingError as error:
            self.close_connection = True
            self.send_error(error.status, str(error))

    def do_GET(self):
        self.do_POST()

    def handle_request(self):
        raise NotImplementedError


class DirectHandler(WireHandler):
    def handle_request(self):
        data = self.receive()
        route = urlsplit(self.path)
        records = self.server.records
        if self.command == "POST" and route.path == "/deliveries":
            identity = data["id"]
            if identity not in records:
                records[identity] = data.copy()
                self.server.effects += 1
                self.reply(201, data)
            elif records[identity] == data:
                if self.server.fault == "duplicate":
                    self.server.effects += 1
                self.reply(200, data)
            else:
                if self.server.fault == "conflict_effect":
                    self.server.effects += 1
                    records[identity] = data.copy()
                self.reply(409, {"error": "conflict"})
        elif self.command == "GET" and route.path == "/stats":
            self.reply(200, {"effects": self.server.effects})
        elif self.command == "GET" and route.path.startswith("/deliveries/") and route.path[12:] in records:
            item = records[route.path[12:]]
            view = parse_qs(route.query).get("view", ["full"])[0]
            body = {"id": item["id"], "quantity": item["quantity"], "view": view}
            if view == "full":
                body["item"] = item["item"]
            self.reply(200, body)
        else:
            self.reply(404, {"error": "not_found"})


class TableHandler(WireHandler):
    def handle_request(self):
        data = self.receive()
        path, _, query = self.path.partition("?")

        def store():
            previous = self.server.records.get(data["id"])
            if previous is not None:
                return (200, previous) if previous == data else (409, {"error": "conflict"})
            self.server.records[data["id"]] = dict(data)
            self.server.effects += 1
            return 201, dict(data)

        def retrieve():
            row = self.server.records[path.removeprefix("/deliveries/")]
            view = dict(part.split("=", 1) for part in query.split("&") if "=" in part).get("view", "full")
            fields = ("id", "quantity") if view == "summary" else ("id", "item", "quantity")
            return 200, dict([(field, row[field]) for field in fields] + [("view", view)])

        routes = {("POST", "/deliveries"): store,
                  ("GET", "/stats"): lambda: (200, {"effects": self.server.effects})}
        routes.update({("GET", f"/deliveries/{identity}"): retrieve for identity in self.server.records})
        status, body = routes.get((self.command, path), lambda: (404, {"error": "not_found"}))()
        self.reply(status, body)


@contextmanager
def fixture(style="direct", fault=None, delay=None):
    if style not in ("direct", "table"):
        raise ValueError("Unknown fixture style")
    try:
        server = LocalServer(("127.0.0.1", 0), DirectHandler if style == "direct" else TableHandler)
    except OSError as error:
        raise FixtureUnavailable(f"Could not bind an owned loopback fixture: {error}") from error
    server.style, server.fault = style, fault
    server.records, server.trace, server.effects = {}, [], 0
    server.request_media = []
    server.attempts = []
    server.release = threading.Event()
    server.closed = threading.Event()
    server.delay = delay
    server.delay_started = threading.Event()
    server.delay_received_at = None
    server.delay_released_at = None
    server.delay_max_gap = 0.0
    server.delay_last_tick = None

    def release_reply():
        server.delay_started.wait()
        if server.closed.is_set():
            return
        previous = server.delay_received_at
        if previous is None or delay is None:
            return
        deadline = previous + delay[1]
        while not server.closed.is_set():
            now = time.monotonic()
            server.delay_max_gap = max(server.delay_max_gap, now - previous)
            previous = now
            server.delay_last_tick = now
            remaining = deadline - now
            if remaining <= 0:
                server.delay_released_at = now
                server.release.set()
                return
            server.closed.wait(min(remaining, 0.05))

    controller = threading.Thread(target=release_reply, daemon=True) if delay else None
    if controller:
        controller.start()
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", server
    finally:
        server.closed.set()
        server.delay_started.set()
        server.release.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        if thread.is_alive():
            raise RuntimeError("Owned fixture did not stop")
        if controller:
            controller.join(timeout=3)
            if controller.is_alive():
                raise RuntimeError("Owned delay controller did not stop")


@contextmanager
def unavailable():
    # A controlled EOF avoids platform/VPN-dependent refusal versus timeout on unlistened ports.
    with fixture(fault="disconnect") as (url, _):
        yield url
