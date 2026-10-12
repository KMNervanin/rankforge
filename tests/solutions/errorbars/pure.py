"""Metric calculator: plain dicts, loops and math; clustered standard error when cases share a source."""
import math

FIELDS = ("item", "quantity", "unit", "urgency")
ABSTAIN = "abstain"
Z_POWER = 0.8416  # Φ⁻¹(0.80) to four decimals: 80 % power


def normalize(value):
    if isinstance(value, bool):
        return str(value).casefold()
    if isinstance(value, (int, float)) and math.isfinite(value) and value == int(value):
        return str(int(value))
    return " ".join(str(value).split()).casefold()


def _aligned(predictions, references):
    if not isinstance(predictions, dict) or not isinstance(references, dict):
        raise ValueError("predictions and references must be mappings from case id to outcome")
    if set(predictions) != set(references):
        missing = sorted(set(references) - set(predictions))
        extra = sorted(set(predictions) - set(references))
        raise ValueError(f"case ids differ: missing {missing[:5]}, unexpected {extra[:5]}")
    if not references:
        raise ValueError("no cases")
    return sorted(references)


def _field(outcome, field):
    if isinstance(outcome, dict) and outcome.get(field) is not None:
        return normalize(outcome[field])
    return None


def field_scores(predictions, references):
    ids = _aligned(predictions, references)
    counts = {field: {"tp": 0, "fp": 0, "fn": 0} for field in FIELDS}
    for case in ids:
        for field in FIELDS:
            got, wanted = _field(predictions[case], field), _field(references[case], field)
            if got is not None and wanted is not None and got == wanted:
                counts[field]["tp"] += 1
                continue
            if got is not None:
                counts[field]["fp"] += 1
            if wanted is not None:
                counts[field]["fn"] += 1
    result = {}
    for field, c in counts.items():
        precision = c["tp"] / (c["tp"] + c["fp"]) if c["tp"] + c["fp"] else 0.0
        recall = c["tp"] / (c["tp"] + c["fn"]) if c["tp"] + c["fn"] else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        result[field] = {**c, "precision": precision, "recall": recall, "f1": f1}
    return result


def abstention_accuracy(predictions, references):
    ids = _aligned(predictions, references)
    expected = [case for case in ids if references[case] == ABSTAIN]
    correct = sum(1 for case in expected if predictions[case] == ABSTAIN)
    n = len(expected)
    if n == 0:
        return {"n": 0, "correct": 0, "accuracy": None, "low": None, "high": None}
    low, high = wilson(correct, n)
    return {"n": n, "correct": correct, "accuracy": correct / n, "low": low, "high": high}


def case_scores(predictions, references):
    ids = _aligned(predictions, references)
    scores = {}
    for case in ids:
        got, wanted = predictions[case], references[case]
        if wanted == ABSTAIN:
            scores[case] = 1.0 if got == ABSTAIN else 0.0
        elif isinstance(got, dict):
            scores[case] = 1.0 if all(_field(got, f) is not None and _field(got, f) == _field(wanted, f) for f in FIELDS) else 0.0
        else:
            scores[case] = 0.0
    return scores


def wilson(successes, n, z=1.96):
    if n <= 0 or not 0 <= successes <= n:
        raise ValueError("wilson needs 0 <= successes <= n and n > 0")
    p = successes / n
    z2 = z * z
    denominator = 1 + z2 / n
    center = (p + z2 / (2 * n)) / denominator
    half = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / denominator
    return max(0.0, center - half), min(1.0, center + half)


def paired_comparison(scores_a, scores_b, z=1.96, clusters=None):
    ids = _aligned(scores_a, scores_b)
    n = len(ids)
    if n < 2:
        raise ValueError("a paired comparison needs at least two cases")
    diffs = {case: float(scores_b[case]) - float(scores_a[case]) for case in ids}
    mean = sum(diffs.values()) / n
    if clusters is None:
        variance = sum((d - mean) ** 2 for d in diffs.values()) / (n - 1)
        se = math.sqrt(variance / n)
    else:
        if set(clusters) != set(ids):
            raise ValueError("clusters must map every case id to a cluster id")
        if len(set(clusters.values())) < 2:
            raise ValueError("a clustered standard error needs at least two clusters")
        sums = {}
        for case, d in diffs.items():
            sums[clusters[case]] = sums.get(clusters[case], 0.0) + (d - mean)
        se = math.sqrt(sum(s * s for s in sums.values())) / n
    low, high = mean - z * se, mean + z * se
    verdict = "better" if low > 0 else "worse" if high < 0 else "inconclusive"
    return {"n": n, "mean_diff": mean, "se": se, "low": low, "high": high, "verdict": verdict, "clustered": clusters is not None}


def needed_n(scores_a, scores_b, z=1.96, z_power=Z_POWER):
    ids = _aligned(scores_a, scores_b)
    diffs = [float(scores_b[c]) - float(scores_a[c]) for c in ids]
    n = len(diffs)
    mean = sum(diffs) / n
    if mean == 0 or n < 2:
        return None
    variance = sum((d - mean) ** 2 for d in diffs) / (n - 1)
    return math.ceil((z + z_power) ** 2 * variance / (mean * mean))


def _summary(run, z):
    predictions, references = run["predictions"], run["references"]
    scores = case_scores(predictions, references)
    correct, n = int(sum(scores.values())), len(scores)
    low, high = wilson(correct, n, z)
    return {"name": run.get("name", ""), "fields": field_scores(predictions, references), "abstention": abstention_accuracy(predictions, references),
            "accuracy": {"correct": correct, "n": n, "mean": correct / n, "low": low, "high": high}}, scores


def report(run_a, run_b, z=1.96, clusters=None):
    if run_a["references"] != run_b["references"]:
        raise ValueError("two runs can only be compared on the same golden set")
    a, scores_a = _summary(run_a, z)
    b, scores_b = _summary(run_b, z)
    return {"n": len(scores_a), "z": z, "z_power": Z_POWER, "a": a, "b": b,
            "paired": paired_comparison(scores_a, scores_b, z, clusters), "needed_n": needed_n(scores_a, scores_b, z)}
