# Field manual — an unreliable colleague

The relay that carries the operator assistant's calls drops answers mid-sentence, answers "slow down" with a wait time, times out, and some mornings it says the outpost's quota is spent. The starter retries all of it the same way, forever, and hands back whatever arrived as if it were the answer. That is the deliberate defect: a model is a dependency that fails in five different ways, and each way needs a different response.

## Workshop and entry point

Python 3.10 or later, standard library only. Edit `wrapper.py` and keep one name importable: the function `call`. Verify imports your module, calls `call` with explicit keyword arguments, reads the result it returns and the lines it appends to the ledger. `policy.json` and `request.json` are samples for your own terminal runs; Verify passes its own policy with fresh values, so read every number from the `policy` argument, never from a constant.

`python3 -B demo.py 429:2,timeout,503,ok` starts a flaky relay on loopback (a labeled test tool, never a model), makes one call through your wrapper with real sleeps and prints the result and the ledger. Name any fault order you like: `ok`, `length`, `cut` (streams only, add `--stream`), `429`, `429:<seconds>` for a Retry-After, `quota`, `400`, `500`, `503`, `timeout`. No model is needed for this mission and no key is read: a real endpoint would take `LLM_API_KEY` from the environment, never from a file.

## Five ways a model call fails

| What the relay does | What you see | What the right wrapper does |
| --- | --- | --- |
| HTTP 429, often with `Retry-After: 3` | `urllib.error.HTTPError` with `code` 429 and `headers` | retry; wait at least the header value, jittered backoff otherwise |
| HTTP 429 whose body says `"type": "insufficient_quota"` | same exception, a different body | stop: the outpost is out of quota or billing; a retry costs money or another refusal |
| HTTP 500 or 503 (sometimes with `Retry-After`) | `HTTPError` with `code` ≥ 500 | retry with backoff, header as a floor |
| no response within the timeout | `TimeoutError` (3.10 and later; `socket.timeout` is the same class) or a `URLError` whose `reason` is one | retry: the relay may or may not have processed the request |
| a stream closed before the final chunk | the line iterator simply ends; `read()` raises `http.client.IncompleteRead` | the text so far is a fragment: retry, and never return it as complete |
| `"finish_reason": "length"` | a normal 200 | the answer is truncated: return it marked incomplete, do not retry (the same request gives the same cut) |
| HTTP 400, 401, 403, 404 | `HTTPError` with a 4xx code | stop: the request itself is wrong |

OpenAI's rate-limit guide states the three rules behind this table: when `Retry-After` is present, wait at least that long before retrying; when it is missing, use exponential backoff with jitter and bound the number of retries; do not retry quota and billing errors. Unsuccessful requests still count against your limits, which is the reason the bound exists. For streams the guide adds a fourth rule: never replay a request after you have handed its output to someone. This wrapper buffers the stream and decides only at its end, so nothing has been handed out when it retries; the moment you print tokens as they arrive, a cut stream becomes a final answer marked incomplete.

## Complete public contract

```python
call(request, *, base_url, policy, ledger_path, clock=time.monotonic, sleep=time.sleep, effect=None, idempotency_key=None) -> dict
```

`request` is the chat completions body: `model`, `messages`, `max_tokens`, optional `temperature` and `stream`. `policy` has the shape of `policy.json`: `max_attempts` (integer ≥ 1), `base_delay`, `max_delay`, `jitter` (0 to 1), `total_budget`, `request_timeout` and `quota_pause`, all seconds. `clock` returns monotonic seconds and `sleep` waits; use them for every measurement and every wait, because Verify injects a fake clock whose time advances only through its own `sleep`. `effect` is the caller's commit step, the thing that must happen once per completed answer (the reservation). `idempotency_key` is the key for this logical call; when it is `None`, generate one.

