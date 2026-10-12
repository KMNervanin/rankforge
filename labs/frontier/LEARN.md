# Field manual — choose a model with evidence

The outpost can afford one model for the triage assistant and five are on offer. The starter runs the first candidate on the whole set and the others on half of it, trusts the summary each run wrote about itself, and crowns whichever has the highest accuracy with a sentence that cites no number. That is the deliberate defect: a choice, not evidence.

## Workshop and entry point

Python 3.10 or later, standard library only. Edit `frontier.py` and keep three names importable: `run_candidates`, `frontier` and `decide`. Verify imports your module, injects its own case runner for the deterministic checks, points your own HTTP runner at a loopback adapter, and feeds `frontier` and `decide` manifests and rows it built by hand. `cases.json`, `settings.json`, `candidates.json`, `budget.json` and `replay.json` are fixtures for your own terminal runs; Verify carries its own values, so read everything from the arguments.

`python3 -B demo.py` replays five sample candidates from `replay.json`, prints the frontier table and the decision for `budget.json`; `python3 -B demo.py 800` tightens the p95 budget. `python3 -B demo.py --live` runs the model from `llm.json` on the first three cases and writes `runs/live.json`. An API key, if your endpoint needs one, lives in `LLM_API_KEY`, never in a file of this workspace.

## The idea

Hamel Husain's evals FAQ puts it first: do error analysis before switching models, and when you compare models, compare them on the same questions. Evan Miller's "Adding Error Bars to Evals" adds the statistics: a score without an interval is a point, and two models should be compared with paired per-case differences on the same set. A model choice is therefore three artifacts: one **run manifest** per candidate that records exactly what ran (set, settings, per-case numbers), a **frontier** recomputed from those raw numbers (not from what the run claimed about itself), and a **decision record** that cites the measured numbers and the tolerance it applied.

A worked example. Five candidates, twenty cases each. `relay-xl` scores 19/20 at p95 1900 ms and 0.90 per 100 cases; `relay-mid` scores 18/20 at 900 ms and 0.30; `relay-large` also scores 18/20 but at 1400 ms and 0.50. `relay-large` is dominated by `relay-mid` (same quality, slower, dearer) and leaves the frontier. With tolerance 0.10 and a 2000 ms budget the record picks `relay-mid`: 0.900 is within 0.100 of the best 0.950, 900 ms fits, and it is the cheapest of the eligible. Tighten the budget to 800 ms and `relay-mid` is out; the record moves to the faster candidate within tolerance, or says that nothing fits.

Bonus: a row may carry `paired_vs_best = {best, mean_diff, se, low, high}` — `d_i = correct_i − best.correct_i` per case, `se = sqrt(Σ(d_i − mean)² / (n(n−1)))`, bounds `mean ± 1.96·se`. That is Miller's paired comparison: the difference column has its own interval.

## Complete public contract

```python
run_candidates(candidates, cases, *, base_url, settings, out_dir, run_case=None) -> list[dict]
frontier(manifests) -> list[dict]
decide(rows, budget) -> dict
```

Inputs:

| Argument | Shape |
| --- | --- |
| `candidates` | list of `{"id", "model", "input_price_per_million", "output_price_per_million"}`; `id` matches `[A-Za-z0-9._-]+` and names the manifest file, `model` is sent to the server. |
| `cases` | `{"version": str, "cases": [{"id", "request", "expected"}, …]}`, at least two cases, ids unique. |
| `settings` | `{"prompt_version", "system", "template", "temperature", "max_tokens"}`; `template` contains the literal `{request}`. |
| `run_case` | optional callable `run_case(model, case, settings) -> {"correct": 0|1, "latency_ms": int, "input_tokens": int, "output_tokens": int, "peak_memory_mb": int or absent}`. |
| `budget` | `{"tolerance": float, "p95_ms": int, "memory_mb": int (optional)}`. |

