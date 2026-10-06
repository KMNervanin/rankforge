"""Bounded HTTP transfer checks; run outside the learner workspace."""
import copy
import http.client
import importlib.util
import json
import os
import socketserver
import sys
import threading
from http.server import HTTPServer

MISSION, WORKSPACE = sys.argv[1:3]
CHECKS = []


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def check(name, operation):
    try:
        operation()
        CHECKS.append({"name": name, "passed": True, "detail": "Real HTTP responses and the supplied snapshot verified."})
    except Exception as error:
        CHECKS.append({"name": name, "passed": False, "detail": f"{type(error).__name__}: {error}"[:1500]})


class LocalServer(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True
    supplies: list[dict]

    def server_bind(self):
        # Loopback validation must not wait on VPN-dependent reverse DNS.
        socketserver.TCPServer.server_bind(self)
        self.server_name = "localhost"
        self.server_port = self.server_address[1]

    def handle_error(self, request, client_address):
        pass


def trial():
    require(MISSION == "http-trial", "Unknown trial")
    sys.path.insert(0, WORKSPACE)
    spec = importlib.util.spec_from_file_location("candidate_http_trial", os.path.join(WORKSPACE, "service.py"))
    if spec is None or spec.loader is None:
        raise ImportError("Cannot load service.py")
    candidate = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = candidate
    spec.loader.exec_module(candidate)
    snapshots = [
        [{"id": 18, "item": "câble", "quantity": 5}, {"id": 1, "item": "power cell", "quantity": 9},
         {"id": 73, "item": "seal", "quantity": 1}, {"id": 6, "item": "coolant", "quantity": 2},
         {"id": 44, "item": "filter", "quantity": 7}],
        [{"id": 100000, "item": "last supply", "quantity": 4}, {"id": 26, "item": "first supply", "quantity": 3},
         {"id": 49, "item": "same label", "quantity": 2}, {"id": 90, "item": "same label", "quantity": 6}],
        [],
    ]

    def exercise(records, operation):
        before = copy.deepcopy(records)
        server = LocalServer(("127.0.0.1", 0), candidate.Handler)
        server.supplies = copy.deepcopy(records)
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
        thread.start()

        def request(route, status=200, after=0, limit=2):
            client = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=1.5)
            try:
                client.request("GET", route)
                response = client.getresponse()
                raw = response.read(16385)
                require(len(raw) <= 16384, "Response exceeds the fixture's 16 KiB bound")
                declared = response.getheader("Content-Length")
                if declared is not None and not response.chunked:
                    require(len(raw) == int(declared), "Incomplete HTTP body: fewer bytes than Content-Length")
                require(response.status == status, f"GET {route}: expected HTTP {status}, got {response.status}")
                require(response.headers.get_content_type() == "application/json", f"GET {route}: expected application/json")
                data = json.loads(raw)
                require(isinstance(data, dict), "Expected a JSON object")
                if status != 200:
                    require(data.get("error") == ("invalid query" if status == 400 else "not found"), f"Unexpected error body: {data!r}")
                else:
                    eligible = sorted((row for row in before if row["id"] > after), key=lambda row: row["id"])
                    expected = eligible[:limit]
                    cursor = expected[-1]["id"] if len(eligible) > limit else None
                    items = data.get("items")
                    require(isinstance(items, list) and len(items) == len(expected), f"Wrong page length for {route}: {data!r}")
                    for actual, wanted in zip(items, expected):
                        require(isinstance(actual, dict), "A page item must be an object")
                        require(type(actual.get("id")) is int and type(actual.get("quantity")) is int, "Item numbers must be JSON integers")
                        require(all(actual.get(key) == value for key, value in wanted.items()), f"Wrong record/order: {actual!r}, expected {wanted!r}")
                    require("next_after" in data and data["next_after"] == cursor and type(data["next_after"]) is type(cursor), f"Wrong continuation for {route}: {data!r}")
                require(json.dumps(server.supplies, sort_keys=True) == json.dumps(before, sort_keys=True), "A read changed the supplied snapshot or its order")
                return data
            finally:
                client.close()
        try:
            operation(request)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=1)

    def traverse(request):
        request("/supplies")
        for limit in [1, 2, 4]:
            after = 0
            for _ in range(9):
                page = request(f"/supplies?after={after}&limit={limit}", after=after, limit=limit)
                if page["next_after"] is None:
                    break
                after = page["next_after"]
            else:
                raise AssertionError("Continuation did not terminate")

    for index, snapshot in enumerate(snapshots):
        check(f"Snapshot {index + 1}: defaults, stable pages and final continuation", lambda rows=snapshot: exercise(rows, traverse))

    def bounds(request):
        for after in [2, 17, 43, 72, 99999, 100000]:
            request(f"/supplies?after={after}&limit=3", after=after, limit=3)
        request("/supplies?after=%30%30%31&limit=%30%32", after=1, limit=2)
        request("/supplies?trace=&trace=ignored&next=/missing&limit=4", limit=4)
    check("Cursor bounds, encoded values and unknown parameters", lambda: exercise(snapshots[0], bounds))

    def invalid(request):
        queries = ["limit=", "limit", "limit=0", "limit=5", "limit=-1", "limit=+2", "limit=1.0", "limit=no", "limit=%D9%A2",
                   "limit=2&limit=2", "after=", "after", "after=-1", "after=100001", "after=1.0", "after=abc", "after=0&after=0", "after=%20",
                   "limit=2%0A", "after=0%0A", "limit=2%20", "after=0%09"]
        for query in queries:
            request("/supplies?" + query, status=400)
    check("Invalid query values and duplicate known parameters", lambda: exercise(snapshots[0], invalid))

    def routes(request):
        for route in ["/", "/missing?next=/supplies", "/supplies/", "/supplies/extra", "/supplies-list", "/missing?limit=0"]:
            request(route, status=404)
    check("Exact route and unknown-path precedence", lambda: exercise(snapshots[0], routes))

    def repeat(request):
        first = request("/supplies?limit=1", limit=1)
        request("/supplies?after=18&limit=4", after=18, limit=4)
        request("/supplies?limit=0", status=400)
        request("/supplies?after=6", after=6)
        again = request("/supplies?limit=1", limit=1)
        require(first["items"] == again["items"] and first["next_after"] == again["next_after"], "Interleaved clients changed a repeated page")
    check("Read-only snapshot and independent interleaved clients", lambda: exercise(snapshots[0], repeat))


try:
    trial()
except Exception as error:
    CHECKS.append({"name": "Load HTTP trial", "passed": False, "detail": f"{type(error).__name__}: {error}"[:1500]})
print(json.dumps({"checks": CHECKS}))
sys.exit(0 if CHECKS and all(item["passed"] for item in CHECKS) else 1)
