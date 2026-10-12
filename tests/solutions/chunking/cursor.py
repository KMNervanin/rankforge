"""Chunker as a cursor over passage boundaries: passage offsets live in a sorted list, coverage comes from bisect,
chunks are emitted lazily by generators and metrics are plain floats averaged with statistics.fmean.
"""
import bisect
import heapq
import math
import statistics
from itertools import groupby

STRATEGIES = {"fixed", "structural", "semantic"}


def full_text(passage):
    warning = passage.get("warning")
    if isinstance(warning, str) and warning.strip():
        return f"{passage.get('text', '')}\nWarning: {warning}"
    return str(passage.get("text", ""))


def _is_warning(passage):
    return passage.get("kind") == "paragraph" and str(passage.get("text", "")).lstrip()[:8].lower() == "warning:"


def _layout(passages):
    """Word stream, sorted passage start offsets, and the protected units of one document."""
    words, starts, ends = [], [], []
    for passage in passages:
        own = full_text(passage).split()
        starts.append(len(words))
        words.extend(own)
        ends.append(len(words))
    units = []
    skip = False
    for index, passage in enumerate(passages):
        if skip:
            skip = False
            continue
        unit = {"start": starts[index], "end": ends[index], "kind": passage.get("kind"), "ids": [passage["id"]], "pair": None}
        if passage.get("kind") == "step":
            if isinstance(passage.get("warning"), str) and passage["warning"].strip():
                unit["pair"] = (passage["id"], passage["id"])
            elif index + 1 < len(passages) and _is_warning(passages[index + 1]):
                unit["end"] = ends[index + 1]
                unit["ids"].append(passages[index + 1]["id"])
                unit["pair"] = (passage["id"], passages[index + 1]["id"])
                skip = True
        units.append(unit)
    return words, starts, ends, units


def _covered(passages, starts, ends, lo, hi):
    first = bisect.bisect_right(ends, lo)  # first passage ending after lo
    last = bisect.bisect_left(starts, hi)  # passages starting before hi
    return [passages[index]["id"] for index in range(first, last)]


def _emit(doc_id, strategy, passages, words, starts, ends, spans):
    for number, (lo, hi) in enumerate(spans):
        yield {"id": f"{doc_id}/{strategy}/{number}", "doc_id": doc_id, "strategy": strategy, "start": lo, "end": hi,
               "text": " ".join(words[lo:hi]), "passage_ids": _covered(passages, starts, ends, lo, hi)}


def _fixed_spans(total, size, overlap):
    lo = 0
    while lo < total:
        hi = min(lo + size, total)
        yield lo, hi
        if hi == total:
            return
        lo += size - overlap


def _packed_spans(units, size, must_cut):
    lo = hi = None
    for index, unit in enumerate(units):
        if lo is not None and (hi - lo + unit["end"] - unit["start"] > size or must_cut(index)):
            yield lo, hi
            lo = None
        lo = unit["start"] if lo is None else lo
        hi = unit["end"]
    if lo is not None:
        yield lo, hi


def _cos(a, b):
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return sum(x * y for x, y in zip(a, b)) / (na * nb) if na and nb else 0.0


def chunk(passages, strategy, *, size, overlap=0, embed=None, threshold=0.3):
    if strategy not in STRATEGIES:
        raise ValueError(f"strategy must be one of {sorted(STRATEGIES)}")
    if type(size) is not int or size <= 0:
        raise ValueError("size must be a positive integer")
    if type(overlap) is not int or not 0 <= overlap < size:
        raise ValueError("overlap must be an integer in [0, size)")
    if strategy == "semantic" and not callable(embed):
        raise ValueError("semantic chunking requires embed")
    out = []
    for doc_id, group in groupby(passages, key=lambda passage: passage["doc_id"]):
        own = list(group)
        words, starts, ends, units = _layout(own)
        if strategy == "fixed":
            spans = _fixed_spans(len(words), size, overlap)
        elif strategy == "structural":
            spans = _packed_spans(units, size, lambda index: units[index]["kind"] == "heading")
        else:
            vectors = embed([" ".join(words[unit["start"]:unit["end"]]) for unit in units]) if units else []
            similarity = [1.0] + [_cos(vectors[index - 1], vectors[index]) for index in range(1, len(units))]
            spans = _packed_spans(units, size, lambda index: similarity[index] < threshold)
        out.extend(_emit(doc_id, strategy, own, words, starts, ends, spans))
    return out


