import type { Mission } from '../types.js'

export const mission: Mission = {
  id: 'record', chapter: 'voice', order: 3, title: 'Words into a record', subtitle: 'Separate shape from meaning', sector: 'Operator’s desk', icon: '▣',
  block: 'Calling the model', files: ['extract.py', 'schema.json', 'catalog.json'],
  nudge: 'Rumour says the relay sometimes declines instead of answering, in a field nobody reads.',
  skills: ['JSON Schema', 'Validation', 'Bounded repair'], prerequisites: ['price'], xp: 240, duration: 'Self-paced', kind: 'build',
  briefs: {
    guided: 'Supply requests arrive as free text and the stock system needs records. Publish a schema, write a validator that tells a wrong shape from a wrong item, and let the model repair its answer a bounded number of times before you say no. Hints are available; guided work earns the same rewards.',
    connected: 'Turn free text into a schema-valid record and keep two questions apart: does it have the right shape, and does it name something the catalog stocks? Prove the repair loop stops where the bound says, then measure how much a grammar-enforced request buys over a prompt.',
    independent: 'Build an extraction step with a published JSON Schema, a validator that reports syntactic and domain errors separately, a bounded repair loop that fails visibly, and a live comparison of prompt-only against schema-enforced output on your own endpoint.',
  },
  objectives: [
    'Keep extract.py importable with load_schema(path=SCHEMA_PATH) -> dict, validate(record, catalog, schema=None) -> list[str] and extract(text, *, base_url, model, catalog, schema=None, schema_enforced=False, max_repairs=2, max_tokens=256, temperature=0.0) -> dict. schema.json publishes item (string, minLength 1), quantity (integer, minimum 1), unit (enum piece, box, litre, kilogram), urgency (enum low, normal, high), requester (string, minLength 1) and optional notes (string); the first five are required and additionalProperties is false.',
    'Syntactic errors start with "schema: " and name the field: wrong type (a boolean is not an integer, nor is 12.0; a present notes must be a string), missing required key, unknown key, value outside the enum, number outside minimum or maximum, string shorter than minLength, or a value that is not an object. Verify uses only those keywords.',
    'Domain errors start with "domain: " and are checked only when no schema error exists: item not in the catalog (case-insensitive, trimmed; then the only domain error), unit different from the catalog unit, quantity above max_quantity. A well-formed record naming an item absent from the catalog is rejected.',
    'With schema_enforced=True the request carries response_format {type: "json_schema", json_schema: {name, schema}} where schema equals the schema in use; with schema_enforced=False it carries no response_format. A finish_reason of length is a failed attempt even when the text parses; its error mentions length or truncated. The first request names every catalog item in its messages.',
    'After a failed attempt send at most max_repairs repair requests, each quoting every error string, the rejected output and the original text verbatim. max_repairs=k means exactly k + 1 requests when the model never corrects itself; a valid first answer sends nothing more.',
    'The result carries ok, record (null unless ok), errors (the last attempt’s, [] when ok), attempts (one per request: kind initial or repair, finish_reason, content, errors) and schema_enforced. Exhaustion returns ok=false with every attempt; a record that failed validation is never returned.',
    'A schema passed as schema= replaces the published one for the request and the validation, so a new optional field is accepted, type-checked and preserved without code changes. Verify runs a scripted adapter (malformed, array, truncated, extra-field, unknown-item outputs, then a correction; and a never-correct script with a fresh bound) and a live measurement of prompt-only versus schema-enforced validity on the endpoint in llm.json; no model id or no answer within 15 seconds is environment blocked.',
  ],
  languageGoal: 'Distinguish two kinds of failure with one example each and say which one a tool can prevent.', prompt: 'Explain to the operator why a record can pass the schema and still be refused. Give one syntactic and one domain example from your own run, and say which of the two a schema-enforced request can prevent and which it cannot.',
  hints: ['Run the demo in both modes and read the raw content of each attempt. Which failures are about shape, and which are about the catalog? Which ones does the --schema run make disappear?', 'A schema is data: your validator walks the properties and the catalog is a lookup. If the two checks live in one function, give them two prefixes and run the second only when the first is clean.', 'Count requests, not loops: the first request plus max_repairs repairs. Put the error strings, the rejected text and the original request into the repair message, and return ok=false with the attempt log instead of the last parsed object.'],
  sources: [
    { title: 'OpenAI Structured Outputs: response_format json_schema, strict, refusals and truncation', url: 'https://developers.openai.com/api/docs/guides/structured-outputs' },
    { title: 'Ollama OpenAI compatibility: response_format on /v1/chat/completions', url: 'https://github.com/ollama/ollama/blob/main/docs/api/openai-compatibility.mdx' },
    { title: 'Ollama structured outputs (native format field)', url: 'https://github.com/ollama/ollama/blob/main/docs/capabilities/structured-outputs.mdx' },
    { title: 'llama.cpp server README: JSON schema to grammar', url: 'https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md' },
    { title: 'vLLM structured outputs', url: 'https://docs.vllm.ai/en/stable/features/structured_outputs/' },
    { title: 'JSON Schema 2020-12 validation vocabulary', url: 'https://json-schema.org/draft/2020-12/json-schema-validation' },
  ],
  commands: ['python3 -B demo.py', 'python3 -B demo.py --schema', 'python3 -B demo.py --schema "Two boxes of fuses for relay 4, no rush. Teo"', 'python3 -c "import json, extract; print(extract.validate(json.load(open(\'requests.json\'))[0][\'expected\'] | {\'unit\': \'piece\', \'urgency\': \'high\', \'requester\': \'Mara\'}, json.load(open(\'catalog.json\'))))"'],
  lesson: 'The starter asks for JSON and keeps whatever parses: it never checks the catalog, treats a cut answer as complete, retries five times whatever the bound says, repairs without telling the model what was wrong, never sends response_format and, when it gives up, returns ok=true with the last object it saw. LEARN.md gives the complete contract. Verify drives your extract() through a scripted adapter that answers malformed, truncated, extra-field and unknown-item outputs in a chosen order and records every request body, then measures prompt-only against schema-enforced validity on the endpoint in llm.json with max_repairs=0. Configure llm.json with your local model first and warm it up with the demo; a cold load can exceed the 15-second limit and is reported as environment blocked, not as a failure. The live numbers are measurements, never a verdict. Out of scope: timeouts, backoff and rate limits (the next mission), streaming, and prompt versioning.',
  artifact: 'Schema, validator and bounded repair',
}

export const followUps: string[] = [
  'The operator wants to drop the catalog check because the schema-enforced run was 3/3 valid. Explain what that number does and does not show.',
  'A new requester writes the item name in another language. Say where in your pipeline that fails, with which prefix, and what you would change.',
]
