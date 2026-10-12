"""Turn a free-text supply request into a record for the operator assistant.

Starter: it asks the model for JSON and usually gets some. See LEARN.md for the complete
contract that Verify checks; this file passes none of its hard cases on purpose.
"""
import json
import os
import urllib.request

SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.json")
FIELD_TYPES = {"item": str, "quantity": int, "unit": str, "urgency": str, "requester": str, "notes": str}


def load_schema(path=SCHEMA_PATH):
    with open(path, encoding="utf-8") as file:
        return json.load(file)


def validate(record, catalog, schema=None):
    errors = []
    if not isinstance(record, dict):
        return ["the output is not a JSON object"]
    for field, kind in FIELD_TYPES.items():
        if field == "notes":
            continue
        if field not in record:
            errors.append(f"{field} is missing")
        elif not isinstance(record[field], kind):
            errors.append(f"{field} must be a {kind.__name__}")
    return errors


def _complete(messages, *, base_url, model, max_tokens, temperature):
    body = json.dumps({"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature}).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    key = os.environ.get("LLM_API_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    request = urllib.request.Request(base_url.rstrip("/") + "/chat/completions", data=body, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))
    choice = payload["choices"][0]
    return choice["message"].get("content") or "", choice.get("finish_reason")


def extract(text, *, base_url, model, catalog, schema=None, schema_enforced=False, max_repairs=2, max_tokens=256, temperature=0.0):
    schema = schema or load_schema()
    items = ", ".join(entry["item"] for entry in catalog)
    messages = [
        {"role": "system", "content": "Extract the supply request as one JSON object with the keys item, quantity, unit, urgency, requester and optionally notes. Known items: " + items + "."},
        {"role": "user", "content": text},
    ]
    attempts = []
    record = None
    for attempt in range(5):
        content, finish_reason = _complete(messages, base_url=base_url, model=model, max_tokens=max_tokens, temperature=temperature)
        try:
            record = json.loads(content)
            errors = validate(record, catalog)
        except ValueError:
            errors = ["the output is not JSON"]
        attempts.append({"kind": "initial" if attempt == 0 else "repair", "finish_reason": finish_reason, "content": content, "errors": errors})
        if not errors:
            break
        messages.append({"role": "assistant", "content": content})
        messages.append({"role": "user", "content": "That was not valid. Return the JSON object again."})
    return {"ok": True, "record": record if isinstance(record, dict) else None, "errors": [], "attempts": attempts, "schema_enforced": schema_enforced}
