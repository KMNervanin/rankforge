# Field manual — words into a record

Supply requests reach the outpost as free text: "we need twelve water filters by tomorrow, urgent, Mara". The assistant must turn each into a record the stock system can act on, and a record that merely looks right is worse than no record. The starter asks the model for JSON and takes whatever parses; that is the deliberate defect.

## Workshop and entry point

Python 3.10 or later, standard library only. Edit `extract.py` and `schema.json`, and keep three names importable: `load_schema`, `validate` and `extract`. `catalog.json` is the outpost's stock catalog for your own runs; Verify passes its own catalog with fresh maxima, so read every item, unit and bound from the `catalog` argument. `requests.json` holds five request texts with the record a human would write.

`python3 -B demo.py` runs every fixture through `extract` against the endpoint in `llm.json` in prompt-only mode; `python3 -B demo.py --schema` sends the schema with the request. Add your own text as an argument to try one request. An API key, if your endpoint needs one, lives in `LLM_API_KEY`, never in a file of this workspace.

## Two kinds of valid

A JSON Schema says what shape a record has: which keys, which types, which enum values, which bounds. A record can satisfy all of that and still be wrong for the outpost: `{"item": "plasma coil", "quantity": 1, …}` is perfectly shaped and names something the catalog has never stocked. The schema check is **syntactic** validity; the catalog check is **domain** validity. Keep them apart in code and in the error messages, because they are fixed differently: a syntactic error means the model did not follow the format, a domain error means the model (or the requester) is asking for something that does not exist, and no amount of format enforcement will catch it. OpenAI's own guide says it plainly: structured outputs "can still contain mistakes".

Servers can enforce the shape for you. With `response_format: {"type": "json_schema", "json_schema": {"name": "…", "schema": {…}}}` llama.cpp, vLLM and Ollama compile the schema into a grammar and the model can only emit tokens that fit it; OpenAI's Structured Outputs do the same when `strict: true` is set, but only for a schema subset (every property listed in `required`, `additionalProperties: false`, optional fields expressed as nullable types). The published schema keeps `notes` optional because the local servers accept it; add `strict` only after adapting the schema to that subset. Two things escape enforcement everywhere: a refusal (OpenAI returns it in `message.refusal` with `content` null) and truncation (`finish_reason` `length` cuts the record mid-way, grammar or not).

## Complete public contract

`schema.json` is the published schema of a supply request record, loaded by `load_schema(path=SCHEMA_PATH) -> dict`. It is a JSON Schema object with `type: "object"`, `properties` for `item` (string, minLength 1), `quantity` (integer, minimum 1), `unit` (enum `piece`, `box`, `litre`, `kilogram`), `urgency` (enum `low`, `normal`, `high`), `requester` (string, minLength 1) and `notes` (string); `required` lists the first five, `additionalProperties` is `false`. Verify's schemas use only these keywords: `type`, `properties`, `required`, `additionalProperties`, `enum`, `minimum`, `maximum`, `minLength`; a hand-written validator for that subset is enough, and `title` or `description` are ignored.

`validate(record, catalog, schema=None) -> list[str]` returns `[]` for a valid record. `catalog` is a list of `{"item", "unit", "max_quantity"}` as in `catalog.json`; `schema` defaults to `load_schema()`. Every error is one string; Verify matches only the prefix and the field or item name, the rest of the wording is yours:

1. **Syntactic errors start with `schema: `** and name the offending field: a value of the wrong type (a JSON boolean is not an integer, nor is a number with a fractional part such as `12.0`; an optional field that is present must still have its type, so `"notes": null` is an error), a missing required key, a key the schema does not list, a value outside its enum, a number below `minimum` or above `maximum`, a string shorter than `minLength`, or a value that is not an object at all.
2. **Domain errors start with `domain: `** and are checked only when the list of schema errors is empty, on a record whose shape is already trusted: the item is not in the catalog (names compared case-insensitively after trimming; the error quotes the item as written; when the item is unknown, that is the only domain error), the unit is not the catalog unit of that item, or the quantity exceeds the item's `max_quantity`. A quantity equal to the maximum is valid.

