import heapq
import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qsl


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def send_json(self, code, payload):
        body = json.dumps(dict(payload, diagnostic="extra fields are allowed"), indent=2).encode()
        self.send_response(code)
        self.send_header("Content-Type", "Application/JSON")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        route, _, raw = self.path.partition("?")
        if route != "/supplies":
            self.send_json(404, {"error": "not found"})
            return
        values = {"limit": 2, "after": 0}
        seen = set()
        for name, text in parse_qsl(raw, keep_blank_values=True):
            if name not in values:
                continue
            low, high = (1, 4) if name == "limit" else (0, 100000)
            if name in seen or not text or any(char not in "0123456789" for char in text) or not low <= int(text) <= high:
                self.send_json(400, {"error": "invalid query"})
                return
            values[name] = int(text)
            seen.add(name)
        candidates = (row for row in getattr(self.server, "supplies") if row["id"] > values["after"])
        page = heapq.nsmallest(values["limit"] + 1, candidates, key=lambda row: row["id"])
        more = len(page) > values["limit"]
        if more:
            page.pop()
        self.send_json(200, {"next_after": page[-1]["id"] if more else None, "items": page})