1. **Same set, same settings, every case once.** For every candidate and for every case in set order, call `run_case(candidate["model"], case, settings)` exactly once, with the case dict and the settings dict as given, unchanged. No subset, no per-candidate tweak. When `run_case` is `None`, use your own HTTP runner (rule 2).
2. **Your own runner builds one identical request per case.** `POST {base_url}/chat/completions` with `{"model": model, "messages": [{"role": "system", "content": settings["system"]}, {"role": "user", "content": settings["template"] with {request} replaced by case["request"]}], "max_tokens": settings["max_tokens"], "temperature": settings["temperature"]}`, no `stream`. Apart from `model` the body for a case is byte-for-byte the same for every candidate. From the response: `correct` is `1` when `content.strip().rstrip(".").strip().lower()` equals `expected.strip().lower()`, else `0` (an answer of `not urgent` for `urgent` is wrong); `input_tokens` and `output_tokens` are `usage.prompt_tokens` and `usage.completion_tokens`, never estimated; `latency_ms` is an integer measured around the request; `peak_memory_mb` is `usage.peak_memory_mb` when the server reports an integer there (a JSON integer; booleans and floats count as absent), otherwise `null`. Transport errors may raise any exception.
3. **One manifest per candidate**, written to `out_dir/<id>.json` (`out_dir` is created) and returned as a list in candidate order, each equal to its file. Keys: `candidate`, `model`, `set_version`, `set_hash`, `settings_hash`, `settings` (a copy), `prices` (`input_price_per_million`, `output_price_per_million` copied from the candidate), `results`: one `{"case", "correct", "latency_ms", "input_tokens", "output_tokens", "cost", "peak_memory_mb"}` per case in set order. `cost = (input_tokens × input price + output_tokens × output price) / 1,000,000`, tolerance 1e-9. Extra keys are allowed but never trusted (rule 5).
4. **Hashes are SHA-256 hex of canonical JSON**: `json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`. `set_hash` hashes `{"version": cases["version"], "cases": [{"id", "request", "expected"} …]}` with the cases sorted by `id`; `settings_hash` hashes the settings dict.
5. **`frontier` validates, then recomputes from raw results.** It raises `ValueError` when a manifest's `set_hash` or `settings_hash` differs from the first manifest's, or when its `results` do not cover the same case ids as the first manifest's results, each once; a subset, a superset or a repeated case is `results`. The message names the candidate and the field (`set_hash`, `settings_hash` or `results`). Every aggregate comes from `results`; a `summary` or any other key in the manifest is ignored. Rows are returned sorted by `candidate`, each with: `candidate`, `model`, `n`, `correct`, `accuracy = correct / n`, `accuracy_low` and `accuracy_high` (Wilson score interval, z = 1.96, clamped to [0, 1], tolerance 1e-6), `p50_ms` and `p95_ms` (nearest-rank percentiles: the k-th smallest latency with `k = ceil(q × n)`, integers), `cost_per_100 = Σ cost × 100 / n` (tolerance 1e-7), `peak_memory_mb` (the maximum reported value, `null` when none), `pareto` (boolean).
6. **Pareto over (accuracy ↑, p95_ms ↓, cost_per_100 ↓).** A row is dominated when another row is at least as good on all three and strictly better on at least one; `pareto` is `true` for the undominated rows.
7. **`decide` picks the cheapest candidate within tolerance that fits the budget.** `best` is the row with the highest accuracy (ties: lower `cost_per_100`, then `candidate`). A row is rejected with the first matching reason: `quality` when `accuracy + tolerance + 1e-9 < best.accuracy`, `latency` when `p95_ms > budget["p95_ms"]`, `memory` when the budget has `memory_mb` and the row's `peak_memory_mb` is not `null` and exceeds it. Among the rest, `chosen` is the lowest `cost_per_100` (ties: lower `p95_ms`, then `candidate`); the other eligible rows are rejected with reason `cost`. With nothing eligible `chosen` is `null`.
8. **The decision record cites numbers.** It is `{"chosen", "best", "tolerance", "budget", "rejected", "summary"}`. `rejected` lists every candidate but the chosen one as `{"candidate", "reason", "detail"}`, sorted by candidate, and `detail` cites the measured value behind the reason: `f"{accuracy:.3f}"` for `quality`, `f"{p95_ms} ms"` for `latency`, `f"{peak_memory_mb} MB"` for `memory`, `f"{cost_per_100:.4f}"` for `cost`. `summary` is one paragraph naming the chosen and the best candidate and citing the chosen accuracy and the best accuracy as `.3f`, the tolerance as `.3f`, the chosen `p95_ms` and the budget as `"<int> ms"`, and the chosen `cost_per_100` as `.4f`. With `chosen` null, `rejected` lists every candidate; `summary` still names `best` and contains the words `no candidate`.

## What Verify runs

- A **scripted runner** (a Python callable, a labeled test tool) that returns chosen numbers per model and case and records every call: three candidates on ten cases must produce thirty calls with identical settings and manifests carrying the runner's numbers, price-table costs and the expected hashes.
- A **loopback adapter** that speaks the chat completions contract with scripted answers per model (including `urgent.`, `URGENT` and `not urgent`), per-model delays, deterministic usage and `usage.peak_memory_mb` for one model: your own runner must send identical bodies across candidates and take correctness, tokens, latency and memory from each response.
- **Hand-built manifests** for five candidates on twenty cases with fresh latencies, prices and wrong answers each run: a tweaked-settings manifest, a subset manifest and a partial manifest must each be refused by name; forged `summary` blocks must be ignored; the Pareto set is known in advance; the decision must pick the cheaper candidate within tolerance, name every rejection with its number, reject on a memory budget, and move to a faster candidate when the p95 budget tightens.
- One **live run** of three cases on the model in `llm.json` through your own runner, reported as a measurement (correct count with its Wilson interval, p50/p95, tokens, cost), never as a verdict on the model. No model id, or an endpoint that does not answer Verify's own probe within 15 seconds, is **Environment blocked**: nothing fails, nothing passes. A transport error inside your runner after the probe succeeded is a failed check, not Environment blocked, and the usage integers must be greater than zero. Warm a local model up with `demo.py --live` first.

Two different implementations pass: `urllib.request` with dict rows, floats and a pairwise dominance scan, and `http.client` with dataclass rows, `Fraction` arithmetic and a sorted sweep. No specific structure of `frontier.py` is required beyond the three importable names.

## Sources

- Hamel Husain & Shreya Shankar, AI Evals FAQ: do error analysis before switching models; keep the comparison on the same questions.
- Evan Miller, "Adding Error Bars to Evals" (arXiv 2411.00640): report intervals, compare models with paired per-case differences on the same set.
- Wikipedia, binomial proportion confidence interval: the Wilson score interval.
- Wikipedia, Pareto front: dominance over several objectives.
