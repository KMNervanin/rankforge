# Field manual — a judge needs a judge

Code can check that a record has the right shape or that a citation id exists; it cannot check whether the cited runbook actually supports the sentence, or whether the assistant quietly reserved diesel nobody asked for. For those criteria the outpost uses a second model as a judge, and a judge is only worth as much as its agreement with human labels. The starter asks a model for a 1–10 score and averages it; it never measures agreement, never swaps the order of a comparison and pins nothing. That is the deliberate defect.

## Workshop and entry point

Python 3.10 or later, standard library only. Edit `judge.py` and keep these names importable: `JudgeParseError`, `UnlabeledCriterionError`, `judge_binary`, `judge_pairwise`, `length_bias_probe`, `calibrate`, `require_labels`, `calibration_report`. `criteria.json` holds three criteria, `items.json` nine answers of the assistant with the request and the source it had, `labels.json` human labels per criterion and item; `neutral_tone` has no labels on purpose. Verify carries its own criteria, items, labels and judge version with fresh values, so read everything from the arguments, never from these files.

`python3 -B demo.py` prints the calibration report of `cites_source` against the endpoint in `llm.json`; `python3 -B demo.py within_request` reports another criterion, `python3 -B demo.py neutral_tone` must be refused, `--pairwise` compares two answers with the order swap and `--probe` runs the length-bias probe. `llm.json` holds the endpoint, the model id and your judge version string; an API key, if the endpoint needs one, lives in `LLM_API_KEY`. Use a different model as judge than the one whose answers you judge when you can: a model grading itself shares its blind spots.

## Why binary, and why rates instead of agreement

A score from 1 to 10 hides two decisions in one number: what the criterion means, and where the line is. A binary question per criterion, "does the answer cite a source that supports it: PASS or FAIL", forces both into the prompt, where you can read and version them, and gives a verdict a human can agree or disagree with. Agreement with human labels is then measured as two rates, because one number misleads under class imbalance: a judge that always says PASS on a set with nine good answers and one bad one agrees with the humans 90% of the time and catches zero failures. The **true-positive rate** (TPR, the recall of PASS) is the share of human-PASS items the judge passes; the **true-negative rate** (TNR) is the share of human-FAIL items the judge fails. Raw agreement is reported next to them, never alone.

Pairwise judges have their own biases. MT-Bench measured that a judge prefers the answer shown first and the answer that is longer. The order probe is the cure for the first: ask twice with the answers swapped and count a win only when both orders agree, otherwise call it a tie. The length probe measures the second: a short, supported answer against the same answer padded with repetition; if the padded one wins, the judge is measuring length.

## Complete public contract

A **criterion** is a dict with `id`, `name` and `instruction` (the sentence the judge checks). An **item** is a dict with `id`, `request`, `answer` and `source`. A **label** is `{"item_id", "label": bool}`; a **label store** maps a criterion id to its list of labels, the shape of `labels.json`. Every function below reaches the model through `POST {base_url}/chat/completions` with `model`, `messages`, an integer `max_tokens` between 1 and 64 and `temperature`.

```python
judge_binary(criterion, item, *, base_url, model, judge_version, max_tokens=4, temperature=0.0) -> dict
```

1. **One request per item.** The criterion prompt is one message of its own, containing no item text: its text includes `criterion["instruction"]` verbatim and the words `PASS` and `FAIL`. The item's `request`, `source` and `answer` go verbatim in a separate message. Which role each message has is yours. Verify passes its own `max_tokens` explicitly, so the default of 4 and the 8 in `llm.json` are both fine.
2. **A strict grammar.** Strip whitespace and the characters `*`, `` ` ``, `"`, `'`, `.` and `!` from both ends of the answer text and compare case-insensitively: `PASS` gives `verdict: true`, `FAIL` gives `verdict: false`. Anything else, including `7/10`, `Score: 8`, `Mostly PASS` or an empty answer, raises `JudgeParseError`. A parse failure is never a verdict in either direction.
3. **Every result is pinned.** The dict carries `item_id`, `criterion_id`, `verdict` (bool), `raw` (the answer text verbatim), `judge_version` (the string you were given), `model` (the model id called) and `prompt_hash`: the lowercase SHA-256 hex digest of the criterion prompt exactly as sent, so Verify can find a message in the request whose content hashes to it. Two items under one criterion share a hash; two criteria never do.

```python
judge_pairwise(criterion, a, b, *, base_url, model, judge_version, max_tokens=4, temperature=0.0) -> dict
```

