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
from contextlib import closing
from http.server import HTTPServer

MISSION, WORKSPACE = sys.argv[1:3]
sys.path.insert(0, WORKSPACE)
CHECKS = []


def check(name, operation, optional=False):
    # An optional check is the hidden bonus of a mission: it can only add, it never fails the run.
    try:
        operation()
        CHECKS.append({"name": name, "passed": True, "detail": "Behavior verified.", **({"optional": True} if optional else {})})
    except Exception as error:
        CHECKS.append({"name": name, "passed": False, "detail": f"{type(error).__name__}: {error}"[:1500], **({"optional": True} if optional else {})})


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
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        del sys.modules[spec.name]
        raise
    return module


def connect(path=":memory:"):
    db = sqlite3.connect(path)
    db.execute("PRAGMA foreign_keys=ON")
    return db


def primary_key(db, table):
    columns = db.execute(f'PRAGMA table_info("{table}")').fetchall()
    require([(row[1], row[5]) for row in columns if row[5]] == [("id", 1)],
            f"{table}.id must be the sole primary key")


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
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
    local_http = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    def request(route, expected):
        try:
            response = local_http.open(f"http://127.0.0.1:{server.server_port}{route}", timeout=3)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            require(response.status == expected, f"Expected HTTP {expected}, got {response.status}")
            if expected == 200:
                require(response.headers.get_content_type() == "application/json", "Expected application/json")
                data = json.loads(response.read())
                required = {"status": "ok", "service": "relay"}
                require(isinstance(data, dict) and {key: data.get(key) for key in required} == required, f"Unexpected health body: {data!r}")
    def framed(route, expected):
        try:
            response = local_http.open(f"http://127.0.0.1:{server.server_port}{route}", timeout=3)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            require(response.status == expected, f"GET {route}: expected HTTP {expected}, got {response.status}")
            body = response.read()
            declared = response.headers.get("Content-Length")
            require(declared is not None and declared.strip().isdigit(), f"GET {route}: no Content-Length header; the client cannot tell where the body ends")
            require(int(declared) == len(body), f"GET {route}: Content-Length {declared} but {len(body)} body bytes arrived")
            require(isinstance(json.loads(body), dict), f"GET {route}: the framed body is not a complete JSON object")
    def bonus():
        framed("/health", 200)
        framed("/missing?probe=bonus", 404)
    try:
        for route, expected in [("/health", 200), ("/health?probe=1&next=/missing", 200),
                                ("/missing", 404), ("/missing?probe=1", 404),
                                ("/healthcheck", 404), ("/health/extra", 404),
                                ("/health/", 404), ("/missing?next=/health", 404)]:
            check(f"HTTP contract: {route}", lambda r=route, e=expected: request(r, e))
        check("bonus: Content-Length equals the body bytes on /health and on an unknown path", bonus, optional=True)
    finally:
        server.shutdown()
        server.server_close()


