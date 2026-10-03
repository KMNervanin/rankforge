import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlsplit


class Relay(BaseHTTPRequestHandler):
    def do_GET(self):
        healthy = urlsplit(self.path).path == "/health"
        self.send_response(200 if healthy else 404)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(
            {"status": "ok", "service": "relay"} if healthy else {"error": "not found"}
        ).encode())


HTTPServer(("0.0.0.0", 8000), Relay).serve_forever()
