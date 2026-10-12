# Chapter IX acceptance — the voice of the outpost

Evidence for the shipped chapter IX labs. Each entry records what was actually run on the day it was authored; a later `Verify` on a newer contract supersedes it.

## G01 — Every word has a price (`price`), 2026-10-12

**Contract.** `labs/price/LEARN.md` publishes the full contract: `ask(prompt, *, base_url, model, max_tokens, manifest, log_path, temperature=0.0)`, the byte-bound window guard, the request body, the record keys, the price formula with 1e-9 tolerance, latency bounds and the append-only journal. The mission objectives in `shared/voice.ts` repeat it.

**Starter defect.** `labs/price/client.py` reaches the model and prints its answer; the cost comes from `len(prompt)/4` and a constant price, `finish_reason` is the constant `stop`, latency is 0, no window guard, the log is overwritten, temperature is not sent.

**Verifier.** `server/verify_price.py` runs six required checks and one hidden bonus through a recording adapter (a loopback chat-completions server with deterministic counts: words + 4 per message + 3, or ⌈bytes/3⌉ + 5, so a character estimate is always wrong; an injectable 150 ms delay; cached prompt tokens for the bonus), then one live call to the endpoint in the workspace's `llm.json` reconciled with its own direct request. No model id, an unreadable config or no answer within 15 s yields a check named `Environment blocked`, which the runner reports as unsupported: no failure, no pass.

**Runs on 2026-10-12 (macOS, Python 3.14.5, Node 24).**

| Candidate | Result |
| --- | --- |
| Starter | RED on all six required checks and the bonus; the live check failed on cost (a configured endpoint is not an environment problem) |
| `tests/solutions/price/urllib.py` (urllib, floats) | GREEN 8/8 including the bonus; live call to Ollama `gemma-3-4b` (Q4_K_M): 16 prompt / 3 completion tokens, finish `stop`, 58 ms, prompt tokens equal to the direct request |
| `tests/solutions/price/httpclient.py` (http.client, Decimal, dataclass) | GREEN 8/8; live call 16 / 3 tokens, 51 ms |
| Nine mutations of the urllib solution | each RED on the named check: cost from characters, constant finish reason, guard disabled, character instead of byte bound, latency not around the request, temperature dropped, log overwritten, total tokens as input tokens, prices from a constant |
| Cached tokens ignored | GREEN on the contract, bonus RED, exit 0 |
| Empty model id / unreachable endpoint | `Environment blocked` with the config or the address in the detail; adapter checks still pass |
| Import failure | one failed `Load metered client` check |

The Node tests (`tests/price.test.ts`) repeat every row above against a test-only stub endpoint whose model id is `test-only`; the stub never stands in for a live evaluation outside the test process. `tests/campaign.test.ts` runs the same lab through the HTTP API: start, RED, solution copied, GREEN, repeated check awards nothing extra.

**Limits.** The live check reconciles prompt tokens and bounds the output; it does not judge the model's answer. The verifier's 45 s budget means a cold load of a large local model is reported as environment blocked; warm the model with `demo.py` first. Retries, streaming usage and rate limits are G04's scope. No learner has yet attempted the mission; clarity is authoring evidence only (gate 6 of the roadmap).

## Batch 1 — G02–G06 "Calling the model", 2026-10-12 evening

Five labs authored in parallel by author agents following `VOICE-AUTHORING.md`, each then attempted blind by a second agent from LEARN.md and the starter only (gate 6), with the review findings applied before integration. All five blind solutions passed within two iterations; every review returned "ship after fixes" and the fixes were applied and re-tested.

| Mission | Runtime id | Checks (required + bonus) | Live part | Node tests | Review findings applied |
| --- | --- | --- | --- | --- | --- |
| G02 Same question, different answers | `sampling` | 7 + 1 | yes: 3 samples × 2 settings on the configured endpoint, agreement/entropy reported as measurements | 20/20 | records matched by served position, not order; misleading detail; Bearer header on the probe; fourth broken-file case; two manual sentences |
| G03 Words into a record | `record` | 9 + 1 | yes: prompt-only vs schema-enforced validity on fixtures (one live run on gemma-3-4b: 0/3 vs 3/3) | 17/17 | `notes` type never checked (a validator skipping notes passed); live section bounded at 20 s; `maximum` exercised; catalog-in-prompt enforced; wording |
| G04 An unreliable colleague | `backoff` | 9 + 1 | no (fault adapter with injected clock) | 15/15 | ledger/result elapsed tolerance 50 ms; per-scenario real-time cap; strict budget rule and precedence wording |
| G05 The prompt is code | `prompts` | 6 + 1 | no | 16/16 | named "nothing was raised" details; workspace cleanup; separator and unknown-version semantics in the manual |
| G06 Fit the window | `window` | 7 + 1 | no | 16/16 | a dropped document must not end the fill (new check + mutation); worked-example arithmetic; passage normalisation stated |

Limits: the live measurements report numbers only; no learner has attempted these missions yet, so clarity rests on the blind-solver pass, not on a real learner. Chapter IX in the game shows these quests as cards grouped by sub-block; the Atlas links each to its roadmap node.