1. **Send the request as given.** `POST {base_url}/chat/completions` with the request as the JSON body and the header `Idempotency-Key` set to the call's key, the same key on every attempt of one call and a different key for every call. When `stream` is true, add `"stream_options": {"include_usage": true}` so the usage chunk is sent. Each attempt waits at most `request_timeout` seconds for the response.
2. **Classify every attempt** into one of: `complete` (200 and a `finish_reason` other than `length`), `truncated` (`finish_reason` `length`), `rate_limited` (429), `quota` (429 whose `error.type` or `error.code` is `insufficient_quota` or starts with `billing`), `server_error` (5xx), `timeout`, `stream_cut` (a streamed response ended before any chunk carried a `finish_reason`), `rejected` (any other 4xx) and `transport` (any other connection failure). Retryable: `rate_limited`, `server_error`, `timeout`, `stream_cut`, `transport`. Everything else ends the call.
3. **Wait by the rule.** After retryable attempt *n* (counted from 1) the bare delay is `min(base_delay × 2^(n−1), max_delay)` and the wait is drawn uniformly from `[delay × (1 − jitter), delay × (1 + jitter)]`. When the failed response carried `Retry-After` (delta-seconds), the wait is `max(Retry-After, that draw)`: the header is a minimum, never the exact value. Verify checks every wait against these bounds with a tolerance of 1e-9 and checks that waits are not all equal to the bare delay.
4. **Stay bounded.** Never make more than `max_attempts` attempts: when `max_attempts` is reached the call ends with `stop: "attempts"` without computing a wait. For an attempt that would otherwise retry, compute the wait and, if `elapsed + wait > total_budget` (strictly), do not sleep: end the call with `stop: "budget"`. The budget applies only to an attempt that would otherwise retry. `elapsed` is `clock()` now minus `clock()` at the start of the call. A `Retry-After` the budget cannot afford is not waited for.
5. **Never pretend.** A `truncated` attempt returns immediately with `complete: false`, its partial `content` and `finish_reason` `"length"`. A `stream_cut` is retried; if the bound ends the call, the result is `complete: false`, `last: "stream_cut"`, `finish_reason: null`, `usage: null` (the usage chunk arrives last and was never received) and `content` holds the fragment for display, never as an answer.
6. **Pause on quota.** A `quota` attempt ends the call with `outcome: "paused"` after one request, with no sleep inside `call`; `pause` is the response's `Retry-After` when present, else the policy's `quota_pause`. The runtime, not the wrapper, holds the pending message for that long. A `rejected` attempt ends the call with `outcome: "rejected"` after one request and `error` carrying the server's message.
7. **One effect per answer.** Call `effect(result)` exactly once, after the result is assembled, only when `complete` is true. Never on a truncated or cut answer, never per attempt. The stable `Idempotency-Key` lets the relay make the server side of the same promise: one reservation per key however many times the request arrives.
8. **Append one JSON line per attempt** to `ledger_path`, opened in append mode, with at least the keys `key`, `attempt` (1-based integer), `outcome` (the class from rule 2), `status` (HTTP status integer or `null` when no response arrived), `retry_after` (the header value as a number, `null` when absent), `wait` (the seconds slept after this attempt, `0` on the last line) and `elapsed` (seconds since the call started, by `clock`, sampled once per attempt before the wait; the last line's value is the result's `elapsed`). Earlier lines stay byte-for-byte unchanged.

The result is a dict with exactly these keys, in any order; extra keys are allowed:

| Key | Value |
| --- | --- |
| `outcome` | `complete`, `truncated`, `exhausted` (retryable failures until the bound), `paused`, `rejected` |
| `complete` | `true` only when `outcome` is `complete` |
| `content` | the answer text, a fragment, or `null` |
| `finish_reason`, `usage` | from the last response, verbatim; `null` when none arrived |
| `attempts` | number of requests made, integer ≥ 1 |
| `elapsed` | seconds from the start of the call to the end of the last attempt, by `clock` |
| `last` | the class of the last attempt |
| `status` | the last HTTP status or `null` |
| `retry_after` | the most recent `Retry-After` seen during the call, or `null` |
| `pause` | seconds to pause when `outcome` is `paused`, else `null` |
| `stop` | why the call ended: `complete`, `truncated`, `attempts`, `budget`, `quota`, `rejected` |
| `key` | the idempotency key that was sent |
| `error` | the error message of the last attempt, `null` when the last attempt returned a response with choices |

Worked example with `max_attempts` 4, `base_delay` 0.5, `max_delay` 8, `jitter` 0.25, `total_budget` 30: attempt 1 gets 429 with `Retry-After: 2`; the draw is in [0.375, 0.625], so the wait is 2. Attempt 2 times out; the draw is in [0.75, 1.25], say 1.1. Attempt 3 returns 503; the draw is in [1.5, 2.5], say 1.9; `elapsed + 1.9` is below 30, so it sleeps. Attempt 4 answers with `finish_reason` `stop`: `outcome` `complete`, `attempts` 4, four ledger lines with waits 2, 1.1, 1.9, 0, the effect runs once. With `max_attempts` 3 the same relay ends at attempt 3 with `outcome` `exhausted`, `stop` `attempts`, no fourth request and no effect.

## What Verify runs

A **fault adapter**: a loopback server that speaks the contract and answers each request with the next scripted fault: 429 with and without `Retry-After`, timeouts (the adapter holds the response past `request_timeout`), 500 and 503, a chunked stream closed mid-answer with no usage chunk, a `length` stop, a quota error, a 400, and an endless run of 503 to prove the bound. It records every request, its `Idempotency-Key` and one reservation per key. Time is injected: Verify's `sleep` records each wait and advances the clock, so a run that respects the contract takes about a second of real time and a wrapper that waits with `time.sleep` is caught by a 6-second watchdog per call. A transfer run shuffles the fault order and expects the same wrapper to pass. The hidden bonus concerns a 429 that carries an `x-ratelimit-reset-requests` duration (`3s`, `20ms`, `6m0s`) but no `Retry-After`: treat the parsed duration exactly like `Retry-After`, a floor on the wait.

Two different implementations pass: `urllib.request` with a dataclass policy and a line-by-line stream reader, and `http.client` with a delay generator and a buffered SSE parser. No specific structure of `wrapper.py` is required beyond the importable `call`.

## Sources

- OpenAI rate limits guide and error codes: `Retry-After` on 429 and 503 as a minimum, exponential backoff with jitter when it is absent, no retry on quota and billing errors (`insufficient_quota`), unsuccessful requests count against limits, no replay of a stream after consuming output; `x-ratelimit-reset-*` headers.
- OpenAI chat completions streaming: `stream_options.include_usage` sends usage in the last chunk before `data: [DONE]`; a cut stream has none.
- Python `urllib.request` and `http.client`: `HTTPError.headers`, `TimeoutError` on read timeouts, `IncompleteRead` on a chunked body that ends early.
