"""Terminal demo: python3 -B demo.py 429:2,timeout,503,ok

Starts a flaky relay on loopback (a test tool, not a model) that answers request.json with the
fault sequence you name, runs wrapper.call against it with policy.json and real sleeps, then prints
the result and the ledger lines of that call. Faults: ok, length, cut (streams only), 429, 429:<secs>
(Retry-After), quota, 400, 500, 503, timeout. The last fault repeats forever. Add --stream to ask for
a streamed answer.
"""
import json
import socket
import socketserver
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import wrapper

ANSWER = "Two filters are reserved for the night shift; eleven remain in stock."


class FlakyRelay(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True
    block_on_close = False

    def __init__(self, faults):
        super().__init__(("127.0.0.1", 0), Handler)
        self.faults = faults

    def server_bind(self):
        socketserver.TCPServer.server_bind(self)
        self.server_name = "localhost"
        self.server_port = self.server_address[1]

    def handle_error(self, request, client_address):
        pass

    def next_fault(self):
        return self.faults.pop(0) if len(self.faults) > 1 else self.faults[0]


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def reply(self, status, payload, headers=()):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        for name, value in headers:
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def chunk(self, payload):
        data = f"data: {payload if isinstance(payload, str) else json.dumps(payload)}\n\n".encode("utf-8")
        self.wfile.write(f"{len(data):x}\r\n".encode("ascii") + data + b"\r\n")
        self.wfile.flush()

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        kind, _, retry_after = self.server.next_fault().partition(":")
        print(f"  relay: attempt with Idempotency-Key {self.headers.get('Idempotency-Key')!r} -> {kind}{' Retry-After ' + retry_after if retry_after else ''}", file=sys.stderr)
        headers = [("Retry-After", retry_after)] if retry_after else []
        if kind == "429":
            return self.reply(429, {"error": {"message": "Rate limit reached for requests", "type": "requests", "code": "rate_limit_exceeded"}}, headers)
        if kind == "quota":
            return self.reply(429, {"error": {"message": "You exceeded your current quota, please check your plan and billing details.", "type": "insufficient_quota", "code": "insufficient_quota"}}, headers)
        if kind == "400":
            return self.reply(400, {"error": {"message": "Unsupported parameter: 'relay_mode'", "type": "invalid_request_error"}})
        if kind in ("500", "503"):
            return self.reply(int(kind), {"error": {"message": "The engine is currently overloaded.", "type": "server_error"}}, headers)
        if kind == "timeout":
            time.sleep(60)  # longer than any request_timeout the demo allows
        words = ANSWER.split(" ")
        produced = len(words) // 2 if kind == "length" else len(words)
        usage = {"prompt_tokens": 41, "completion_tokens": produced, "total_tokens": 41 + produced}
        finish = "length" if kind == "length" else "stop"
        if body.get("stream") is True:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            cut_at = produced // 2 if kind == "cut" else produced
            for index in range(cut_at):
                self.chunk({"choices": [{"index": 0, "delta": {"content": words[index] + (" " if index < produced - 1 else "")}, "finish_reason": None}]})
            if kind == "cut":
                self.connection.shutdown(socket.SHUT_RDWR)
                self.close_connection = True
                return
            self.chunk({"choices": [{"index": 0, "delta": {}, "finish_reason": finish}]})
            self.chunk({"choices": [], "usage": usage})
            self.chunk("[DONE]")
            self.wfile.write(b"0\r\n\r\n")
            self.close_connection = True
            return
        self.reply(200, {"id": "chatcmpl-demo", "object": "chat.completion", "model": body.get("model"), "choices": [{"index": 0, "message": {"role": "assistant", "content": " ".join(words[:produced])}, "finish_reason": finish}], "usage": usage})


if __name__ == "__main__":
    arguments = [argument for argument in sys.argv[1:] if argument != "--stream"]
    faults = (arguments[0] if arguments else "429:2,timeout,503,ok").split(",")
    with open("policy.json", encoding="utf-8") as file:
        policy = json.load(file)
    with open("request.json", encoding="utf-8") as file:
        request = json.load(file)
    if "--stream" in sys.argv:
        request["stream"] = True
    policy["request_timeout"] = min(float(policy["request_timeout"]), 2.0)
    relay = FlakyRelay(faults)
    thread = threading.Thread(target=relay.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
    thread.start()
    print(f"flaky relay on http://127.0.0.1:{relay.server_port}/v1 with faults {faults}", file=sys.stderr)
    started = time.monotonic()
    result = wrapper.call(request, base_url=f"http://127.0.0.1:{relay.server_port}/v1", policy=policy, ledger_path="ledger.jsonl", effect=lambda done: print("  effect: reservation committed once", file=sys.stderr))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"real time {time.monotonic() - started:.2f} s; ledger lines for this call:", file=sys.stderr)
    with open("ledger.jsonl", encoding="utf-8") as file:
        for line in file:
            if json.loads(line).get("key") == result.get("key"):
                print("  " + line.rstrip(), file=sys.stderr)
    relay.shutdown()
    relay.server_close()
