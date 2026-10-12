"""Metric calculator built on the statistics module, dataclasses and Counter; clusters via NormalDist-free sums."""
from collections import Counter, defaultdict
from dataclasses import dataclass
from math import ceil, isfinite, sqrt
from statistics import fmean, variance

FIELDS = ("item", "quantity", "unit", "urgency")
ABSTAIN = "abstain"
Z_POWER = 0.8416


@dataclass(frozen=True)
class Aligned:
    ids: tuple
    left: dict
    right: dict

    @classmethod
    def of(cls, left, right):
        if not isinstance(left, dict) or not isinstance(right, dict):
            raise ValueError("expected two mappings keyed by case id")
        if left.keys() != right.keys():
            raise ValueError(f"case ids differ: {sorted(left.keys() ^ right.keys())[:6]}")
        if not left:
            raise ValueError("no cases")
        return cls(tuple(sorted(left)), left, right)


def normalize(value):
    if isinstance(value, bool):
        return str(value).casefold()
    if isinstance(value, (int, float)) and isfinite(value) and float(value).is_integer():
        return str(int(value))
    return " ".join(str(value).split()).casefold()


def value_of(outcome, field):
    if isinstance(outcome, dict) and outcome.get(field) is not None:
        return normalize(outcome[field])
    return None


def field_scores(predictions, references):
    pairs = Aligned.of(predictions, references)
    tally = {field: Counter() for field in FIELDS}
    for case in pairs.ids:
        for field in FIELDS:
            got, wanted = value_of(predictions[case], field), value_of(references[case], field)
            if got is not None and got == wanted:
                tally[field]["tp"] += 1
            else:
                tally[field]["fp"] += got is not None
                tally[field]["fn"] += wanted is not None
    out = {}
    for field, counter in tally.items():
        tp, fp, fn = counter["tp"], counter["fp"], counter["fn"]
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        out[field] = {"tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall, "f1": f1}
    return out


def abstention_accuracy(predictions, references):
    pairs = Aligned.of(predictions, references)
    wanted = [case for case in pairs.ids if references[case] == ABSTAIN]
    hits = Counter(predictions[case] == ABSTAIN for case in wanted)[True]
    if not wanted:
        return {"n": 0, "correct": 0, "accuracy": None, "low": None, "high": None}
    low, high = wilson(hits, len(wanted))
    return {"n": len(wanted), "correct": hits, "accuracy": hits / len(wanted), "low": low, "high": high}


def case_scores(predictions, references):
    pairs = Aligned.of(predictions, references)
    out = {}
    for case in pairs.ids:
        got, wanted = predictions[case], references[case]
        if wanted == ABSTAIN:
            out[case] = float(got == ABSTAIN)
        else:
            out[case] = float(isinstance(got, dict) and all(value_of(got, f) is not None and value_of(got, f) == value_of(wanted, f) for f in FIELDS))
    return out


def wilson(successes, n, z=1.96):
    if n <= 0 or successes < 0 or successes > n:
        raise ValueError("wilson needs 0 <= successes <= n with n > 0")
    p, z2 = successes / n, z * z
    center = (p + z2 / (2 * n)) / (1 + z2 / n)
    half = z * sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / (1 + z2 / n)
    return max(0.0, center - half), min(1.0, center + half)


def paired_comparison(scores_a, scores_b, z=1.96, clusters=None):
    pairs = Aligned.of(scores_a, scores_b)
    if len(pairs.ids) < 2:
        raise ValueError("need at least two paired cases")
    diffs = [float(scores_b[case]) - float(scores_a[case]) for case in pairs.ids]
    n, mean = len(diffs), fmean(diffs)
    if clusters is None:
        se = sqrt(variance(diffs, mean) / n)
    else:
        if set(clusters) != set(pairs.ids):
            raise ValueError("clusters must cover exactly the case ids")
        if len(set(clusters.values())) < 2:
            raise ValueError("need at least two clusters")
        per_cluster = defaultdict(float)
        for case, d in zip(pairs.ids, diffs):
            per_cluster[clusters[case]] += d - mean
        se = sqrt(sum(s * s for s in per_cluster.values())) / n
    low, high = mean - z * se, mean + z * se
    verdict = "better" if low > 0 else ("worse" if high < 0 else "inconclusive")
    return {"n": n, "mean_diff": mean, "se": se, "low": low, "high": high, "verdict": verdict, "clustered": clusters is not None}


def needed_n(diffs, z=1.96, z_power=Z_POWER):
    mean = fmean(diffs)
    if mean == 0 or len(diffs) < 2:
        return None
    return ceil((z + z_power) ** 2 * variance(diffs, mean) / mean ** 2)


def summarize(run, z):
    scores = case_scores(run["predictions"], run["references"])
    correct = int(sum(scores.values()))
    low, high = wilson(correct, len(scores), z)
    return {"name": run.get("name", ""), "fields": field_scores(run["predictions"], run["references"]),
            "abstention": abstention_accuracy(run["predictions"], run["references"]),
            "accuracy": {"correct": correct, "n": len(scores), "mean": correct / len(scores), "low": low, "high": high}}, scores


def report(run_a, run_b, z=1.96, clusters=None):
    if run_a["references"] != run_b["references"]:
        raise ValueError("runs must share the same golden set")
    a, scores_a = summarize(run_a, z)
    b, scores_b = summarize(run_b, z)
    diffs = [scores_b[case] - scores_a[case] for case in sorted(scores_a)]
    return {"n": len(diffs), "z": z, "z_power": Z_POWER, "a": a, "b": b,
            "paired": paired_comparison(scores_a, scores_b, z, clusters), "needed_n": needed_n(diffs, z)}
