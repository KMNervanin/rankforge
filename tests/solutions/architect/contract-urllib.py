import json
import http.client
from urllib.error import HTTPError, URLError
from urllib.request import build_opener, ProxyHandler, HTTPRedirectHandler, Request


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def probe(base_url, scenario):
    opener = build_opener(ProxyHandler({}), NoRedirect())
    event = scenario["delivery"]
    conflict = dict(event, quantity=event["quantity"] + 1)
    full = dict(event, view="full")
    summary = dict(id=event["id"], quantity=event["quantity"], view="summary")
    requests = [
        ("create", "POST", "/deliveries", event, 201, event),
        ("replay", "POST", "/deliveries", event, 200, event),
        ("conflict", "POST", "/deliveries", conflict, 409, {"error": "conflict"}),
        ("effects", "GET", "/stats", None, 200, {"effects": 1}),
        ("missing", "GET", f"/deliveries/{event['id']}/missing?view=full", None, 404, {"error": "not_found"}),
        ("query", "GET", f"/deliveries/{event['id']}?view=summary", None, 200, summary),
        ("read", "GET", f"/deliveries/{event['id']}?view=full", None, 200, full),
    ]
    results = {}
    transport = None
    for name, method, path, payload, expected_status, fields in requests:
        if transport is not None:
            results[name] = False, "Transport failed; skipped"
            continue
        request = Request(base_url + path, data=None if payload is None else json.dumps(payload, ensure_ascii=False).encode(), method=method, headers={"Content-Type": "application/json"})
        try:
            try:
                response = opener.open(request, timeout=scenario["timeout_s"])
            except HTTPError as error:
                response = error
            with response:
                raw = response.read(8192)
                media = response.headers.get("Content-Type", "").partition(";")[0].strip().casefold()
                valid = response.code == expected_status and media == "application/json" and response.headers.get("X-Contract") == "delivery-v1"
                try:
                    decoded = json.loads(raw)
                    valid = valid and isinstance(decoded, dict)
                    for field, expected in fields.items():
                        valid = valid and field in decoded and type(decoded[field]) is type(expected) and decoded[field] == expected
                except (ValueError, UnicodeError):
                    valid = False
                results[name] = bool(valid), f"Observed HTTP {response.code}, {len(raw)} body bytes"
        except (TimeoutError, URLError, OSError, http.client.HTTPException) as error:
            reason = error.reason if isinstance(error, URLError) else error
            transport = "timeout" if isinstance(reason, TimeoutError) else "unavailable"
            results[name] = False, str(reason)
    return {"status": transport or ("passed" if all(value[0] for value in results.values()) else "failed"),
            "checks": [dict(name=name, passed=passed, detail=detail) for name, (passed, detail) in results.items()]}
