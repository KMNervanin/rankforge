"""Extractor: a recursive JSON Schema interpreter, urllib.request, repair as a continued conversation."""
import json
import os
import urllib.request

SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.json")


def load_schema(path=SCHEMA_PATH):
    with open(path, encoding="utf-8") as file:
        return json.load(file)


def _is_type(value, name):
    if name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if name == "boolean":
        return isinstance(value, bool)
    return isinstance(value, {"string": str, "object": dict, "array": list, "null": type(None)}[name])


def _describe(value):
    return {bool: "boolean", int: "integer", float: "number", str: "string", dict: "object", list: "array", type(None): "null"}[type(value)]


def _check(value, schema, path, errors):
    """Walk one schema node; every message starts with 'schema: ' and the JSON-pointer path."""
    where = path or "/"
    expected = schema.get("type")
    if expected is not None:
        allowed = expected if isinstance(expected, list) else [expected]
        if not any(_is_type(value, name) for name in allowed):
            errors.append(f"schema: {where} expected {' or '.join(allowed)}, got {_describe(value)} {json.dumps(value)[:60]}")
            return
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"schema: {where} must be one of {json.dumps(schema['enum'])}, got {json.dumps(value)[:60]}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"schema: {where} must be at least {schema['minimum']}, got {value}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"schema: {where} must be at most {schema['maximum']}, got {value}")
    if isinstance(value, str) and "minLength" in schema and len(value) < schema["minLength"]:
        errors.append(f"schema: {where} must have at least {schema['minLength']} characters")
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"schema: {path}/{key} is required")
        for key, item in value.items():
            if key in properties:
                _check(item, properties[key], f"{path}/{key}", errors)
            elif schema.get("additionalProperties") is False:
                errors.append(f"schema: {path}/{key} is not a property of the record")
    if isinstance(value, list) and "items" in schema:
        for index, item in enumerate(value):
            _check(item, schema["items"], f"{path}/{index}", errors)


def validate(record, catalog, schema=None):
    schema = schema or load_schema()
    errors = []
    _check(record, schema, "", errors)
    if errors:
        return errors
    by_name = {entry["item"].strip().lower(): entry for entry in catalog}
    entry = by_name.get(str(record["item"]).strip().lower())
    if entry is None:
        return [f"domain: /item {json.dumps(record['item'])} is not in the catalog"]
    if record["unit"] != entry["unit"]:
        errors.append(f"domain: /unit {json.dumps(record['unit'])} does not match the catalog unit {json.dumps(entry['unit'])} for {json.dumps(entry['item'])}")
    if record["quantity"] > entry["max_quantity"]:
        errors.append(f"domain: /quantity {record['quantity']} exceeds the catalog maximum {entry['max_quantity']} for {json.dumps(entry['item'])}")
    return errors


def _complete(messages, *, base_url, model, max_tokens, temperature, response_format):
    body = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature}
    if response_format is not None:
        body["response_format"] = response_format
    headers = {"Content-Type": "application/json"}
    key = os.environ.get("LLM_API_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    request = urllib.request.Request(base_url.rstrip("/") + "/chat/completions", data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))
    choice = payload["choices"][0]
    message = choice.get("message") or {}
    return message.get("content"), message.get("refusal"), choice.get("finish_reason")


def _instructions(schema, catalog):
    lines = [f"- {entry['item']} (unit: {entry['unit']}, at most {entry['max_quantity']})" for entry in catalog]
    return ("You turn a supply request from an outpost into one JSON object and nothing else: no prose, no code fences.\n"
            "The object must satisfy this JSON Schema:\n" + json.dumps(schema) + "\n"
            "Use the exact catalog name of the item and its catalog unit. Known items:\n" + "\n".join(lines) + "\n"
            "urgency is high when the request says urgent or names a deadline within a day, low when it says no rush, otherwise normal.")


def _assess(content, refusal, finish_reason, schema, catalog):
    if refusal:
        return [f"schema: the model refused instead of answering: {refusal}"], None
    if finish_reason == "length":
        return ["schema: the output was truncated (finish_reason length); a cut record is never complete"], None
    try:
        record = json.loads(content or "")
    except ValueError as error:
        return [f"schema: / the output is not a JSON object ({error})"], None
    errors = validate(record, catalog, schema)
    return errors, (record if not errors else None)


def extract(text, *, base_url, model, catalog, schema=None, schema_enforced=False, max_repairs=2, max_tokens=256, temperature=0.0):
    schema = schema or load_schema()
    response_format = {"type": "json_schema", "json_schema": {"name": "supply_request", "schema": schema}} if schema_enforced else None
    messages = [{"role": "system", "content": _instructions(schema, catalog)},
                {"role": "user", "content": f"Supply request:\n{text}\n\nReply with one JSON object only."}]
    attempts = []
    for attempt in range(max_repairs + 1):
        content, refusal, finish_reason = _complete(messages, base_url=base_url, model=model, max_tokens=max_tokens, temperature=temperature, response_format=response_format)
        errors, record = _assess(content, refusal, finish_reason, schema, catalog)
        attempts.append({"kind": "initial" if attempt == 0 else "repair", "finish_reason": finish_reason, "content": content if content is not None else "", "errors": errors})
        if not errors:
            return {"ok": True, "record": record, "errors": [], "attempts": attempts, "schema_enforced": schema_enforced}
        messages.append({"role": "assistant", "content": content if content is not None else refusal or ""})
        messages.append({"role": "user", "content": "Your previous answer was rejected:\n" + "\n".join(f"- {error}" for error in errors)
                         + f"\n\nThe original supply request:\n{text}\n\nReply with one corrected JSON object only."})
    return {"ok": False, "record": None, "errors": attempts[-1]["errors"], "attempts": attempts, "schema_enforced": schema_enforced}
