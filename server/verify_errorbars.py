"""Metric and error-bar checks for the Errorbars mission; run outside the learner workspace.

Nothing here calls a model. Every expected number is recomputed inside this file with fractions.Fraction
and the closed-form Wilson formula on tiny fixtures whose counts were fixed by hand; fresh surface values
(names, quantities, which cases differ) change on every run so a hardcoded answer cannot pass.
"""
import importlib.util
import json
import math
import os
import random
import sys
from fractions import Fraction

MISSION, WORKSPACE = sys.argv[1:3]
CHECKS = []
FIELDS = ("item", "quantity", "unit", "urgency")
Z = Fraction(196, 100)
Z_POWER = Fraction(8416, 10000)
TOLERANCE = Fraction(1, 10**9)
ITEMS = ["water filter", "filter cartridge", "fuel can", "signal flare", "thermal blanket", "relay fuse", "antenna mast", "medkit"]
UNITS = ["piece", "box", "litre", "kilogram"]
URGENCY = ["low", "normal", "high"]


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def check(name, operation, optional=False):
    # An optional check is the hidden bonus of a mission: it can only add, it never fails the run.
    flag = {"optional": True} if optional else {}
    try:
        detail = operation()
        CHECKS.append({"name": name, "passed": True, "detail": detail or "Hand-computed fixture reproduced.", **flag})
    except Exception as error:
        CHECKS.append({"name": name, "passed": False, "detail": f"{type(error).__name__}: {error}"[:1500], **flag})


def close(got, wanted, what):
    require(isinstance(got, (int, float)) and not isinstance(got, bool) and math.isfinite(got), f"{what} must be a finite number, got {got!r}")
    require(abs(Fraction(str(got)) - Fraction(wanted)) <= TOLERANCE, f"{what} is {got!r}, expected {float(wanted)!r} (tolerance 1e-9)")


def rates(tp, fp, fn):
    precision = Fraction(tp, tp + fp) if tp + fp else Fraction(0)
    recall = Fraction(tp, tp + fn) if tp + fn else Fraction(0)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else Fraction(0)
    return precision, recall, f1


