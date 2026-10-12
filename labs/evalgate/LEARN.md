# Field manual — evals as a gate

The outpost's assistant now has a judge, a metric calculator and a case set with splits, and every prompt tweak and every model swap still ships on a feeling. The starter runs the whole set, held-out cases included, compares the result to a number typed into the code, reruns nothing, caps nothing and overwrites one `results.json`. That is the deliberate defect: a gate that can neither block a real regression with a name nor let honest noise through.

## Workshop and entry point

Python 3.10 or later, standard library only. Edit `gate.py` and keep two names importable: the class `ConfigError` and the function `run_gate`. Verify imports your module and calls `run_gate` with its own config, its own baseline, a **scripted runner** in place of the model and judge, and an injected clock. The runner is a labeled test tool: it answers from a script keyed by case id and attempt number, so the gate is tested on its logic and never on a model. There is no live call in this mission.

`cases.json`, `baseline.json`, `gate.json` and `replay.json` are fixtures for your own terminal runs. `python3 -B demo.py v3 relay-small` assembles a config from `gate.json` plus the manifest in `cases.json`, replays the outcomes recorded in `replay.json` for that model id and prints the decision. Try `python3 -B demo.py v3 relay-large` and `python3 -B demo.py v4 relay-small` and watch the archive grow. Verify carries its own case ids, thresholds, token counts and clock, so read every number from the arguments, never from a constant.

## The problem

Hamel Husain's evals FAQ draws the line this course follows: keep the CI set small and purpose-built, prefer deterministic checks over judges in CI, run the judge nightly or per release, and know what each test costs. A gate that is too strict blocks on noise and gets disabled; a gate that is too loose ships regressions. The gate you build here is a pipeline stage with three published numbers: how far a candidate may fall behind the baseline, a hard floor it may never go under, and a cap on tokens and seconds it may spend finding out. The repeat policy and the spend cap are this course's own contract, not published methodology.

Two hygiene rules carry over from the earlier missions. Thresholds are set on the **dev** split only: a subset that touches a held-out case is a configuration error, not a run. And every archived result pins its versions: the prompt, the model, the set and a hash of the config, so a number without its provenance never enters the archive.

## Complete public contract

```python
class ConfigError(Exception): ...
run_gate(config, *, candidate, baseline_results, run_case, clock) -> decision
```

**`config`** is a dict:

| key | content |
| --- | --- |
| `manifest` | `{"version": str, "cases": [case, …]}`; every case is a dict with a string `id`, a `split` (`dev` or `heldout`) and a `category`, plus whatever the runner needs (`request`, `expected`) |
| `subset` | the list of case ids to run, in run order |
| `thresholds` | `{"max_drop": points, "floor": percent}` — how many percentage points the candidate may fall below the baseline, and the accuracy it may never go under |
| `repeat` | `{"runs": k, "pass_min": m}` with `1 ≤ m ≤ k`: a case that fails is rerun until it has `k` attempts and passes only if at least `m` of them passed |
| `cap` | `{"tokens": int, "seconds": number}` — the spend the whole run may not exceed |
| `archive` | a directory for the results; created if missing |

**`candidate`** is `{"prompt_version": str, "model": str}`. **`baseline_results`** is `{"prompt_version": str, "model": str, "cases": {id: bool, …}}`, the per-case outcome of the release you compare against; it may list more ids than the subset. **`run_case(case)`** takes the case dict from the manifest, verbatim, and returns `{"passed": bool, "tokens": int, "seconds": number, "output": str}`. **`clock()`** returns a float of seconds; it is the only source of time in the gate, for the cap and for the archive stamp alike.

