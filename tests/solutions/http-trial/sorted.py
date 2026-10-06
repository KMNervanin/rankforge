import json
import re
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlsplit


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def reply(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlsplit(self.path)
        if url.path != "/supplies":
            self.reply(404, {"error": "not found"})
            return
        query = parse_qs(url.query, keep_blank_values=True)
        numbers = {}
        for key, default, minimum, maximum in [("after", "0", 0, 100000), ("limit", "2", 1, 4)]:
            values = query.get(key, [default])
            if len(values) != 1 or not re.fullmatch(r"[0-9]+", values[0]):
                self.reply(400, {"error": "invalid query"})
                return
            value = int(values[0])
            if not minimum <= value <= maximum:
                self.reply(400, {"error": "invalid query"})
                return
            numbers[key] = value
        after, limit = numbers["after"], numbers["limit"]
        rows = sorted((row for row in getattr(self.server, "supplies") if row["id"] > after), key=lambda row: row["id"])
        items = rows[:limit]
        cursor = items[-1]["id"] if len(rows) > limit else None
        self.reply(200, {"items": items, "next_after": cursor})
