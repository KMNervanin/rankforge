import http.client
import json
from urllib.parse import urlsplit


def probe(base_url, scenario):
    """The starter checks a status only. Extend it using the published contract."""
    endpoint = urlsplit(base_url)
    connection = http.client.HTTPConnection(endpoint.hostname, endpoint.port, timeout=scenario["timeout_s"])
    checks = [{"name": name, "passed": False, "detail": "Not checked yet."}
              for name in ("create", "replay", "conflict", "read", "query", "missing", "effects")]
    try:
        connection.request("POST", "/deliveries", json.dumps(scenario["delivery"]), {"Content-Type": "application/json"})
        response = connection.getresponse()
        checks[0] = {"name": "create", "passed": response.status == 201, "detail": f"HTTP {response.status}; body and headers not checked."}
        response.read()
    except TimeoutError:
        return {"status": "timeout", "checks": checks}
    except OSError:
        return {"status": "unavailable", "checks": checks}
    finally:
        connection.close()
    return {"status": "failed", "checks": checks}
