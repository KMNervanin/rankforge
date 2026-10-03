import json
import os
import socketserver
from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(503)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"relay offline")


class LocalServer(HTTPServer):
    def server_bind(self):
        # Local labs do not need reverse DNS, which may stall on a VPN.
        socketserver.TCPServer.server_bind(self)
        self.server_name = "localhost"
        self.server_port = self.server_address[1]


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "45101"))
    print(f"Relay listening on http://127.0.0.1:{port}", flush=True)
    LocalServer(("127.0.0.1", port), Handler).serve_forever()