def vault():
    candidate = load("store")
    def schema():
        db = connect()
        candidate.create_schema(db)
        db.execute("INSERT INTO items(id,name) VALUES ('cell','Power cell')")
        db.commit()
        return db
    def valid():
        with schema() as db:
            primary_key(db, "items")
            primary_key(db, "movements")
            db.execute("INSERT INTO movements(id,item_id,quantity) VALUES ('m','cell',2)")
            db.commit()
            candidate.create_schema(db)
            require(db.execute("SELECT quantity FROM movements WHERE id='m'").fetchone() == (2,), "Repeated schema creation lost data")
    check("Valid movement and repeatable schema", valid)
    def reject_write(db, sql):
        def write():
            db.execute(sql)
            db.commit()
        try:
            raises(sqlite3.IntegrityError, write)
        finally:
            db.rollback()
    def invalid(sql):
        with schema() as db:
            reject_write(db, sql)
    for label, sql in [
        ("Reject unknown item", "INSERT INTO movements(id,item_id,quantity) VALUES ('m','ghost',1)"),
        ("Reject zero quantity", "INSERT INTO movements(id,item_id,quantity) VALUES ('m','cell',0)"),
        ("Reject negative quantity", "INSERT INTO movements(id,item_id,quantity) VALUES ('m','cell',-2)"),
        ("Reject missing name", "INSERT INTO items(id,name) VALUES ('other',NULL)"),
        ("Reject duplicate item", "INSERT INTO items(id,name) VALUES ('cell','Other')"),
        ("Reject missing movement item", "INSERT INTO movements(id,item_id,quantity) VALUES ('m',NULL,1)"),
        ("Reject missing quantity", "INSERT INTO movements(id,item_id,quantity) VALUES ('m','cell',NULL)"),
    ]:
        check(label, lambda s=sql: invalid(s))
    def duplicate():
        with schema() as db:
            db.execute("INSERT INTO movements(id,item_id,quantity) VALUES ('m','cell',1)")
            db.commit()
            reject_write(db, "INSERT INTO movements(id,item_id,quantity) VALUES ('m','cell',2)")
    check("Movement identity is unique", duplicate)
    def persistent():
        with tempfile.TemporaryDirectory() as directory:
            file = os.path.join(directory, "vault.sqlite")
            with closing(connect(file)) as db, db:
                candidate.create_schema(db)
                db.executemany("INSERT INTO items(id,name) VALUES (?,?)", [("cell", "Power cell"), ("coolant", "Coolant")])
                db.executemany("INSERT INTO movements(id,item_id,quantity) VALUES (?,?,?)", [("m1", "cell", 2), ("m2", "coolant", 5), ("m3", "cell", 1)])
            with closing(connect(file)) as db, db:
                candidate.create_schema(db)
                db.commit()
                require(db.execute("SELECT id,name FROM items ORDER BY id").fetchall() == [("cell", "Power cell"), ("coolant", "Coolant")], "Items were lost after reconnect/setup")
                require(db.execute("SELECT id,item_id,quantity FROM movements ORDER BY id").fetchall() == [("m1", "cell", 2), ("m2", "coolant", 5), ("m3", "cell", 1)], "Movements were lost after reconnect/setup")
                reject_write(db, "INSERT INTO movements(id,item_id,quantity) VALUES ('bad','ghost',1)")
    check("Schema and data persist after commit, close and reconnect", persistent)
    def orphans():
        # A client that never ran PRAGMA foreign_keys: the schema alone must keep movements attached to items.
        with closing(sqlite3.connect(":memory:")) as db:
            candidate.create_schema(db)
            db.execute("INSERT INTO items(id,name) VALUES ('cell','Power cell')")
            db.execute("INSERT INTO movements(id,item_id,quantity) VALUES ('m','cell',2)")
            db.commit()
            try:
                db.execute("DELETE FROM items WHERE id='cell'")
                db.commit()
            except sqlite3.DatabaseError:
                db.rollback()
                require(db.execute("SELECT COUNT(*) FROM items WHERE id='cell'").fetchone() == (1,), "The rejected delete must leave the item in place")
                return
            require(db.execute("SELECT COUNT(*) FROM movements WHERE item_id='cell'").fetchone() == (0,), "Deleting a referenced item left orphan movements on a connection without foreign key enforcement; restrict it or cascade")
    check("bonus: deleting a referenced item leaves no orphan movements, even without PRAGMA foreign_keys", orphans, optional=True)


INVALID_EVENTS = [
    ("not an object", None), ("list instead of object", []), ("empty object", {}),
    ("numeric record", 1), ("string record", "event"),
    ("nonempty list record", [{"id": "x", "item": "cell", "quantity": 1}]),
    ("tuple record", ("x", "cell", 1)),
    ("missing id", {"item": "cell", "quantity": 1}),
    ("missing item", {"id": "x", "quantity": 1}),
    ("missing quantity", {"id": "x", "item": "cell"}),
    ("empty id", {"id": "", "item": "cell", "quantity": 1}),
    ("empty item", {"id": "x", "item": "", "quantity": 1}),
    ("null id", {"id": None, "item": "cell", "quantity": 1}),
    ("numeric id", {"id": 1, "item": "cell", "quantity": 1}),
    ("null item", {"id": "x", "item": None, "quantity": 1}),
    ("numeric item", {"id": "x", "item": 1, "quantity": 1}),
    ("null quantity", {"id": "x", "item": "cell", "quantity": None}),
    ("text quantity", {"id": "x", "item": "cell", "quantity": "1"}),
    ("zero quantity", {"id": "x", "item": "cell", "quantity": 0}),
    ("negative quantity", {"id": "x", "item": "cell", "quantity": -1}),
    ("fractional quantity", {"id": "x", "item": "cell", "quantity": 1.2}),
    ("integral float quantity", {"id": "x", "item": "cell", "quantity": 7.0}),
    ("boolean quantity", {"id": "x", "item": "cell", "quantity": True}),
    ("quantity exceeds SQLite INTEGER", {"id": "x", "item": "cell", "quantity": 9223372036854775808}),
]


