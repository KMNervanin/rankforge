# Field manual — numbers with error bars

The golden set exists and two prompt versions have been run over it. The operator wants to know whether v3 is better than v2, and the starter answers "yes" because 21 is more than 18. On thirty cases that is a coin toss dressed as a result. That is the deliberate defect.

## Workshop and entry point

Python 3.10 or later, standard library only. Edit `metrics.py` and keep six names importable: `field_scores`, `abstention_accuracy`, `case_scores`, `wilson`, `paired_comparison` and `report`. Verify imports your module and calls each function with its own tiny fixtures whose expected numbers are recomputed independently with exact fractions and closed forms; names, quantities and which cases differ change on every run, so compute everything from the arguments.

`golden.json` is a thirty-case golden set (`cases`: case id → reference outcome; `texts`: the request each case came from). `runs/prompt-v2.json` and `runs/prompt-v3.json` are two runs of the extraction step over it (`predictions`: case id → outcome). `python3 -B demo.py` scores both runs and prints the comparison; `python3 -B demo.py runs/prompt-v2.json runs/prompt-v3-swapped.json` compares a run with the same exact-match count as v3 but a different set of right answers. There is no live call in this mission: every number comes from code.

## Outcomes, records and normalization

An **outcome** is either a record, a dict with the fields `item`, `quantity`, `unit` and `urgency` (extra keys such as `requester` are ignored), the string `"abstain"` (the assistant declined because the text is not a supply request), or `null` for a run that produced nothing usable. References are records or `"abstain"`.

Two field values are compared **after normalization**: a number that is integral (`12`, `12.0`) becomes its decimal digits (`"12"`); everything else becomes `str(value)`; then whitespace is trimmed and collapsed to single spaces and the text is casefolded. So `"  Water  FILTER "` equals `"water filter"` and `"12"` equals `12`, while `"many"` does not equal `12`. A field that is missing or `null` in an outcome is **no prediction** for that field, and an outcome that is `"abstain"` or `null` predicts no field at all.

## Complete public contract

Every function that takes two mappings requires **the same set of case ids on both sides** and at least one case; a case id missing on one side, unexpected on the other, or an empty set raises `ValueError`. Never score what you can and skip the rest. Tolerance on every number is 1e-9.

```python
field_scores(predictions, references) -> {field: {tp, fp, fn, precision, recall, f1}}
```

For each of the four fields, over all cases: a **true positive** is a predicted value equal to the reference value after normalization; a predicted value with no reference value or a different one is a **false positive**; a reference value with no predicted value or a different one is a **false negative**. A mismatch is therefore one false positive and one false negative. `precision = tp / (tp + fp)`, `recall = tp / (tp + fn)`, `f1 = 2PR / (P + R)`, each `0.0` when its denominator is zero. The result has exactly the four fields.

```python
abstention_accuracy(predictions, references) -> {n, correct, accuracy, low, high}
```

`n` counts the cases whose **reference** is `"abstain"`, `correct` those among them whose prediction is `"abstain"`, `accuracy = correct / n`, and `low`, `high` the Wilson interval of that proportion, always at z = 1.96, even when `report` is called with another `z`. A prediction that abstains on a real request is wrong, but it is not abstention accuracy: it shows up as false negatives in the field scores and as a zero in the case score. With `n == 0` the result is `{"n": 0, "correct": 0, "accuracy": None, "low": None, "high": None}`.

```python
case_scores(predictions, references) -> {case_id: 0.0 | 1.0}
```

**Exact match.** A case scores 1 when the reference is `"abstain"` and the prediction is `"abstain"`, or when the reference is a record and the prediction is a record whose four fields all equal the reference after normalization. Anything else scores 0. Verify uses these scores as the per-case input of the comparison.

```python
wilson(successes, n, z=1.96) -> (low, high)
```

The Wilson score interval for a proportion `p = successes / n`:

```
center = (p + z²/(2n)) / (1 + z²/n)
half   = z · sqrt(p(1 − p)/n + z²/(4n²)) / (1 + z²/n)
```

Both bounds stay inside `[0, 1]`: 0 of 5 gives `[0, 0.434]`, 30 of 30 gives `[0.886, 1]`, 7 of 10 gives `[0.397, 0.892]`. Clamp against floating-point dust. `n == 0` raises `ValueError`. The naive `p ± z·sqrt(p(1−p)/n)` is wrong here: it gives `[0, 0]` for 0 of 5, `[1, 1]` for 30 of 30 and crosses 1 for 29 of 30.