def wilson_expected(successes, n, z=Z):
    p = Fraction(successes, n)
    denominator = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denominator
    half = z * Fraction(math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denominator
    return center - half, center + half


def paired_expected(diffs, z=Z):
    n = len(diffs)
    mean = sum(diffs, Fraction(0)) / n
    variance = sum((d - mean) ** 2 for d in diffs) / (n - 1)
    se = Fraction(math.sqrt(variance / n))
    return mean, variance, se, mean - z * se, mean + z * se


def clustered_expected(diffs, groups, z=Z):
    n = len(diffs)
    mean = sum(diffs, Fraction(0)) / n
    sums = {}
    for d, group in zip(diffs, groups):
        sums[group] = sums.get(group, Fraction(0)) + (d - mean)
    se = Fraction(math.sqrt(sum(s * s for s in sums.values()))) / n
    return mean, se, mean - z * se, mean + z * se


def record(item, quantity, unit, urgency):
    return {"item": item, "quantity": quantity, "unit": unit, "urgency": urgency}


def shout(text):
    return "  " + "  ".join(text.upper().split()) + " "


def trial():
    require(MISSION == "errorbars", "Unknown mission")
    sys.path.insert(0, WORKSPACE)
    spec = importlib.util.spec_from_file_location("candidate_errorbars", os.path.join(WORKSPACE, "metrics.py"))
    if spec is None or spec.loader is None:
        raise ImportError("Cannot load metrics.py")
    candidate = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = candidate
    spec.loader.exec_module(candidate)
    for name in ("field_scores", "abstention_accuracy", "case_scores", "wilson", "paired_comparison", "report"):
        require(callable(getattr(candidate, name, None)), f"metrics.py must define {name}(...)")
    rng = random.Random()

    def scores_of(diffs, ids=None):
        """Builds two aligned 0/1 (or 0..1) score mappings whose per-case differences are exactly diffs."""
        ids = ids or [f"c{rng.randint(100, 999)}-{index:04d}" for index in range(len(diffs))]
        a, b = {}, {}
        for case, d in zip(ids, diffs):
            if d > 0:
                a[case], b[case] = 0.0, float(d)
            elif d < 0:
                a[case], b[case] = float(-d), 0.0
            else:
                a[case] = b[case] = float(rng.randint(0, 1))
        return a, b

    def fields():
        item, other = rng.sample(ITEMS, 2)
        quantity = rng.randint(2, 40)
        unit, urgency = rng.choice(UNITS), rng.choice(URGENCY)
        other_urgency = rng.choice([u for u in URGENCY if u != urgency])
        references = {
            "r1": record(item, quantity, unit, urgency),
            "r2": record(other, quantity + 1, unit, urgency),
            "r3": record(item, quantity, unit, other_urgency),
            "r4": "abstain",
            "r5": record(other, 3, unit, urgency),
            "r6": record(item, quantity, unit, urgency),
        }
        predictions = {
            "r1": record(shout(item), str(quantity), unit.upper(), urgency),        # all four equal after normalization
            "r2": record(other, quantity, unit, urgency),                             # quantity off by one
            "r3": {"item": item, "quantity": float(quantity), "unit": None},          # urgency absent, unit null: no prediction for two fields
            "r4": record(other, 1, unit, "high"),                                     # answered instead of abstaining: four false positives
            "r5": "abstain",                                                          # abstained on a real request: four false negatives
            "r6": {"item": shout(item), "quantity": "many", "unit": unit, "urgency": urgency, "requester": "Mara"},  # quantity wrong, extra key ignored
        }
        # Hand count (tp, fp, fn): r1 all tp; r2 item/unit/urgency tp, quantity fp+fn; r3 item/quantity tp, unit fn, urgency fn;
        # r4 four fp; r5 four fn; r6 item/unit/urgency tp, quantity fp+fn.
        expected = {"item": (4, 1, 1), "quantity": (2, 3, 3), "unit": (3, 1, 2), "urgency": (3, 1, 2)}
        got = candidate.field_scores(predictions, references)
        require(isinstance(got, dict) and set(got) == set(FIELDS), f"field_scores must return exactly the four fields {FIELDS}, got {sorted(got) if isinstance(got, dict) else type(got).__name__}")
        for field, (tp, fp, fn) in expected.items():
            entry = got[field]
            require(isinstance(entry, dict), f"field_scores[{field!r}] must be a dict")
            require(entry.get("tp") == tp and entry.get("fp") == fp and entry.get("fn") == fn, f"{field}: expected tp={tp} fp={fp} fn={fn}, got tp={entry.get('tp')!r} fp={entry.get('fp')!r} fn={entry.get('fn')!r}. Normalization: trimmed, whitespace collapsed, casefolded; integral numbers compare by their digits; a null or missing field is no prediction; a mismatch is one false positive and one false negative")
            precision, recall, f1 = rates(tp, fp, fn)
            close(entry.get("precision"), precision, f"{field} precision")
            close(entry.get("recall"), recall, f"{field} recall")
            close(entry.get("f1"), f1, f"{field} f1")
        return f"Six cases on {item!r}/{other!r}: item 4/1/1, quantity 2/3/3, unit 3/1/2, urgency 3/1/2 (tp/fp/fn) reproduced with precision, recall and F1."
    check("Field scores: per-field precision, recall and F1 match the hand-counted fixture after the published normalization", fields)

    def abstention():
        item = rng.choice(ITEMS)
        references, predictions = {}, {}
        abstain_ids = rng.sample(range(1, 13), 5)
        hits = rng.randint(1, 4)
        for index in range(1, 13):
            case = f"a{index:02d}"
            if index in abstain_ids:
                references[case] = "abstain"
                predictions[case] = "abstain" if len([i for i in abstain_ids if i <= index]) <= hits else record(item, 1, "piece", "low")
            else:
                references[case] = record(item, index, "piece", "normal")
                predictions[case] = "abstain" if index % 2 else record(item, index, "piece", "normal")  # abstaining on real requests is not abstention accuracy
        got = candidate.abstention_accuracy(predictions, references)
        require(isinstance(got, dict), "abstention_accuracy must return a dict")
        require(got.get("n") == 5 and got.get("correct") == hits, f"Five references abstain and {hits} predictions matched: expected n=5 correct={hits}, got n={got.get('n')!r} correct={got.get('correct')!r}. Cases whose reference is a record never count, however the prediction abstained")
        close(got.get("accuracy"), Fraction(hits, 5), "abstention accuracy")
        low, high = wilson_expected(hits, 5)
        close(got.get("low"), low, "abstention low")
        close(got.get("high"), high, "abstention high")
        empty = candidate.abstention_accuracy({"x1": record(item, 1, "piece", "low")}, {"x1": record(item, 1, "piece", "low")})
        require(empty.get("n") == 0 and empty.get("correct") == 0 and empty.get("accuracy") is None and empty.get("low") is None and empty.get("high") is None, "With no abstain reference the result is n=0, correct=0 and accuracy, low, high null")
        return f"{hits} of 5 abstain references matched; the 7 record cases (3 wrongly abstained) were ignored; Wilson bounds and the empty case reproduced."
    check("Abstention accuracy counts only the cases whose reference is abstain, with a Wilson interval", abstention)

    def wilson():
        n_edge = rng.randint(12, 40)
        n_mid = rng.randint(20, 80)
        pairs = [(7, 10), (0, 5), (30, 30), (n_edge - 1, n_edge), (rng.randint(1, n_mid - 1), n_mid)]
        for successes, n in pairs:
            got = candidate.wilson(successes, n)
            require(isinstance(got, (tuple, list)) and len(got) == 2, f"wilson({successes}, {n}) must return (low, high)")
            low, high = wilson_expected(successes, n)
            close(got[0], low, f"wilson({successes}, {n}) low")
            close(got[1], high, f"wilson({successes}, {n}) high")
            require(-1e-9 <= got[0] <= got[1] <= 1 + 1e-9, f"wilson({successes}, {n}) = {got!r} must stay inside [0, 1]")
        z = Fraction(2576, 1000)
        got = candidate.wilson(7, 10, z=float(z))
        low, high = wilson_expected(7, 10, z)
        close(got[0], low, "wilson(7, 10, z=2.576) low")
        close(got[1], high, "wilson(7, 10, z=2.576) high")
        refused = False
        try:
            candidate.wilson(0, 0)
        except ValueError:
            refused = True
        require(refused, "wilson(0, 0) must raise ValueError")
        return f"Wilson bounds for 7/10, 0/5, 30/30, {n_edge - 1}/{n_edge} and {pairs[4][0]}/{n_mid} matched the closed form inside [0, 1]; z=2.576 honoured; n=0 refused."
    check("Wilson interval: 7/10, 0/5, 30/30 and fresh edge counts match the closed form and stay inside [0, 1]", wilson)

    def thirty():
        # Thirty cases, mean difference exactly +0.02: three cases at +0.5, three at -0.3, twenty-four unchanged.
        diffs = [Fraction(1, 2)] * 3 + [Fraction(-3, 10)] * 3 + [Fraction(0)] * 24
        rng.shuffle(diffs)
        a, b = scores_of(diffs)
        got = candidate.paired_comparison(a, b)
        require(isinstance(got, dict), "paired_comparison must return a dict")
        mean, variance, se, low, high = paired_expected(diffs)
        require(got.get("verdict") == "inconclusive", f"+2 points on 30 cases: the paired interval [{float(low):.4f}, {float(high):.4f}] contains 0, so the verdict is 'inconclusive', got {got.get('verdict')!r}")
        require(got.get("n") == 30, f"n must be 30, got {got.get('n')!r}")
        close(got.get("mean_diff"), mean, "mean_diff")
        close(got.get("se"), se, "se (sample standard deviation with n - 1, divided by sqrt(n))")
        close(got.get("low"), low, "low")
        close(got.get("high"), high, "high")
        swapped = candidate.paired_comparison(b, a)
        close(swapped.get("mean_diff"), -mean, "swapped mean_diff")
        require(swapped.get("verdict") == "inconclusive", "Swapping the runs keeps the verdict inconclusive")
        return f"Mean +0.02 on 30 cases: SE {float(se):.4f}, interval [{float(low):.4f}, {float(high):.4f}], inconclusive both ways."
    check("Paired comparison: +2 points on 30 cases is inconclusive, not a win", thirty)

    def transfer():
        # The same +0.02 mean difference on 1000 cases: twenty cases at +1, the rest unchanged.
        ids = [f"t{index:04d}" for index in range(1000)]
        rng.shuffle(ids)
        diffs = [Fraction(1)] * 20 + [Fraction(0)] * 980
        rng.shuffle(diffs)
        a, b = scores_of(diffs, ids)
        got = candidate.paired_comparison(a, b)
        mean, variance, se, low, high = paired_expected(diffs)
        require(got.get("verdict") == "better", f"+2 points on 1000 cases with twenty +1 differences: interval [{float(low):.4f}, {float(high):.4f}] excludes 0, verdict 'better', got {got.get('verdict')!r}")
        require(got.get("n") == 1000, f"n must be 1000, got {got.get('n')!r}")
        close(got.get("mean_diff"), mean, "mean_diff")
        close(got.get("se"), se, "se")
        close(got.get("low"), low, "low")
        close(got.get("high"), high, "high")
        swapped = candidate.paired_comparison(b, a)
        require(swapped.get("verdict") == "worse", f"The reverse comparison is 'worse', got {swapped.get('verdict')!r}")
        close(swapped.get("low"), -high, "swapped low")
        return f"Mean +0.02 on 1000 cases: SE {float(se):.5f}, interval [{float(low):.4f}, {float(high):.4f}], better; reversed: worse."
    check("Transfer: the same 2-point difference on 1000 cases with low per-case variance is better, and worse when reversed", transfer)

    def paired_rule():
        # Forty cases: A right on 20, B right on the same 20 plus four more. Unpaired Wilson intervals overlap; paired differences do not.
        ids = [f"p{index:02d}" for index in range(40)]
        rng.shuffle(ids)
        a = {case: 1.0 if index < 20 else 0.0 for index, case in enumerate(ids)}
        b = {case: 1.0 if index < 24 else 0.0 for index, case in enumerate(ids)}
        low_a, high_a = wilson_expected(20, 40)
        low_b, high_b = wilson_expected(24, 40)
        require(low_b < high_a, "fixture: the two unpaired intervals overlap")
        got = candidate.paired_comparison(a, b)
        diffs = [Fraction(int(b[case]) - int(a[case])) for case in ids]
        mean, variance, se, low, high = paired_expected(diffs)
        close(got.get("mean_diff"), mean, "mean_diff")
        close(got.get("se"), se, "se")
        close(got.get("low"), low, "low")
        require(got.get("verdict") == "better", f"A 20/40 [{float(low_a):.3f}, {float(high_a):.3f}] and B 24/40 [{float(low_b):.3f}, {float(high_b):.3f}] overlap, but the paired interval [{float(low):.4f}, {float(high):.4f}] excludes 0: the rule is paired differences, so the verdict is 'better', got {got.get('verdict')!r}")
        # Same mean, different pairing: C is right on 26 but lost four of A's cases and gained ten. The paired interval straddles 0.
        c = {case: 1.0 if 4 <= index < 30 else 0.0 for index, case in enumerate(ids)}
        d = {case: 1.0 if index < 26 else 0.0 for index, case in enumerate(ids)}  # D: right on 26 including every A case
        got_c = candidate.paired_comparison(a, c)
        got_d = candidate.paired_comparison(a, d)
        diffs_c = [Fraction(int(c[case]) - int(a[case])) for case in ids]
        diffs_d = [Fraction(int(d[case]) - int(a[case])) for case in ids]
        _, _, _, low_c, high_c = paired_expected(diffs_c)
        _, _, _, low_d, _ = paired_expected(diffs_d)
        require(low_c < 0 < high_c and low_d > 0, "fixture: C straddles 0, D excludes it")
        require(got_c.get("verdict") == "inconclusive" and got_d.get("verdict") == "better", f"C and D are both right on 26 of 40 (same mean), but C lost four of A's cases: C must be 'inconclusive' and D 'better', got {got_c.get('verdict')!r} and {got_d.get('verdict')!r}. Two means never decide; the per-case differences do")
        return f"Overlapping unpaired intervals, paired verdict better ([{float(low):.4f}, {float(high):.4f}]); same means with and without losses decided differently."
    check("The published rule is paired: overlapping unpaired intervals with consistent paired differences decide better, equal means do not", paired_rule)

    def composed():
        item, other = rng.sample(ITEMS, 2)
        unit, urgency = rng.choice(UNITS), rng.choice(URGENCY)
        references, predictions_a, predictions_b = {}, {}, {}
        # Twelve cases: 9 records, 3 abstain. Baseline right on 5 records + 2 abstain = 7; candidate keeps those and adds 2 records = 9.
        for index in range(1, 13):
            case = f"g{index:02d}"
            if index > 9:
                references[case] = "abstain"
                predictions_a[case] = "abstain" if index < 12 else record(other, 2, unit, "high")
                predictions_b[case] = predictions_a[case]
                continue
            references[case] = record(item if index % 2 else other, index * 3, unit, urgency)
            right = record(references[case]["item"].upper(), str(index * 3), unit, urgency)
            wrong = record(references[case]["item"], index * 3 + 1, unit, urgency)
            predictions_a[case] = right if index <= 5 else wrong
            predictions_b[case] = right if index <= 7 else wrong
        run_a = {"name": "prompt-v2", "predictions": predictions_a, "references": references}
        run_b = {"name": "prompt-v3", "predictions": predictions_b, "references": references}
        got = candidate.report(run_a, run_b)
        require(isinstance(got, dict) and got.get("n") == 12, f"report must carry n=12, got {got.get('n') if isinstance(got, dict) else type(got).__name__!r}")
        scores_a = candidate.case_scores(predictions_a, references)
        scores_b = candidate.case_scores(predictions_b, references)
        wanted_a = {f"g{i:02d}": 1.0 if (i <= 5 or i in (10, 11)) else 0.0 for i in range(1, 13)}
        wanted_b = {f"g{i:02d}": 1.0 if (i <= 7 or i in (10, 11)) else 0.0 for i in range(1, 13)}
        require({k: float(v) for k, v in scores_a.items()} == wanted_a, f"case_scores for the baseline: exact match (all four fields after normalization, or both abstain) scores 1, anything else 0; expected {wanted_a}, got {scores_a}")
        require({k: float(v) for k, v in scores_b.items()} == wanted_b, "case_scores for the candidate must mark exactly g01..g07, g10 and g11 as 1")
        for key, correct, name in (("a", 7, "prompt-v2"), ("b", 9, "prompt-v3")):
            side = got.get(key)
            require(isinstance(side, dict) and side.get("name") == name, f"report[{key!r}] must describe the run named {name!r}")
            accuracy = side.get("accuracy") or {}
            require(accuracy.get("correct") == correct and accuracy.get("n") == 12, f"report[{key!r}]['accuracy'] must be {correct} of 12, got {accuracy!r}")
            close(accuracy.get("mean"), Fraction(correct, 12), f"{key} accuracy mean")
            low, high = wilson_expected(correct, 12)
            close(accuracy.get("low"), low, f"{key} accuracy low")
            close(accuracy.get("high"), high, f"{key} accuracy high")
            abst = side.get("abstention") or {}
            require(abst.get("n") == 3 and abst.get("correct") == 2, f"report[{key!r}]['abstention'] must be 2 of 3, got {abst!r}")
            fields_ = side.get("fields") or {}
            require(set(fields_) == set(FIELDS), f"report[{key!r}]['fields'] must carry the four fields")
            # item: right cases tp; wrong record cases tp (item unchanged); abstain-answered g12 fp; so tp = 9, fp = 1, fn = 0.
            require(fields_["item"].get("tp") == 9 and fields_["item"].get("fp") == 1 and fields_["item"].get("fn") == 0, f"report[{key!r}] item field: expected tp=9 fp=1 fn=0, got {fields_['item']!r}")
            wrong_quantity = 9 - correct + 2
            require(fields_["quantity"].get("tp") == correct - 2 and fields_["quantity"].get("fp") == wrong_quantity + 1 and fields_["quantity"].get("fn") == wrong_quantity, f"report[{key!r}] quantity field: expected tp={correct - 2} fp={wrong_quantity + 1} fn={wrong_quantity}, got {fields_['quantity']!r}")
        diffs = [Fraction(int(wanted_b[c]) - int(wanted_a[c])) for c in sorted(references)]
        mean, variance, se, low, high = paired_expected(diffs)
        paired = got.get("paired") or {}
        close(paired.get("mean_diff"), mean, "report paired mean_diff")
        close(paired.get("se"), se, "report paired se")
        require(paired.get("verdict") == "inconclusive", f"Two more right answers on 12 cases: interval [{float(low):.3f}, {float(high):.3f}], 'inconclusive', got {paired.get('verdict')!r}")
        needed = (Z + Z_POWER) ** 2 * variance / (mean * mean)
        wanted_n = math.ceil(needed)
        needed_got = got.get("needed_n")
        require(isinstance(needed_got, (int, float)) and not isinstance(needed_got, bool) and float(needed_got).is_integer() and abs(int(needed_got) - wanted_n) <= 1, f"needed_n for the observed +{float(mean):.4f} with variance {float(variance):.4f}: ceil((1.96 + 0.8416)^2 * variance / mean^2) = {wanted_n}, got {got.get('needed_n')!r}")
        same = candidate.report(run_a, run_a)
        require((same.get("paired") or {}).get("verdict") == "inconclusive" and same.get("needed_n") is None, "Comparing a run with itself: inconclusive and needed_n null (no observed effect)")
        return f"Report on 12 cases: 7 vs 9 right, Wilson bounds, abstention 2/3, field counts, paired interval [{float(low):.3f}, {float(high):.3f}] inconclusive, needed_n {wanted_n}."
    check("Report composes field scores, abstention, Wilson accuracy intervals, the paired verdict and needed_n", composed)

    def alignment():
        item = rng.choice(ITEMS)
        references = {f"m{i}": record(item, i, "piece", "low") for i in range(1, 7)}
        predictions = {f"m{i}": record(item, i, "piece", "low") for i in range(2, 8)}  # m1 missing, m7 unexpected
        for name, call in (
            ("field_scores", lambda: candidate.field_scores(predictions, references)),
            ("abstention_accuracy", lambda: candidate.abstention_accuracy(predictions, references)),
            ("case_scores", lambda: candidate.case_scores(predictions, references)),
            ("paired_comparison", lambda: candidate.paired_comparison({"m1": 1, "m2": 0, "m3": 1}, {"m1": 1, "m2": 0, "m4": 1})),
            ("paired_comparison with one case", lambda: candidate.paired_comparison({"m1": 1}, {"m1": 0})),
            ("report on different references", lambda: candidate.report({"name": "a", "predictions": references, "references": references}, {"name": "b", "predictions": dict(references, m6="abstain"), "references": dict(references, m6="abstain")})),
        ):
            refused = False
            try:
                call()
            except ValueError:
                refused = True
            except Exception as error:
                raise AssertionError(f"{name} must raise ValueError on misaligned case ids, raised {type(error).__name__}: {error}")
            require(refused, f"{name} must raise ValueError: a case id missing on one side, unexpected on the other, a single case or two different golden sets never produce a number")
        return "Missing, unexpected and single case ids and two different golden sets were refused with ValueError by every function."
    check("Misaligned case ids are rejected: every function raises ValueError instead of scoring what it can", alignment)

    def clustered():
        # Twenty cases from four source documents, five cases each. Within a document the differences move together.
        docs = [f"doc-{rng.randint(10, 99)}-{k}" for k in range(4)]
        pattern = [Fraction(1)] * 5 + [Fraction(1)] * 3 + [Fraction(0)] * 2 + [Fraction(0)] * 10
        ids = [f"k{index:02d}" for index in range(20)]
        groups = [docs[index // 5] for index in range(20)]
        a, b = scores_of(pattern, ids)
        clusters = dict(zip(ids, groups))
        plain = candidate.paired_comparison(a, b)
        got = candidate.paired_comparison(a, b, clusters=clusters)
        mean, se, low, high = clustered_expected(pattern, groups)
        _, _, plain_se, plain_low, _ = paired_expected(pattern)
        require(plain_low > 0 and low < 0 < high, "fixture: plain better, clustered inconclusive")
        require(plain.get("verdict") == "better", "Without clusters the twenty cases decide 'better'")
        close(got.get("mean_diff"), mean, "clustered mean_diff")
        close(got.get("se"), se, "clustered se: sqrt(sum over clusters of (sum of (d_i - mean) in the cluster)^2) / n")
        close(got.get("low"), low, "clustered low")
        close(got.get("high"), high, "clustered high")
        require(got.get("verdict") == "inconclusive", f"With cases clustered by source document the interval [{float(low):.4f}, {float(high):.4f}] includes 0: 'inconclusive', got {got.get('verdict')!r}")
        refused = False
        try:
            candidate.paired_comparison(a, b, clusters={case: docs[0] for case in ids})
        except ValueError:
            refused = True
        require(refused, "A single cluster has no between-cluster variance: fewer than two clusters must raise ValueError")
        return f"Plain SE {float(plain_se):.4f} says better; clustered SE {float(se):.4f} over four documents says inconclusive."
    check("bonus: a clustered standard error when cases share a source document widens the interval", clustered, optional=True)


try:
    trial()
except Exception as error:
    CHECKS.append({"name": "Load metric calculator", "passed": False, "detail": f"{type(error).__name__}: {error}"[:1500]})
print(json.dumps({"checks": CHECKS}))
sys.exit(0 if CHECKS and all(item["passed"] for item in CHECKS if not item.get("optional")) else 1)
