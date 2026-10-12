# Field manual — every word has a price

The outpost is getting an operator assistant. Before it answers a single supply request, you must be able to say what one call costs, how long it took, whether the answer was cut short and whether the request could fit at all. The starter reaches a model and prints its answer; everything else in its record is invented. That is the deliberate defect.

## Workshop and entry point

Python 3.10 or later, standard library only. Edit `client.py` and keep two names importable: the class `WindowError` and the function `ask`. Verify imports your module, calls `ask` with explicit keyword arguments and reads the record it returns and the line it appends to the log. `models.json` is a sample price table for your own terminal runs; Verify passes its own manifest with fresh values, so read every number from the `manifest` argument, never from a constant.

`python3 -B demo.py "Reply with the single word OK."` makes one real call through your client using `llm.json`. That file holds only the endpoint and the model id. An API key, if your endpoint needs one, lives in the environment variable `LLM_API_KEY`, never in a file of this workspace, never in the log. A local server such as Ollama or llama.cpp needs no key.

## The API you talk to

Every server in this chapter speaks the OpenAI-compatible chat completions contract. A request is `POST {base_url}/chat/completions` with a JSON body:

```json
{"model": "relay-small", "messages": [{"role": "user", "content": "…"}], "max_tokens": 64, "temperature": 0.0}
```

The response is a JSON object. Three parts matter here:

| Field | Meaning |
| --- | --- |
| `choices[0].message.content` | the answer text |
| `choices[0].finish_reason` | `stop` when the model finished, `length` when `max_tokens` cut it short, `tool_calls` or `content_filter` on other servers |
| `usage.prompt_tokens`, `usage.completion_tokens`, `usage.total_tokens` | what the server actually counted; `usage.prompt_tokens_details.cached_tokens` is present on some servers |

Do not send `"stream": true` in this mission: the usage object arrives in the final chunk of a stream and is absent when a stream is cut, which is a later mission's problem.

## Complete public contract

```python
ask(prompt, *, base_url, model, max_tokens, manifest, log_path, temperature=0.0) -> dict
```

`manifest` has the shape of `models.json`: `overhead_tokens` (integer) and `models`, a mapping from model id to `context_window`, `input_price_per_million`, `output_price_per_million` and optionally `cached_input_price_per_million`. Prices are in currency units per one million tokens.

1. **Fit before you send.** A token never covers less than one byte of UTF-8 text, so `len(prompt.encode("utf-8")) + overhead_tokens` is a safe upper bound for the prompt. If that bound plus `max_tokens` exceeds the model's `context_window`, raise `WindowError` and make **no** request and **no** log line. A prompt exactly at the bound is sent.
2. **Send what you log.** The request body carries `model`, `max_tokens`, `temperature` and the prompt as the user message. The record carries the same `model`, `max_tokens` and `temperature` that were sent.
3. **Take the meter from the response.** `input_tokens` is `usage.prompt_tokens`, `output_tokens` is `usage.completion_tokens`, `finish_reason` is the first choice's `finish_reason`, verbatim. `cached_tokens` is `usage.prompt_tokens_details.cached_tokens` when present, otherwise `0`. Never estimate tokens from characters: tokenizers differ between models, and Verify's adapters count differently on purpose.
4. **Price from the table.** `cost = input_tokens × input_price + output_tokens × output_price`, each price divided by 1,000,000. Tolerance is 1e-9. The second model in the manifest has different prices and a different window; the cost must follow the model that was called.
5. **Measure latency around the request.** `latency_ms` is a non-negative integer measured from just before the request is sent to just after the response body is read, in milliseconds. It cannot be smaller than the time the server took, and it cannot be larger than the time your caller waited.
6. **Append one JSON line per call.** Open `log_path` in append mode and write `json.dumps(record)` followed by a newline. Earlier lines stay byte-for-byte unchanged. A refused call writes nothing.

The record is a dict with exactly these keys, in any order: `model`, `max_tokens`, `temperature`, `input_tokens`, `output_tokens`, `cached_tokens`, `latency_ms`, `finish_reason`, `cost`, `content`. Token counts and `latency_ms` are integers, `cost` is a number, `content` is the answer text. Extra keys are allowed.

Transport errors (connection refused, timeout, HTTP 4xx/5xx) may raise any exception; retries and backoff are the next mission.

## What Verify runs

- A **recording adapter**: a loopback server that speaks the contract above, records every request body and answers with deterministic token counts, a chosen `finish_reason`, an optional delay and, for the hidden bonus, cached prompt tokens. It is a labeled test tool, not a model. Its counts are chosen so that a character-based estimate is always wrong.
- One **live call** through your client to the endpoint in `llm.json`, followed by Verify's own direct request with the same parameters. The prompt token counts must agree and the output must stay within `max_tokens`. If `llm.json` has no model id or the endpoint does not answer within 15 seconds, the result is **Environment blocked**: nothing is recorded as a failure, and nothing is recorded as a pass. Warm a local model up with the demo first; a cold load of a large model can take longer than the check allows.

Two different implementations pass: `urllib.request` with floats and `http.client` with `decimal.Decimal` both satisfy the contract. No specific structure of `client.py` is required beyond the two importable names.

## Sources

- OpenAI chat completions reference: request body, `finish_reason` values, the `usage` object and its `prompt_tokens_details`.
- Ollama OpenAI compatibility (`/v1/chat/completions`) and llama.cpp `llama-server` README: both return the same `usage` shape; llama.cpp refuses a prompt over the context size, Ollama drops old messages silently instead. Your guard runs before either server sees the request.
