# Field manual — same question, different answers

The operator assistant now classifies supply requests, and the relay crew wants to know whether it says "urgent" because the request is urgent or because the dice fell that way. The starter asks each setting once, writes that answer down and calls it a distribution; where a seed is present it declares the setting reproducible without ever trying again. Those are the deliberate defects.

## Workshop and entry point

Python 3.10 or later, standard library only. Edit `experiment.py` and keep two names importable: `run_experiment` and `report`. Verify imports your module, runs experiments against its own scripted adapter, reads the raw file you write and compares your report with its own recomputation. `settings.json` and `prompt.txt` are fixtures for your terminal runs; Verify carries its own settings, sample counts, seeds and labels, so read everything from the arguments.

`python3 -B demo.py 5` runs five samples per setting from `settings.json` through `llm.json` and prints the report; `python3 -B demo.py 5 4` does the same with four requests in flight. The raw outputs land in `raw.jsonl`. The endpoint and model id live in `llm.json`; a key, if your endpoint needs one, lives in `LLM_API_KEY` in the environment, never in a file of this workspace. A local server such as Ollama or llama.cpp needs none.

## What a sampling setting is

Every request in this chapter is `POST {base_url}/chat/completions`. Three body fields steer how the next token is chosen: `temperature` (0 means take the most likely token every time; larger values flatten the distribution), `top_p` (sample only from the smallest set of tokens whose probability mass reaches p) and `seed` (ask the server to start its random generator from a fixed value). Some servers also return `system_fingerprint`, a label for the backend configuration that produced the answer.

What a seed does and does not guarantee is the point of this mission. OpenAI documents `seed` and `system_fingerprint` as deprecated and best-effort: the same seed usually gives the same output when the fingerprint is unchanged, and nothing is promised otherwise. vLLM documents reproducibility only for the same batch composition, hardware and version; llama.cpp notes that the batch size changes the logits. A server may also ignore `seed` entirely and still answer HTTP 200. So a reproducibility claim is an observation you make by running the setting again, never a property you derive from the parameters.

## Complete public contract

```python
run_experiment(settings, *, base_url, model, prompt, samples, max_tokens, out_path, concurrency=1) -> dict
report(raw_path) -> dict
```

`settings` is a list of dicts: `name` (unique string), `temperature` (number), optional `top_p` (number) and optional `seed` (integer). `samples` is an integer from 2 to 50. `prompt` is sent unchanged as the single user message.

1. **Send the declared count.** For every setting send exactly `samples` requests, each with the body `{model, messages: [{role: "user", content: prompt}], max_tokens, temperature}` plus `top_p` and `seed` when the setting has them (omit the key or send `null` otherwise). Do not send `stream: true`. Record each answer with `run: "first"` and `index` from 0 to `samples − 1`.
2. **Rerun every seeded setting.** After its first run, send `samples` more identical requests for every setting that has a seed and record them with `run: "rerun"` and `index` 0 to `samples − 1`. A setting without a seed is not rerun.
3. **Write every output verbatim.** `out_path` is created or truncated at the start of a run. Each record is one JSON line with the keys `setting`, `run`, `index`, `model`, `seed`, `temperature`, `top_p`, `content`, `finish_reason`, `usage`, `system_fingerprint`. `content` is `choices[0].message.content` exactly as returned, `finish_reason` the first choice's value, `usage` the response's usage object, `system_fingerprint` the response value or `null` when the server sends none; `seed` and `top_p` are `null` when the setting has none. Records may be written in any order; extra keys are allowed.
4. **Report from the raw file only.** `report(raw_path)` returns a dict keyed by setting name. The answer of a record is `content.strip()`; nothing else is normalized. The distribution uses the first-run records only. Each entry has `samples` (first-run record count N), `seed`, `temperature`, `distinct` (number of different answers), `majority` (the most frequent answer; a tie goes to the lexicographically smallest), `majority_share` (its count divided by N), `agreement` (the probability that two different samples agree: Σ c·(c − 1) / (N·(N − 1)) over the answer counts c; 1 when N = 1), `entropy_bits` (−Σ p·log₂ p over the answer shares), `reproducible` and `finish_reasons` (a mapping from finish reason to its count over the first run). Tolerance for the numbers is 1e-9. `run_experiment` returns exactly `report(out_path)`. A setting counts as seeded when its records carry a non-null `seed`. A null finish reason is counted under the key `"null"`.
5. **Claim reproducibility only from the rerun.** `reproducible` is `true` when the rerun's answers equal the first run's answers index by index, `false` when any position differs, `null` when the setting has no seed. Agreement inside the first run proves nothing about a rerun: a server that answered the same thing five times and something else on the sixth is not reproducible.
6. **Refuse a partial file.** `report` raises `ValueError` when a setting's records for a run do not carry exactly the indices 0 to n − 1 (a gap or a duplicate), when a seeded setting's rerun count differs from its first-run count, or when the file holds no records. A truncated experiment is not a distribution.

`concurrency` is optional: a value above 1 may send that many requests at once. Whatever the order of completion, the file must still hold every record once and the report must still follow the file. Transport errors may raise any exception; retries are a later mission.

## Worked example

Five samples of one setting answered `urgent`, `urgent`, `routine`, `urgent`, `reject`. Counts are 3, 1, 1, so `distinct` is 3, `majority` is `urgent`, `majority_share` is 0.6, `agreement` is (3·2 + 0 + 0) / (5·4) = 0.3 and `entropy_bits` is −(0.6·log₂0.6 + 2·0.2·log₂0.2) ≈ 1.371. Had the counts been 2, 2, 1 with answers `routine` and `urgent` tied, `majority` would be `routine`. If that setting had seed 42 and its rerun answered `urgent` five times, `reproducible` is `false`: three of five positions differ from the first run.

## What Verify runs

- A **scripted adapter**: a loopback server that speaks the contract above, serves labels Verify chose and records every request. It runs in three modes: one honors the seed, one ignores it (the rerun differs), one honors it until a chosen number of requests and then answers differently with a changed `system_fingerprint`, as a redeployed server would. At temperature 0 it is greedy. It is a labeled test tool, never a model. Verify also hand-builds raw files with a tie, a shuffled order, padded whitespace and broken indices, and edits one record of your own file to see the report change.
- One **live experiment** through your `run_experiment` against the endpoint in `llm.json`: two settings (temperature 0 with a fresh seed, temperature 1.0 without), three samples each, `max_tokens` 4, nine requests in total. Verify recomputes your report from the raw file and reports the agreement, the rerun result and the entropy as measurements of that endpoint, not as a pass or fail on the model. No model id in `llm.json`, no answer within 15 seconds, an HTTP error from the probe (wrong model id, 401) or nine requests that take longer than 20 seconds is **Environment blocked**: nothing is recorded as a failure, nothing as a pass. An error raised by your `run_experiment` during the nine requests is a failed check. Warm the model up with the demo first.

Two different implementations pass: `urllib.request` with a thread pool and `collections.Counter`, and `http.client` with a queue of worker threads and `fractions.Fraction`. No structure of `experiment.py` is required beyond the two importable names.

## Sources

- OpenAI chat completions reference: `temperature`, `top_p`, `seed` (deprecated, best-effort) and `system_fingerprint` (deprecated).
- vLLM, "Reproducibility": determinism holds only for the same batch composition, hardware and software version.
- llama.cpp `llama-server` README: `seed` defaults to −1, batching affects the logits.
- Ollama OpenAI compatibility: `seed`, `temperature` and `top_p` are passed through; `system_fingerprint` is the constant `fp_ollama`.
- Python `concurrent.futures` and `threading` for the optional concurrency.
