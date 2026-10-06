import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # The starter ignores routing, query validation and pagination on purpose.
        body = json.dumps({"items": getattr(self.server, "supplies"), "next_after": None}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    server = HTTPServer(("127.0.0.1", 45110), Handler)
    setattr(server, "supplies", json.loads(Path(__file__).with_name("supplies.json").read_text()))
    print("Supply beacon: http://127.0.0.1:45110/supplies", flush=True)
    server.serve_forever()
