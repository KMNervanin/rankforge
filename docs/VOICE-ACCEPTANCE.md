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

## Batch 2 — G07–G11 "Measuring the voice", 2026-10-12 evening

Same procedure as batch 1: five author agents, five blind solvers, findings applied before integration. All five blind solutions passed within two iterations.

| Mission | Runtime id | Checks (required + bonus) | Live part | Node tests | Review findings applied |
| --- | --- | --- | --- | --- | --- |
| G07 Read the traces first | `traces` | 10 + 1 | no (the learner reads 120 shipped traces; the reviewer read all of them and judged the size realistic) | 16/16 | agreement tolerance 8 → 12 with the unit and relay rules stated; no foreign ids; bonus prefix documented; a rare empty-category flake removed |
| G08 A golden set you can trust | `golden` | 7 + 1 | no | 14/14 | held-out digest wording contradiction; duplicate prefix documented and a real twin added to the fixture; objective 5 reworded; starter signature |
| G09 Numbers with error bars | `errorbars` | 8 + 1 | no | 16/16 | clustered-SE formula confirmed by derivation and its degenerate cases stated; needed_n integral; unverifiable "969" claim dropped |
| G10 A judge needs a judge | `judge` | 10 + 1 | yes: four labeled fixtures on the configured endpoint, agreement/TPR/TNR reported (one run on gemma-3-4b: 4/4) | 17/17 | criterion prompt must be its own message; Fraction rates accepted; pairwise pins; bonus signature; A/B/TIE parse-failure path exercised |
| G11 Evals as a gate | `evalgate` | 8 + 1 | no (injected runner and clock) | 18/18 | `cases_run` is a count; first-attempt pass decided outright; cap semantics for the interrupting case enforced both ways; starter fails for the stated reasons |

Limits as in batch 1. G07's pass-versus-failure agreement is checked against the planted outcomes with a published tolerance; the grouping itself is debrief material, not a code verdict.

## Batch 3 — G12–G16, end of "Measuring the voice" and start of "The archive", 2026-10-12 evening

Same procedure. All five blind solutions passed on the first verifier run; every review returned "ship after fixes" and the fixes were applied and re-tested.

| Mission | Runtime id | Checks (required + bonus) | Live part | Node tests | Review findings applied |
| --- | --- | --- | --- | --- | --- |
| G12 Choose a model with evidence | `frontier` | 8 + 1 | yes: three cases through the learner's runner on the configured model, Wilson/p95/cost reported (one run on gemma-3-4b: 2/3, p95 82 ms) | 18/18 | Pareto expectations were constant by candidate name (now randomized ids and two dominance designs); workspace litter removed; live Wilson computed by the verifier; wording of rules 2, 5, 7, 8 and the bonus |
| G13 Take the scaffolding away | `ablation` | 7 + 1 | no (scripted runner with a planted truth) | 16/16 | reserved "kept for" label documented; Bonferroni bonus spec; reference tokens/latency and record n/z now checked; refusal list fully exercised |
| G14 Meaning as numbers | `embeddings` | 7 + 1 (+ live) | only when `embedding_model` is set in llm.json (none installed locally: Environment blocked by design) | 18/18 | identity-before-dimension precedence; empty-store re_embed (the starter demo crashed on a fresh file); vector scan by decoding, not BLOB length; workspace cleanup; batches persisted after reopen |
| G15 Documents are not plain text | `extraction` | 8 + 1 | no (layout JSON stands in for PDF parser output, stated in the manual) | 17/17 | indentation and whitespace rules; unknown layout block types ignored; unclosed-element lists aligned; reason matched with the path removed |
| G16 Where to cut | `chunking` | 7 + 1 | no (injected embed function) | 15/15 | warning-field vs following-paragraph precedence stated and exercised; float metrics; decimal recall in the reason; semantic headings rule; `extraction` prerequisite added |

## Batch 4 — G17–G21, the rest of "The archive", integrated 2026-10-12 19:40 after the stop

Integrated as authored, because the run was stopped before every review cycle finished: `lexical` (G17, 15/15) and `fusion` (G18, 17/17) are blind-reviewed with fixes applied; `reindex` (G21, 14/14) was authored and its blind review interrupted; `annindex` (G19, tests green) was authored without a review; `citations` (G20, 17/17) was reviewed but the author was stopped while applying the findings, so these remain open: typographic quotes and an inline `Sources:` line from small models must be accepted, the no-citation retry message, a non-empty `reason` on every abstention, the bonus offsets documented, the verifier's generic shape check running before the status-specific assertions (the starter fails for the wrong reason), and `reason`/`conflicts` in the required keys. The lexical review also left two items open: the verifier claims a lexical tie that the corpus does not contain, and the tie rule itself is untested. These are the first things to fix in the main context before authoring G22.
