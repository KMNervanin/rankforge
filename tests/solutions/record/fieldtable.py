"""Extractor: a flat field-table validator built from the schema's properties, http.client, repair as one fresh message."""
from __future__ import annotations

import http.client
import json
import os
from dataclasses import dataclass, field
from urllib.parse import urlsplit

SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.json")


def load_schema(path: str = SCHEMA_PATH) -> dict:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


@dataclass
class Attempt:
    kind: str
    finish_reason: str | None
    content: str
    errors: list[str] = field(default_factory=list)


def _kind_of(value) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    return "null"


def _field_errors(name: str, value, rule: dict) -> list[str]:
    """Check one top-level field against its property rule; messages carry the schema: prefix."""
    wanted = rule.get("type")
    wanted = wanted if isinstance(wanted, list) or wanted is None else [wanted]
    actual = _kind_of(value)
    if wanted is not None and actual not in wanted and not (actual == "integer" and "number" in wanted):
        return [f"schema: /{name} should be {' or '.join(wanted)}, got {actual}"]
    problems = []
    if "enum" in rule and value not in rule["enum"]:
        problems.append(f"schema: /{name} should be one of {', '.join(map(str, rule['enum']))}, got {value!r}")
    if actual in ("integer", "number"):
        if "minimum" in rule and value < rule["minimum"]:
            problems.append(f"schema: /{name} should be >= {rule['minimum']}, got {value}")
        if "maximum" in rule and value > rule["maximum"]:
            problems.append(f"schema: /{name} should be <= {rule['maximum']}, got {value}")
    if actual == "string" and len(value) < rule.get("minLength", 0):
        problems.append(f"schema: /{name} should not be shorter than {rule['minLength']} characters")
    return problems


def syntactic(record, schema: dict) -> list[str]:
    if not isinstance(record, dict):
        return [f"schema: / expected an object, got {_kind_of(record)}"]
    table = schema.get("properties", {})
    problems = [f"schema: /{name} is required but missing" for name in schema.get("required", []) if name not in record]
    for name, value in record.items():
        if name in table:
            problems.extend(_field_errors(name, value, table[name]))
        elif schema.get("additionalProperties", True) is False:
            problems.append(f"schema: /{name} is not allowed (additionalProperties is false)")
    return problems


def domain(record: dict, catalog: list[dict]) -> list[str]:
    wanted = str(record["item"]).strip().casefold()
    entry = next((row for row in catalog if row["item"].strip().casefold() == wanted), None)
    if entry is None:
        return [f"domain: /item {record['item']!r} is not a catalog item"]
    problems = []
    if record["unit"] != entry["unit"]:
        problems.append(f"domain: /unit {record['unit']!r} is not the catalog unit {entry['unit']!r} of {entry['item']!r}")
    if record["quantity"] > entry["max_quantity"]:
        problems.append(f"domain: /quantity {record['quantity']} is above the catalog maximum {entry['max_quantity']} of {entry['item']!r}")
    return problems


def validate(record, catalog, schema=None) -> list[str]:
    schema = schema if schema is not None else load_schema()
    problems = syntactic(record, schema)
    return problems if problems else domain(record, catalog)


def _post(base_url: str, payload: dict) -> dict:
    url = urlsplit(base_url)
    connection = http.client.HTTPConnection(url.hostname, url.port or 80, timeout=60)
    headers = {"Content-Type": "application/json"}
    if os.environ.get("LLM_API_KEY"):
        headers["Authorization"] = "Bearer " + os.environ["LLM_API_KEY"]
    try:
        connection.request("POST", url.path.rstrip("/") + "/chat/completions", body=json.dumps(payload), headers=headers)
        response = connection.getresponse()
        raw = response.read()
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status}: {raw[:200]!r}")
    finally:
        connection.close()
    return json.loads(raw)


def _prompt(text: str, schema: dict, catalog: list[dict], previous: Attempt | None) -> str:
    catalog_lines = "\n".join(f"{row['item']}: unit {row['unit']}, max {row['max_quantity']}" for row in catalog)
    parts = ["Read the supply request below and answer with exactly one JSON object matching this schema, nothing else:", json.dumps(schema),
             "Catalog (use the exact item name and unit):", catalog_lines,
             "urgency: high for urgent or same-day requests, low for 'no rush', otherwise normal.",
             "Supply request:", text]
    if previous is not None:
        parts += ["Your earlier answer was:", previous.content, "It was rejected for these reasons:", *previous.errors, "Fix every reason and answer again with one JSON object only."]
    return "\n".join(parts)


def extract(text, *, base_url, model, catalog, schema=None, schema_enforced=False, max_repairs=2, max_tokens=256, temperature=0.0) -> dict:
    schema = schema if schema is not None else load_schema()
    attempts: list[Attempt] = []
    previous: Attempt | None = None
    while len(attempts) <= max_repairs:
        payload = {"model": model, "messages": [{"role": "user", "content": _prompt(text, schema, catalog, previous)}], "max_tokens": max_tokens, "temperature": temperature}
        if schema_enforced:
            payload["response_format"] = {"type": "json_schema", "json_schema": {"name": "supply_request", "schema": schema}}
        choice = _post(base_url, payload)["choices"][0]
        message = choice.get("message") or {}
        attempt = Attempt("initial" if not attempts else "repair", choice.get("finish_reason"), message.get("content") or "")
        if message.get("refusal"):
            attempt.errors = [f"schema: refused by the model: {message['refusal']}"]
            attempt.content = str(message["refusal"])
        elif attempt.finish_reason == "length":
            attempt.errors = ["schema: truncated by max_tokens (finish_reason length), the record is incomplete"]
        else:
            try:
                parsed = json.loads(attempt.content)
            except ValueError:
                attempt.errors = ["schema: the answer is not valid JSON"]
            else:
                attempt.errors = validate(parsed, catalog, schema)
        attempts.append(attempt)
        if not attempt.errors:
            return {"ok": True, "record": parsed, "errors": [], "attempts": [vars(item) for item in attempts], "schema_enforced": schema_enforced}
        previous = attempt
    return {"ok": False, "record": None, "errors": list(attempts[-1].errors), "attempts": [vars(item) for item in attempts], "schema_enforced": schema_enforced}
