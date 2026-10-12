"""Metric calculator for the golden set: field scores, abstention, intervals and the comparison verdict."""
import math

FIELDS = ("item", "quantity", "unit", "urgency")
ABSTAIN = "abstain"


def field_scores(predictions, references):
    result = {}
    for field in FIELDS:
        tp = fp = fn = 0
        for case, wanted in references.items():
            got = predictions.get(case)
            if not isinstance(wanted, dict):
                continue
            if isinstance(got, dict) and got.get(field) == wanted.get(field):
                tp += 1
            else:
                fn += 1
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        result[field] = {"tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall, "f1": f1}
    return result


def abstention_accuracy(predictions, references):
    correct = sum(1 for case, wanted in references.items() if wanted == ABSTAIN and predictions.get(case) == ABSTAIN)
    n = len(references)
    low, high = wilson(correct, n) if n else (None, None)
    return {"n": n, "correct": correct, "accuracy": correct / n if n else None, "low": low, "high": high}


def case_scores(predictions, references):
    scores = {}
    for case, wanted in references.items():
        got = predictions.get(case)
        if wanted == ABSTAIN:
            scores[case] = 1.0 if got == ABSTAIN else 0.0
        else:
            scores[case] = 1.0 if isinstance(got, dict) and all(got.get(f) == wanted.get(f) for f in FIELDS) else 0.0
    return scores


def wilson(successes, n, z=1.96):
    p = successes / n
    half = z * math.sqrt(p * (1 - p) / n)
    return p - half, p + half


def paired_comparison(scores_a, scores_b, z=1.96):
    n = len(scores_b)
    mean_a = sum(scores_a.values()) / n
    mean_b = sum(scores_b.values()) / n
    low_a, high_a = wilson(round(mean_a * n), n, z)
    low_b, high_b = wilson(round(mean_b * n), n, z)
    overlap = low_b <= high_a and low_a <= high_b
    verdict = "better" if mean_b > mean_a else "worse" if mean_b < mean_a else "inconclusive"
    return {"n": n, "mean_diff": mean_b - mean_a, "se": (high_b - low_b) / (2 * z), "low": low_b - high_a, "high": high_b - low_a,
            "verdict": verdict, "intervals_overlap": overlap}


def _summary(run, z):
    scores = case_scores(run["predictions"], run["references"])
    correct, n = int(sum(scores.values())), len(scores)
    low, high = wilson(correct, n, z)
    return {"name": run.get("name", ""), "fields": field_scores(run["predictions"], run["references"]),
            "abstention": abstention_accuracy(run["predictions"], run["references"]),
            "accuracy": {"correct": correct, "n": n, "mean": correct / n, "low": low, "high": high}}, scores


def report(run_a, run_b, z=1.96):
    a, scores_a = _summary(run_a, z)
    b, scores_b = _summary(run_b, z)
    return {"n": len(scores_b), "z": z, "a": a, "b": b, "paired": paired_comparison(scores_a, scores_b, z)}