def echo():
    candidate = load("ingest")
    event = {"id": "delivery-93", "item": "coolant", "quantity": 7}
    def replay():
        with connect() as db:
            require(candidate.ingest(db, event) is True, "New event must return True")
            require(candidate.ingest(db, {**event, "delivery_attempt": 2}) is False, "Replay must ignore extra fields")
            require(db.execute("SELECT id,item,quantity FROM events").fetchall() == [("delivery-93", "coolant", 7)], "Replay changed the effect")
            primary_key(db, "events")
            second = {"id": "delivery-94", "item": "coolant", "quantity": 7}
            require(candidate.ingest(db, second) is True, "Different identities are different events, even with equal payloads")
            require(candidate.ingest(db, event) is False, "Interleaved replay was counted again")
            require(db.execute("SELECT COUNT(*) FROM events").fetchone() == (2,), "Interleaved delivery changed the event set")
    check("One effect for repeated delivery", replay)
    def conflict():
        with connect() as db:
            candidate.ingest(db, event)
            raises(ValueError, lambda: candidate.ingest(db, {**event, "quantity": 8}))
            raises(ValueError, lambda: candidate.ingest(db, {**event, "item": "cell"}))
            require(db.execute("SELECT quantity FROM events").fetchall() == [(7,)], "Conflict changed old data")
    check("Conflicting identities are rejected", conflict)
    for label, bad in INVALID_EVENTS:
        def reject(value=bad):
            with connect() as db:
                candidate.ingest(db, event)
                raises(ValueError, lambda: candidate.ingest(db, copy.deepcopy(value)))
                require(db.execute("SELECT id,item,quantity FROM events").fetchall() == [("delivery-93", "coolant", 7)], "Rejected input changed existing events")
        check(f"Reject {label} without changing events", reject)
    def persistent():
        with tempfile.TemporaryDirectory() as directory:
            file = os.path.join(directory, "events.sqlite")
            with closing(connect(file)) as db, db:
                candidate.ingest(db, event)
            with closing(connect(file)) as db, db:
                require(candidate.ingest(db, event) is False, "Replay identity was lost after reconnect")
                large = {"id": "largest", "item": "cell", "quantity": 9223372036854775807}
                require(candidate.ingest(db, large) is True, "Largest positive SQLite INTEGER is valid")
    check("Identity persists across connections", persistent)
    def quoted():
        with connect() as db:
            candidate.ingest(db, event)
            nasty = {"id": "delivery-'); DROP TABLE events; --", "item": "coolant' OR '1'='1", "quantity": 3}
            require(candidate.ingest(db, copy.deepcopy(nasty)) is True, "An identifier with quotes and SQL text is a valid new event")
            require(candidate.ingest(db, copy.deepcopy(nasty)) is False, "Replay of the quoted identifier must return exactly False")
            require(db.execute("SELECT item,quantity FROM events WHERE id=?", (nasty["id"],)).fetchall() == [(nasty["item"], 3)], "The quoted identifier and item were not stored verbatim")
            require(db.execute("SELECT COUNT(*) FROM events").fetchone() == (2,), "The table must still hold exactly two events")
    check("bonus: an identifier carrying quotes and SQL text is stored verbatim and replayed as a duplicate", quoted, optional=True)


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
        ("Additional fields do not change event identity", [
            {"id": "extra", "date": "2026-01-01", "amount": "1.00", "source": "one"},
            {"id": "extra", "date": "2026-01-01", "amount": "1.00", "source": "two"},
        ], {"totals": {"2026-01-01": "1.00"}, "rejected": []}),
        ("Reject malformed shape and ambiguous dates", [None, {}, {"id": "q", "date": "2026-1-2", "amount": "1.00"}], {"totals": {}, "rejected": [0, 1, 2]}),
        ("Reject non-dictionary rows without losing valid rows", [
            {"id": "before", "date": "2026-01-01", "amount": "1.00"},
            1, "row", [{"id": "x", "date": "2026-01-01", "amount": "1.00"}], ("x", "2026-01-01", "1.00"),
            {"id": "after", "date": "2026-01-01", "amount": "2.00"},
        ], {"totals": {"2026-01-01": "3.00"}, "rejected": [1, 2, 3, 4]}),
        ("Exact cents at the declared amount boundary", [
            {"id": "large", "date": "2026-01-01", "amount": "9999999999999999.99"},
            {"id": "small", "date": "2026-01-01", "amount": "0.01"},
            {"id": "large", "date": "2026/01/01", "amount": "09999999999999999.99"},
            {"id": "too-large", "date": "2026-01-01", "amount": "10000000000000000.00"},
        ], {"totals": {"2026-01-01": "10000000000000000.00"}, "rejected": [3]}),
        ("Cents must survive aggregation", [
            {"id": "a", "date": "2026-01-01", "amount": "1000000000000000.01"},
            {"id": "b", "date": "2026-01-01", "amount": "0.01"},
        ], {"totals": {"2026-01-01": "1000000000000000.02"}, "rejected": []}),
        ("Reject unsupported money spellings and types", [
            {"id": str(index), "date": "2026-01-01", "amount": amount}
            for index, amount in enumerate(["1e2", "+1.00", " 1.00 ", "1.", ".50", "1_000", "１.００", 1, None, True])
        ], {"totals": {}, "rejected": list(range(10))}),
        ("Reject missing fields and non-calendar dates", [
            {"id": "a", "amount": "1.00"}, {"id": "a", "date": "2026-01-01"},
            {"date": "2026-01-01", "amount": "1.00"},
            {"id": 1, "date": "2026-01-01", "amount": "1.00"},
            {"id": "a", "date": "2026/01-01", "amount": "1.00"},
            {"id": "a", "date": "2026-04-31", "amount": "1.00"},
            {"id": "a", "date": "2026-01-01", "amount": "01.0"},
        ], {"totals": {"2026-01-01": "1.00"}, "rejected": list(range(6))}),
    ]
    def verify(source, target):
        original = copy.deepcopy(source)
        actual = candidate.transform(source)
        require(isinstance(actual, dict) and set(actual) == {"totals", "rejected"}, "Return totals and rejected")
        require(actual["totals"] == target["totals"], f"Expected totals {target['totals']!r}, got {actual['totals']!r}")
        rejected = actual["rejected"]
        require(isinstance(rejected, list) and all(type(index) is int for index in rejected), "Rejected must be a list of integer row indices")
        require(len(rejected) == len(set(rejected)) and set(rejected) == set(target["rejected"]), f"Expected rejected indices {target['rejected']!r} in any order, got {rejected!r}")
        require(list(actual["totals"]) == sorted(actual["totals"]), "Day keys are not sorted")
        require(source == original, "Input was mutated")
        previous = copy.deepcopy(actual)
        require(candidate.transform(source) == previous, "Repeated transformation changed output")
        require(source == original, "Repeated transformation mutated input")
    for label, rows, expected in cases:
        check(label, lambda source=rows, target=expected: verify(source, target))
    moved = [{"id": "a", "date": "2026-01-01", "amount": "1.00"}, {"id": "a", "date": "2026-01-02", "amount": "1.00"}]
    check("bonus: the same id and amount on a different day is a conflict, not a replay", lambda: verify(moved, {"totals": {"2026-01-01": "1.00"}, "rejected": [1]}), optional=True)