A worked example with the catalog of this workspace: `{"item": "water filter", "quantity": 0, "unit": "box", "urgency": "high", "requester": "Mara"}` gives one error, `schema: /quantity must be at least 1, got 0`, and says nothing about the unit yet. With `quantity: 60` the schema is satisfied and the list becomes two domain errors: the unit `box` is not `piece`, and 60 exceeds the maximum 50.

`extract(text, *, base_url, model, catalog, schema=None, schema_enforced=False, max_repairs=2, max_tokens=256, temperature=0.0) -> dict` asks the model, validates, repairs within a bound and never accepts silently:

3. **One request per attempt**, `POST {base_url}/chat/completions`, with the request text as message content and every catalog item name somewhere in the messages. With `schema_enforced=True` the body carries `response_format` of type `json_schema` whose `json_schema.schema` equals the schema in use (the `schema` argument, or the published one) and whose `name` is any non-empty string. With `schema_enforced=False` the body carries no `response_format` key at all; that is the prompt-only baseline the live measurement compares against.
4. **Assess every answer.** A `finish_reason` of `length` is a failed attempt even when the cut text happens to parse; its error string mentions `length` or `truncated`. The content must parse as one JSON object (stripping code fences before parsing is your choice; Verify's faults are never fenced), then `validate` decides. A failed attempt keeps its error list.
5. **Repair within the bound.** After a failed attempt, if fewer than `max_repairs` repairs were made, send one repair request whose message content quotes every error string verbatim, the rejected output verbatim and the original request text. `max_repairs=k` means at most `k + 1` requests in total; `max_repairs=0` means a single request. A valid first answer sends nothing more.
6. **Fail visibly.** The result is a dict with `ok` (bool), `record` (the validated record when `ok`, otherwise `null`), `errors` (the last attempt's errors, `[]` when `ok`), `attempts` (one dict per request, in order, with `kind` `initial` or `repair`, `finish_reason` as returned, `content` as returned and `errors`) and `schema_enforced`. Exhausting the bound returns `ok: false` with every attempt listed; it never raises for a bad answer and never returns a record that failed validation. Transport errors (connection refused, HTTP 4xx/5xx) may raise any exception.
7. **The schema is an argument.** A schema passed as `schema=` replaces the published one for both the request and the validation, so adding an optional field means changing one JSON file, not the code.

## What Verify runs

- A **scripted adapter**: a loopback server that speaks the contract above and answers from a script in order: malformed JSON, a JSON array, a complete-looking record with `finish_reason` `length`, a record with an extra field, a record naming an item absent from the catalog, then a corrected record; and a script that never corrects itself, with a fresh `max_repairs`, to count the requests. It records every request body, including whether `response_format` was present and which schema it carried. It is a labeled test tool, not a model.
- A **live measurement**: three fixture texts through your `extract` against the endpoint in `llm.json`, once prompt-only and once schema-enforced, each with `max_repairs=0`, reporting how many answers were schema-valid, catalog-valid and exact on item and quantity. The numbers are a measurement of one run, never a pass or fail on the model. The sample shrinks to one fixture when the warm-up ping takes over 2 seconds, and the whole live section is cut off after 20 seconds as environment blocked. No model id in `llm.json`, or no answer within 15 seconds, is **Environment blocked**: nothing fails, nothing passes. Warm the model up with the demo first.

On a local 4B model the prompt-only run typically returns the record inside a ```` ```json ```` fence and writes `"notes": null`, both schema errors; the schema-enforced run returns bare, valid objects. Strip the fence and the prompt-only rate rises, but the `null` stays: that is what the grammar fixes and the prompt alone does not.

Two different implementations pass: a recursive schema interpreter with `urllib.request` that continues the conversation for the repair, and a flat field-table validator with `http.client` that sends one fresh message. No specific structure of `extract.py` is required beyond the three importable names.

## Sources

- OpenAI Structured Outputs guide: `response_format` `json_schema`, `strict`, the supported schema subset, refusals and truncation as the two ways out of the schema.
- Ollama OpenAI compatibility: `response_format` is a supported field of `/v1/chat/completions`; `docs/capabilities/structured-outputs.mdx` for the native `format` field.
- llama.cpp server README: JSON schema compiled to a GBNF grammar; vLLM structured outputs (xgrammar, guidance, outlines).
- JSON Schema 2020-12 validation vocabulary: `type`, `enum`, `required`, `additionalProperties`, `minimum`, `maximum`, `minLength`.