```python
paired_comparison(scores_a, scores_b, z=1.96, clusters=None) -> {n, mean_diff, se, low, high, verdict}
```

The published rule for "is B better than A" (Miller 2024). Both inputs map case ids to numbers in `[0, 1]`. For every case `d = b − a`. `mean_diff` is the mean of the differences, `se` is their **sample standard deviation (divided by n − 1) over sqrt(n)**, `low = mean_diff − z·se`, `high = mean_diff + z·se`. The verdict is `"better"` when `low > 0`, `"worse"` when `high < 0`, otherwise `"inconclusive"`. Fewer than two cases raise `ValueError`. Two overlapping intervals never decide anything, and neither do two means: the information is in the per-case differences. A run where B is right on everything A is right on plus four more cases is better; a run with the same count that lost four of A's cases and gained ten is inconclusive, because its differences disagree with each other.

Worked example: thirty cases, three improved by 0.5, three worse by 0.3, twenty-four unchanged. The mean difference is +0.02 (two points), the sample variance is 1.008 / 29 = 0.03476, `se = sqrt(0.03476 / 30) = 0.0340`, the interval is `[−0.047, +0.087]`: **inconclusive**. The same two points on 1000 cases as twenty cases improved by 1: variance 19.6 / 999 = 0.01962, `se = 0.00443`, interval `[+0.011, +0.029]`: **better**. The set size changed the conclusion, the effect did not.

The optional `clusters` argument is for the rumour: a mapping from case id to the source document it came from. When several cases share a source their errors move together and the plain standard error is too small. With clusters the standard error is `sqrt(Σ_c (Σ_{i∈c} (d_i − mean))²) / n`, the sum running over clusters. `S_c = Σ_{i∈c}(d_i − mean)` is summed first, then squared: `se = sqrt(Σ_c S_c²) / n`. With one case per cluster this is the population version of the plain `se`; with a single cluster it is 0, so fewer than two clusters raises `ValueError`. The verdict rule is unchanged.

```python
report(run_a, run_b, z=1.96, clusters=None) -> dict
```

A run is `{"name", "predictions", "references"}`. The two runs must carry **equal references** (the same golden set, else `ValueError`). The report has `n` (cases), `z`, `a` and `b`, each `{name, fields, abstention, accuracy}` where `accuracy = {correct, n, mean, low, high}` is the exact-match count with its Wilson interval; `paired`, the paired comparison of the two runs' case scores; and `needed_n`, the set size at which the observed difference would be detected at 80 % power: `ceil((z + 0.8416)² · variance / mean_diff²)` with the plain (unclustered) sample variance of the differences, even when `clusters` is given, and 0.8416 = Φ⁻¹(0.80); the result is an int, or `null` when the mean difference is 0. Verify accepts `needed_n` within 1 of its own ceiling. Extra keys are allowed everywhere.

## What Verify runs

Six cases with hand-counted true positives, false positives and false negatives per field (shouted item names, a quantity as a string, a null unit, a record where the reference abstains, an abstention where the reference is a record, an extra key). Twelve cases with five abstain references, some matched, and real requests wrongly abstained on. Wilson bounds for 7/10, 0/5, 30/30, a fresh n−1 of n and a fresh middle count, at z = 1.96, and z = 2.576 for 7/10 only. The two-point difference on 30 cases (inconclusive) and on 1000 cases (better, and worse reversed). Forty cases whose unpaired intervals overlap but whose paired differences decide better, next to a run with the same mean and disagreeing differences. A report over twelve cases with its intervals, field counts, abstention, paired verdict and needed_n. Misaligned ids, a single case and two different golden sets refused by every function. Every expected number is recomputed independently inside Verify with `fractions.Fraction` and the closed forms above (square roots through float); nothing is learned from your module. No model is called.

Two different implementations pass: plain dicts, loops and `math`, or `statistics.fmean` and `statistics.variance` with dataclasses and `Counter`. No structure of `metrics.py` is required beyond the six importable names.

## Sources

- Evan Miller, "Adding Error Bars to Evals: A Statistical Approach to Language Model Evaluations" (arXiv 2411.00640, 2024): the standard error of the mean suffices; use the paired version wherever practicable; do not compare two overlapping intervals; never lower the temperature to reduce variance; clustered standard errors when questions share a source; power analysis.
- Wilson score interval: Wikipedia, "Binomial proportion confidence interval", and Wilson (1927).
- Python `statistics` (`fmean`, `variance`, `NormalDist`) and `fractions.Fraction` for an exact oracle.