4. **Two requests, opposite orders.** The first request presents `a["answer"]` before `b["answer"]` as A and B, the second presents `b` before `a`. Both answers appear verbatim in both requests. The grammar is `A`, `B` or `TIE` with the same stripping as above; anything else raises `JudgeParseError`.
5. **The MT-Bench rule.** `result` is `"win"` for `a` only when both orders prefer `a` (A in the first, B in the second), `"loss"` only when both prefer `b`, and `"tie"` in every other case, including two `TIE` answers and a judge that always picks the same letter. The result carries `judge_version`, `model` and `prompt_hash` (the hash of the pairwise criterion prompt, which may differ from the binary one), plus the raw texts of both calls.

```python
length_bias_probe(criterion, short_good, long_padded, *, base_url, model, judge_version, **options) -> dict
```

6. The probe is one pairwise judgment of `short_good` against `long_padded` through rule 4 and 5. `padded_won` is `true` exactly when the result is a loss for the short answer. The dict carries the pins and the pairwise result.

```python
calibrate(verdicts, labels) -> dict
require_labels(criterion, label_store) -> list
calibration_report(criterion, items, label_store, *, base_url, model, judge_version, **options) -> dict
```

7. **Rates from aligned ids.** `verdicts` are `judge_binary` results, `labels` human labels; they must cover exactly the same item ids with no duplicates, otherwise `ValueError`. With TP = human PASS and judge PASS, FN = human PASS and judge FAIL, TN and FP likewise: `tpr = TP / n_pos`, `tnr = TN / n_neg`, `agreement = (TP + TN) / n`, where `n_pos` and `n_neg` are the counts of human PASS and FAIL labels. Compute with `fractions.Fraction` and return each rate as a float or int within 1e-9 of the exact value (a `Fraction` is also accepted); a rate with a zero denominator is `None`. Worked example: labels PASS, PASS, FAIL, FAIL; judge PASS, FAIL, FAIL, PASS gives TPR 1/2, TNR 1/2, agreement 2/4.
8. **No labels, no judge.** `require_labels` returns the criterion's labels when the store holds at least one PASS and one FAIL label for it, and raises `UnlabeledCriterionError` otherwise: a new criterion needs new labels before it is used, and labels of one class cannot give both rates. `calibration_report` calls it first, so an unlabeled criterion sends no request at all.
9. **The report.** `calibration_report` judges every labeled item once and returns `criterion_id`, `verdicts` (one `judge_binary` result per labeled item), `tpr`, `tnr`, `agreement`, `n_pos`, `n_neg` and the pins. A mean score with no agreement data is not a report.

Bonus (optional): `consistency_probe(criterion, item, *, base_url, model, judge_version, k=5, ...)` judges one item `k` times and returns `verdicts` (the `k` booleans in order), `flip_rate` (the minority share) and the pins.

Transport errors may raise any exception; retries are the backoff mission's job.

## What Verify runs

- A **scripted adapter**: a loopback server that speaks the contract and answers from rules Verify chooses. It passes items that contain a hidden marker so TPR and TNR are known from the planted labels; it always answers PASS on a 9:1 set to show agreement 9/10 with TNR 0; it answers `7/10`-style scores that must raise `JudgeParseError`; it always prefers the first answer, which must come out as a tie; it prefers the longer answer, which the probe must report as `padded_won: true`; and it records whether both orders were sent. It is a labeled test tool, not a model.
- One **live run**: four labeled fixtures judged through `judge_binary` on the endpoint in `llm.json` with `max_tokens` from that file, reported as parsed count, agreement, TPR and TNR with the model id, judge version and prompt hash. Numbers are measurements of one run, never pass or fail. No model id, or no answer within 15 seconds, is **Environment blocked**; the whole live section has a 20-second budget, so warm the model up with the demo first.

Two different implementations pass: `urllib.request` with module-level functions and an explicit confusion count, and `http.client` with a `Judge` dataclass, regex grammars and a `Counter` of (label, verdict) cells.

## Sources

- Hamel Husain, *Creating a LLM-as-a-Judge that drives business results*: binary pass/fail per criterion, TPR and TNR against human labels, why raw agreement misleads under imbalance.
- Hamel Husain and Shreya Shankar, *AI Evals FAQ*: a judge is calibrated on labels before it is trusted; a new criterion needs its own labels.
- Zheng et al., *Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena* (arXiv 2306.05685), sections 3.3–3.4: position bias and the swap rule, verbosity bias.
- Anthropic, *Define your success criteria / Develop test cases*: prefer code grading, then model grading, then human grading; grade with a different model than the one that generated.
