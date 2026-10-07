import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        ok = urlsplit(self.path).path == "/health"
        body = json.dumps({"status": "ok", "service": "relay"} if ok else {"error": "not found"}).encode()
        self.send_response(200 if ok else 404)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
