import http.client
import json
from urllib.parse import urlsplit


def probe(base_url, scenario):
    delivery = scenario["delivery"]
    identity = delivery["id"]
    plan = [
        ("create", "POST", "/deliveries", delivery, 201, delivery),
        ("replay", "POST", "/deliveries", delivery, 200, delivery),
        ("conflict", "POST", "/deliveries", {**delivery, "quantity": delivery["quantity"] + 1}, 409, {"error": "conflict"}),
        ("read", "GET", f"/deliveries/{identity}?view=full", None, 200, {**delivery, "view": "full"}),
        ("query", "GET", f"/deliveries/{identity}?view=summary", None, 200, {"id": identity, "quantity": delivery["quantity"], "view": "summary"}),
        ("missing", "GET", f"/deliveries/{identity}/missing?view=full", None, 404, {"error": "not_found"}),
        ("effects", "GET", "/stats", None, 200, {"effects": 1}),
    ]
    target = urlsplit(base_url)
    checks = []
    state = None
    for name, method, route, body, status, expected in plan:
        if state:
            checks.append(dict(name=name, passed=False, detail="Not attempted after transport failure"))
            continue
        connection = http.client.HTTPConnection(target.hostname, target.port, timeout=scenario["timeout_s"])
        try:
            connection.request(method, route, json.dumps(body).encode("utf-8") if body is not None else None, {"Content-Type": "application/json"})
            response = connection.getresponse()
            raw = response.read(8192)
            try:
                parsed = json.loads(raw)
            except (ValueError, UnicodeError):
                parsed = None
            passed = response.status == status and response.getheader("X-Contract") == "delivery-v1" and (response.getheader("Content-Type") or "").split(";", 1)[0].strip().lower() == "application/json"
            passed = passed and isinstance(parsed, dict) and all(type(parsed.get(key)) is type(value) and parsed[key] == value for key, value in expected.items())
            checks.append(dict(name=name, passed=passed, detail=f"HTTP {response.status}; body={raw.decode('utf-8', errors='replace')}"))
        except TimeoutError:
            state = "timeout"
            checks.append(dict(name=name, passed=False, detail="Timed out before a complete response"))
        except (OSError, http.client.HTTPException) as error:
            state = "unavailable"
            checks.append(dict(name=name, passed=False, detail=type(error).__name__))
        finally:
            connection.close()
    return dict(status=state or ("passed" if all(c["passed"] for c in checks) else "failed"), checks=checks)
