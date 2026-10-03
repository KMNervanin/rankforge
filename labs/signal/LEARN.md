# Field manual — The command relay

## The idea

A process can be running while its API is wrong. A client sees three things: an HTTP status, headers and a body. A health check is a small agreement between a service and its observer.

`200` means this request succeeded. `404` means the route was not found. `503` means the service is unavailable. Returning `200` for every route hides useful information.

## Before changing anything

1. Run `python3 service.py` in the terminal. Keep that terminal open.
2. In another terminal, run the two curl commands from MISSION.md.
3. Predict which line of `Handler.do_GET` creates the incorrect response.
4. Stop the server with Ctrl+C before starting a new copy after an edit.

Save `service.py` with Cmd+S (macOS) or Ctrl+S (Linux) before restarting it. VS Code can show edits that are still only in its editor buffer; Python and the operator read the saved file on disk. Restarting an unsaved file loads the old code again. A `print` inside `do_GET` runs when a GET request is handled, not when the server merely starts, and its output appears in the server's terminal.

## A little Python

The method receives `self`, the handler for this request. `self.path` contains the request target, including a query string. `send_response` writes the status; `send_header` writes a header; `end_headers` finishes headers. `wfile.write` expects bytes, so text must be encoded.

`json.dumps` converts a Python dictionary into JSON text. `urllib.parse.urlsplit` separates a URL path from its query. Look up their examples in the linked documentation, then construct your own handler.

## Test an idea

What should `/health?probe=1` do? What about `/missing?probe=1`? A query parameter should not turn an unknown path into a health route.

Rankforge checks a fresh instance on a temporary local port. Your manually started service is for exploration; stopping it does not prevent verification. Port 45101 can be changed for your terminal run with `PORT=45111 python3 service.py`.

## Explain it

Try three short sentences: the symptom, the change, and the evidence. Use your own wording. You can ask the operator to explain a word or help you form a sentence; that becomes supported practice, not a failure.