def recovery():
    candidate = load("recover")
    events = [{"id": "a", "item": "cell", "quantity": 4}, {"id": "b", "item": "coolant", "quantity": 2}, {"id": "a", "item": "cell", "quantity": 4, "delivery_attempt": 2}]
    def replay():
        with tempfile.TemporaryDirectory() as directory:
            file = os.path.join(directory, "recovery.sqlite")
            result = candidate.recover(file, events)
            require(result == {"event_count": 2, "total_quantity": 6}, f"Wrong summary: {result!r}")
            require(candidate.recover(file, events) == result, "Recovery is not repeatable")
            with closing(connect(file)) as db:
                require(db.execute("SELECT id,item,quantity FROM events ORDER BY id").fetchall() == [("a", "cell", 4), ("b", "coolant", 2)], "Recovered data is incorrect")
                primary_key(db, "events")
    check("Recover and repeat the archive", replay)
    def preserved(bad):
        with tempfile.TemporaryDirectory() as directory:
            file = os.path.join(directory, "recovery.sqlite")
            def state(db):
                return (db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").fetchall(),
                        db.execute("SELECT id,item,quantity FROM events ORDER BY id").fetchall(),
                        db.execute("SELECT value FROM archive_metadata ORDER BY value").fetchall())
            with closing(connect(file)) as db, db:
                db.execute("CREATE TABLE events(quantity INTEGER,id TEXT PRIMARY KEY,item TEXT)")
                db.executemany("INSERT INTO events(id,item,quantity) VALUES(?,?,?)", [("old", "reserve", 99), ("older", "cell", 5)])
                db.execute("CREATE TABLE archive_metadata(value TEXT)")
                db.execute("INSERT INTO archive_metadata VALUES('last-known-good')")
                before = state(db)
            raises(ValueError, lambda: candidate.recover(file, copy.deepcopy([*events[:2], bad])))
            with closing(connect(file)) as db:
                require(state(db) == before, "Failed recovery changed existing rows, schema or unrelated data")
    for label, bad in INVALID_EVENTS + [("quantity conflict", {"id": "a", "item": "cell", "quantity": 9}), ("item conflict", {"id": "a", "item": "other", "quantity": 4})]:
        check(f"Late {label} preserves previous state", lambda value=bad: preserved(value))
    def replacement():
        with tempfile.TemporaryDirectory() as directory:
            file = os.path.join(directory, "recovery.sqlite")
            candidate.recover(file, events)
            fresh = [{"id": "new", "item": "reserve", "quantity": 3}]
            require(candidate.recover(file, fresh) == {"event_count": 1, "total_quantity": 3}, "Wrong replacement summary")
            with closing(connect(file)) as db:
                require(db.execute("SELECT id,item,quantity FROM events").fetchall() == [("new", "reserve", 3)], "A nonempty archive did not replace all old events")
            require(candidate.recover(file, []) == {"event_count": 0, "total_quantity": 0}, "An empty successful archive must replace old events")
            with closing(connect(file)) as db:
                require(db.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0, "Old events survived replacement")
    check("Successful recovery replaces old state", replacement)
    def reordered():
        with tempfile.TemporaryDirectory() as directory:
            file = os.path.join(directory, "reordered.sqlite")
            with closing(connect(file)) as db, db:
                db.execute("CREATE TABLE events(quantity INTEGER,id TEXT PRIMARY KEY,item TEXT)")
            archive = [{"id": "largest", "item": "cell", "quantity": 9223372036854775807}]
            require(candidate.recover(file, archive) == {"event_count": 1, "total_quantity": 9223372036854775807}, "SQLite INTEGER boundary or column order changed the result")
            with closing(connect(file)) as db:
                require(db.execute("SELECT id,item,quantity FROM events").fetchall() == [("largest", "cell", 9223372036854775807)], "Restored columns do not match their names")
    check("Existing column order does not change recovery", reordered)
    def overflow():
        with tempfile.TemporaryDirectory() as directory:
            file = os.path.join(directory, "overflow.sqlite")
            archive = [{"id": "left", "item": "cell", "quantity": 9223372036854775807}, {"id": "right", "item": "coolant", "quantity": 9223372036854775807}]
            result = candidate.recover(file, archive)
            require(isinstance(result, dict) and type(result.get("total_quantity")) is int and result == {"event_count": 2, "total_quantity": 18446744073709551614},
                    f"Two maximal SQLite integers must sum exactly to 18446744073709551614, got {result!r}")
    check("bonus: two maximal SQLite integers are summed without overflow", overflow, optional=True)


try:
    {"signal": signal, "vault": vault, "echo": echo, "ledger": ledger, "recovery": recovery}[MISSION]()
except Exception as error:
    CHECKS.append({"name": "Load candidate", "passed": False, "detail": f"{type(error).__name__}: {error}"[:1500]})
print(json.dumps({"checks": CHECKS}))
sys.exit(0 if CHECKS and all(item["passed"] for item in CHECKS if not item.get("optional")) else 1)