1. **Validate before you spend.** Raise `ConfigError` and make **no** `run_case` call and write **no** file when the subset is empty or has duplicates, when a subset id is not in the manifest or its `split` is not `dev`, when a subset id has no entry in `baseline_results["cases"]`, or when the repeat policy violates `1 ≤ pass_min ≤ runs`. Held-out cases are for the final report of a release, never for the gate that tunes thresholds.
2. **Run in order, decide early.** Take `started = clock()`. Run the subset ids in the given order. A case that passes its first attempt is decided with one call. A case that fails is rerun, immediately and before the next case, until the outcome is decided: it **passes** as soon as `pass_min` attempts have passed (a first-attempt pass is decided outright, even when `pass_min > 1`), it **fails** as soon as `runs - pass_min + 1` attempts have failed, and no further attempt is made once either is true. With `runs = 3, pass_min = 2`: F T T passes with three calls, F F fails with two, F T F fails with three.
3. **Stop at the cap.** After every `run_case` result add its `tokens` to the running total and read the clock. If the total is greater than `cap.tokens`, or `clock() - started` is greater than `cap.seconds`, stop immediately: no further `run_case` call for any case. The decision is `blocked` with reason `cap`, `cap.exceeded` names `tokens` or `seconds` (tokens is checked first), and `accuracy`, `baseline_accuracy` and `drop` are `null`; `failing` and `regressions` cover only the cases decided before the stop, and the call that exceeds the cap still decides its case when it is the deciding attempt. The partial results are still archived: a run that ran out of budget is a result worth keeping.
4. **Thresholds from config, on the subset.** With `n` the subset size, `accuracy = 100 · passed / n` and `baseline_accuracy = 100 · baseline passes over the same subset ids / n`, both in percent, and `drop = baseline_accuracy - accuracy` in points. The verdict is `blocked` with reason `floor` when `accuracy < floor − 1e-9`, else `blocked` with reason `regression` when `drop > max_drop`, else `pass` with reason `ok`. Comparisons tolerate 1e-9: a drop exactly at `max_drop` passes. `failing` lists, sorted, the ids whose outcome is a fail; `regressions` lists, sorted, the failing ids that the baseline passed. A blocked release always names its cases.
5. **Archive every run, append-only.** Compute `config_hash` as the SHA-256 hex digest of `json.dumps(config, sort_keys=True, separators=(",", ":"), ensure_ascii=False)` encoded as UTF-8. Write the decision to `<archive>/<stamp>-<prompt_version>-<model>.json` where `stamp = int(started * 1000)`, the injected clock at the start of the run in milliseconds. Open the file for exclusive creation (mode `x`): an existing file is never overwritten, the call raises instead and earlier files stay byte for byte unchanged. The file parses to a JSON object equal to the returned decision.
6. **Pin the versions.** `decision["versions"]` carries `prompt_version` and `model` from the candidate, `config_hash` from rule 5 and `set_version` = `manifest["version"]`. Changing only the model id yields a new archive entry whose name carries the new id, the same `config_hash`, the same `set_version` and the same `baseline_accuracy`.

The decision is a dict with exactly these keys (extra keys allowed): `verdict` (`pass` or `blocked`), `reason` (`ok`, `regression`, `floor`, `cap`, or `noise` from the bonus), `failing`, `regressions`, `accuracy`, `baseline_accuracy`, `drop`, `cases_total` (= `n`), `cases_run` (the number of ids that received at least one call), `calls` (every `run_case` invocation, reruns included), `tokens` (the sum of the results' tokens), `seconds` (`clock() - started` at the end of the run), `cap` (`{"tokens", "seconds", "exceeded"}` with `exceeded` `null` when the run finished), `versions`, `archive` (the path of the written file) and `results`: one entry per case that was run, in run order, `{"id", "passed", "attempts"}` where `attempts` holds the `run_case` results verbatim and `passed` is `null` for a case the cap interrupted before it was decided.

Worked example with `n = 20`, `max_drop = 5`, `floor = 70`, `runs = 1`: the baseline passed 19 cases (95.0), the candidate passes 18 (90.0), `drop = 5.0`, verdict `pass`, reason `ok`, `failing` names the two ids. A candidate passing 17 (85.0) has `drop = 10.0 > 5` and is `blocked` with reason `regression`, and `regressions` names the three ids the baseline passed; the one the baseline also failed is in `failing` only. With `runs = 3, pass_min = 2` a case scripted F T T costs three calls and counts as passed.

## Beyond the gate

The gate above blocks on a drop larger than `max_drop`, whatever the set size. The mission on error bars gives the stronger rule: per-case paired differences `d = candidate - baseline` (each −1, 0 or 1), their mean, the sample standard deviation with `n − 1`, the standard error `se = sd / √n` and the upper bound `mean + z · se`. When `thresholds` carries an optional `paired_z`, a drop beyond `max_drop` whose upper bound is still at or above 0 is noise, not a regression: the verdict is `pass` with reason `noise`, and the decision carries `paired = {"n", "mean", "se", "z", "upper"}`. The hard floor still blocks. One hidden bonus check rewards this; it can only add to the result and never fails the run.

## What Verify runs

Every check builds fresh case ids, token counts, seconds, thresholds and a fresh clock epoch. The scripted runner records every call and the case it received. The checks: a seeded regression blocks with the failing ids named and the accuracies recomputed; a drop inside the tolerance passes while a candidate under the floor blocks even against an equally weak baseline; a flaky case scripted F T T passes inside `runs = 3, pass_min = 2` while F F stops at the second call and F T F at the third, in the exact call order; the token cap and the time cap stop the run after the exceeding call with the counts, the reason and an archived partial result; three runs leave three files with every version pinned, an existing path is never overwritten; a subset touching a held-out id, an unknown id or an id without a baseline is rejected before any call or file; and changing only the model id archives a new run against the same baseline with the same config hash. No model output enters any verdict.

Two different implementations pass: plain functions over dicts with `os.path`, and dataclasses with a generator over attempts and `pathlib`. No structure of `gate.py` is required beyond the two importable names.

## Sources

- Hamel Husain and Shreya Shankar, AI Evals FAQ: a small purpose-built CI set, deterministic checks before judges, judges nightly or per release, the cost of each test.
- Hamel Husain, Creating a LLM-as-a-Judge: train, dev and test splits and why thresholds are never tuned on the frozen split.
- Evan Miller, Adding Error Bars to Evals (arXiv 2411.00640): paired differences and the standard error behind the bonus.
- Python `hashlib` and `json.dumps(sort_keys=True)`: a stable config hash; `open(path, "x")`: exclusive creation.
