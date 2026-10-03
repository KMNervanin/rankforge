"""Independent behavioral checks. Launched outside the learner workspace."""
import copy
import importlib.util
import json
import os
import sqlite3
import socketserver
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from http.server import HTTPServer

MISSION, WORKSPACE = sys.argv[1:3]
sys.path.insert(0, WORKSPACE)
CHECKS = []


def check(name, operation):
    try:
        operation()
        CHECKS.append({"name": name, "passed": True, "detail": "Behavior verified."})
    except Exception as error:
        CHECKS.append({"name": name, "passed": False, "detail": f"{type(error).__name__}: {error}"[:1500]})


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def raises(kind, operation):
    try:
        operation()
    except kind:
        return
    raise AssertionError(f"Expected {kind.__name__}")


def load(name):
    spec = importlib.util.spec_from_file_location(f"candidate_{name}", os.path.join(WORKSPACE, f"{name}.py"))
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def connect(path=":memory:"):
    db = sqlite3.connect(path)
    db.execute("PRAGMA foreign_keys=ON")
    return db


def signal():
    candidate = load("service")
    class LocalServer(HTTPServer):
        def server_bind(self):
            # Loopback checks do not need reverse DNS, which can stall under a VPN.
            socketserver.TCPServer.server_bind(self)
            self.server_name = "localhost"
            self.server_port = self.server_address[1]
    server = LocalServer(("127.0.0.1", 0), candidate.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    local_http = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def request(route, expected):
        try:
            response = local_http.open(f"http://127.0.0.1:{server.server_port}{route}", timeout=3)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            require(response.status == expected, f"Expected HTTP {expected}, got {response.status}")
            if expected == 200:
                require("application/json" in response.headers.get("Content-Type", ""), "Expected application/json")
                data = json.loads(response.read())
                require(data == {"status": "ok", "service": "relay"}, f"Unexpected health body: {data!r}")
    try:
        for route, expected in [("/health", 200), ("/health?probe=1", 200), ("/missing", 404), ("/missing?probe=1", 404)]:
            check(f"HTTP contract: {route}", lambda r=route, e=expected: request(r, e))
    finally:
        server.shutdown()
        server.server_close()


def vault():
    candidate = load("store")
    def schema():
        db = connect()
        candidate.create_schema(db)
        db.execute("INSERT INTO items VALUES ('cell','Power cell')")
        return db
    def valid():
        with schema() as db:
            db.execute("INSERT INTO movements VALUES ('m','cell',2)")
            candidate.create_schema(db)
            require(db.execute("SELECT quantity FROM movements WHERE id='m'").fetchone() == (2,), "Repeated schema creation lost data")
    check("Valid movement and repeatable schema", valid)
    def invalid(sql):
        with schema() as db:
            raises(sqlite3.IntegrityError, lambda: db.execute(sql))
    for label, sql in [
        ("Reject unknown item", "INSERT INTO movements VALUES ('m','ghost',1)"),
        ("Reject zero quantity", "INSERT INTO movements VALUES ('m','cell',0)"),
        ("Reject negative quantity", "INSERT INTO movements VALUES ('m','cell',-2)"),
        ("Reject missing name", "INSERT INTO items VALUES ('other',NULL)"),
        ("Reject duplicate item", "INSERT INTO items VALUES ('cell','Other')"),
        ("Reject missing movement item", "INSERT INTO movements VALUES ('m',NULL,1)"),
        ("Reject missing quantity", "INSERT INTO movements VALUES ('m','cell',NULL)"),
    ]:
        check(label, lambda s=sql: invalid(s))
    def duplicate():
        with schema() as db:
            db.execute("INSERT INTO movements VALUES ('m','cell',1)")
            raises(sqlite3.IntegrityError, lambda: db.execute("INSERT INTO movements VALUES ('m','cell',2)"))
    check("Movement identity is unique", duplicate)


INVALID_EVENTS = [
    {}, {"id": "", "item": "cell", "quantity": 1}, {"id": "x", "item": "", "quantity": 1},
    {"id": "x", "item": "cell", "quantity": 0}, {"id": "x", "item": "cell", "quantity": -1},
    {"id": "x", "item": "cell", "quantity": 1.2}, {"id": "x", "item": "cell", "quantity": True},
]


def echo():
    candidate = load("ingest")
    event = {"id": "delivery-93", "item": "coolant", "quantity": 7}
    def replay():
        with connect() as db:
            require(candidate.ingest(db, event) is True, "New event must return True")
            require(candidate.ingest(db, dict(event)) is False, "Replay must return False")
            require(db.execute("SELECT id,item,quantity FROM events").fetchall() == [("delivery-93", "coolant", 7)], "Replay changed the effect")
    check("One effect for repeated delivery", replay)
    def conflict():
        with connect() as db:
            candidate.ingest(db, event)
            raises(ValueError, lambda: candidate.ingest(db, {**event, "quantity": 8}))
            raises(ValueError, lambda: candidate.ingest(db, {**event, "item": "cell"}))
            require(db.execute("SELECT quantity FROM events").fetchall() == [(7,)], "Conflict changed old data")
    check("Conflicting identities are rejected", conflict)
    for index, bad in enumerate(INVALID_EVENTS):
        def reject(value=bad):
            with connect() as db:
                raises(ValueError, lambda: candidate.ingest(db, value))
        check(f"Invalid event boundary {index + 1}", reject)
    def persistent():
        with tempfile.TemporaryDirectory() as directory:
            file = os.path.join(directory, "events.sqlite")
            with connect(file) as db:
                candidate.ingest(db, event)
            with connect(file) as db:
                require(candidate.ingest(db, event) is False, "Replay identity was lost after reconnect")
    check("Identity persists across connections", persistent)


def ledger():
    candidate = load("transform")
    cases = [
        ("Decimal money and normalized dates", [
            {"id": "a", "date": "2024/02/29", "amount": "0.10"},
            {"id": "b", "date": "2024-02-29", "amount": "0.20"},
            {"id": "a", "date": "2024-02-29", "amount": "0.1"},
        ], {"totals": {"2024-02-29": "0.30"}, "rejected": []}),
        ("Bad rows and collisions remain visible", [
            {"id": "x", "date": "2025-02-29", "amount": "1.00"},
            {"id": "x", "date": "2025-02-28", "amount": "2.00"},
            {"id": "x", "date": "2025-02-28", "amount": "3.00"},
            {"id": "y", "date": "2025-02-28", "amount": "NaN"},
            {"id": "z", "date": "2025-02-28", "amount": "-1.00"},
            {"id": "w", "date": "2025-02-28", "amount": "1.001"},
            {"id": "v", "date": "2025-02-28", "amount": "Infinity"},
            {"id": "", "date": "2025-02-28", "amount": "1.00"},
        ], {"totals": {"2025-02-28": "2.00"}, "rejected": [0, 2, 3, 4, 5, 6, 7]}),
        ("Sorted days and zero amounts", [
            {"id": "a", "date": "2026-12-31", "amount": "1000000000000.19"},
            {"id": "b", "date": "2026-01-01", "amount": "0"},
            {"id": "c", "date": "2026-12-31", "amount": "0.01"},
        ], {"totals": {"2026-01-01": "0.00", "2026-12-31": "1000000000000.20"}, "rejected": []}),
        ("Empty input", [], {"totals": {}, "rejected": []}),
        ("Reject malformed shape and ambiguous dates", [None, {}, {"id": "q", "date": "2026-1-2", "amount": "1.00"}], {"totals": {}, "rejected": [0, 1, 2]}),
    ]
    for label, rows, expected in cases:
        def verify(source=rows, target=expected):
            original = copy.deepcopy(source)
            actual = candidate.transform(source)
            require(actual == target, f"Expected {target!r}, got {actual!r}")
            require(list(actual["totals"]) == sorted(actual["totals"]), "Day keys are not sorted")
            require(source == original, "Input was mutated")
            require(candidate.transform(source) == actual, "Repeated transformation changed output")
        check(label, verify)


def recovery():
    candidate = load("recover")
    events = [{"id": "a", "item": "cell", "quantity": 4}, {"id": "b", "item": "coolant", "quantity": 2}, {"id": "a", "item": "cell", "quantity": 4}]
    def replay():
        with tempfile.TemporaryDirectory() as directory:
            file = os.path.join(directory, "recovery.sqlite")
            result = candidate.recover(file, events)
            require(result == {"event_count": 2, "total_quantity": 6}, f"Wrong summary: {result!r}")
            require(candidate.recover(file, events) == result, "Recovery is not repeatable")
            with connect(file) as db:
                require(db.execute("SELECT id,item,quantity FROM events ORDER BY id").fetchall() == [("a", "cell", 4), ("b", "coolant", 2)], "Recovered data is incorrect")
    check("Recover and repeat the archive", replay)
    def preserved(bad):
        with tempfile.TemporaryDirectory() as directory:
            file = os.path.join(directory, "recovery.sqlite")
            with connect(file) as db:
                db.execute("CREATE TABLE events(id TEXT PRIMARY KEY,item TEXT,quantity INTEGER)")
                db.execute("INSERT INTO events VALUES('old','reserve',99)")
            raises(ValueError, lambda: candidate.recover(file, [events[0], bad]))
            with connect(file) as db:
                require(db.execute("SELECT * FROM events").fetchall() == [("old", "reserve", 99)], "A failed recovery damaged the previous database")
    for index, bad in enumerate(INVALID_EVENTS + [{"id": "a", "item": "cell", "quantity": 9}]):
        check(f"Failure preserves previous state {index + 1}", lambda value=bad: preserved(value))
    def replacement():
        with tempfile.TemporaryDirectory() as directory:
            file = os.path.join(directory, "recovery.sqlite")
            candidate.recover(file, events)
            require(candidate.recover(file, []) == {"event_count": 0, "total_quantity": 0}, "An empty successful archive must replace old events")
            with connect(file) as db:
                require(db.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0, "Old events survived replacement")
    check("Successful recovery replaces old state", replacement)


try:
    {"signal": signal, "vault": vault, "echo": echo, "ledger": ledger, "recovery": recovery}[MISSION]()
except Exception as error:
    CHECKS.append({"name": "Load candidate", "passed": False, "detail": f"{type(error).__name__}: {error}"[:1500]})
print(json.dumps({"checks": CHECKS}))
sys.exit(0 if CHECKS and all(item["passed"] for item in CHECKS) else 1)