def audit(chunks, passages):
    spans = {}
    for item in chunks:
        spans.setdefault(item["doc_id"], []).append((item["start"], item["end"]))
    for doc_spans in spans.values():
        doc_spans.sort()
    violations = []
    for doc_id, group in groupby(passages, key=lambda passage: passage["doc_id"]):
        _, _, _, units = _layout(list(group))
        own = spans.get(doc_id, [])
        for unit in units:
            if unit["pair"] is None:
                continue
            # Every candidate chunk starts at or before the unit: scan those and look for one reaching its end.
            cut = bisect.bisect_right(own, (unit["start"], float("inf")))
            if not any(hi >= unit["end"] for _, hi in own[:cut]):
                violations.append({"doc_id": doc_id, "step_id": unit["pair"][0], "warning_id": unit["pair"][1]})
    return violations


def _per_question(expected, ranking, coverage, k):
    wanted = set(expected)
    if not wanted:
        return 0.0, 0.0
    seen, first = set(), 0
    for rank, chunk_id in enumerate(ranking[:k], 1):
        overlap = wanted.intersection(coverage.get(chunk_id, ()))
        if overlap and not first:
            first = rank
        seen.update(overlap)
    return len(seen) / len(wanted), (1.0 / first if first else 0.0)


def metrics(report):
    ks = [int(k) for k in report["k_values"]]
    rows = report["questions"]
    coverage = report["coverage"]
    recall, mrr = {}, {}
    for k in ks:
        pairs = [_per_question(row["expected"], row["ranking"], coverage, k) for row in rows]
        recall[str(k)] = statistics.fmean(pair[0] for pair in pairs) if pairs else 0.0
        mrr[str(k)] = statistics.fmean(pair[1] for pair in pairs) if pairs else 0.0
    return {"recall": recall, "mrr": mrr}


def evaluate(chunks, questions, embed, k_values):
    ks = [int(k) for k in k_values]
    vectors = embed([item["text"] for item in chunks] + [question["text"] for question in questions])
    chunk_vectors, question_vectors = vectors[:len(chunks)], vectors[len(chunks):]
    rows = []
    for question, vector in zip(questions, question_vectors):
        heap = [(-_cos(vector, cv), item["id"]) for item, cv in zip(chunks, chunk_vectors)]
        heapq.heapify(heap)
        ranking = [heapq.heappop(heap)[1] for _ in range(len(heap))]
        rows.append({"id": question["id"], "expected": list(question["expected"]), "ranking": ranking})
    names = sorted({item["strategy"] for item in chunks})
    report = {
        "strategy": names[0] if len(names) == 1 else "+".join(names),
        "k_values": ks,
        "chunk_count": len(chunks),
        "avg_words": statistics.fmean(len(item["text"].split()) for item in chunks) if chunks else 0.0,
        "coverage": {item["id"]: list(item["passage_ids"]) for item in chunks},
        "questions": rows,
    }
    report.update(metrics(report))
    return report


def choose(reports, target_recall, *, k):
    column = str(int(k))
    candidates = []
    for report in reports:
        fresh = metrics(report)
        recall = fresh["recall"][column]
        candidates.append({"strategy": report["strategy"], "recall": recall, "mrr": fresh["mrr"][column], "chunk_count": int(report["chunk_count"]),
                           "avg_words": float(report["avg_words"]), "meets": math.isclose(recall, target_recall, abs_tol=1e-9) or recall > target_recall})
    ranked = sorted((item for item in candidates if item["meets"]), key=lambda item: (item["chunk_count"], item["avg_words"], item["strategy"]))
    if not ranked:
        cited = "; ".join(f"{item['strategy']} recall@{k}={item['recall']:.3f}" for item in candidates)
        return {"strategy": None, "k": int(k), "target_recall": target_recall, "candidates": candidates, "reason": f"no strategy meets recall@{k} >= {target_recall}: {cited}"}
    best = ranked[0]
    reason = f"{best['strategy']}: recall@{k} {best['recall']:.3f} >= {target_recall}, {best['chunk_count']} chunks averaging {best['avg_words']:.1f} words; cheapest of {len(ranked)} that meet the target"
    return {"strategy": best["strategy"], "k": int(k), "target_recall": target_recall, "candidates": candidates, "reason": reason}
