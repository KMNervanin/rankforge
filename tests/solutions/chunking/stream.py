"""Chunker over an explicit word stream per document: every passage owns a half-open word range, every chunk is a slice.

Units (a step together with its attached warning) are computed once; fixed, structural and semantic chunking are three
ways of choosing slice boundaries over the same stream. Metrics are exact Fractions until the report is written.
"""
import math
from fractions import Fraction

STRATEGIES = ("fixed", "structural", "semantic")


def passage_words(passage):
    text = str(passage.get("text") or "")
    warning = passage.get("warning")
    if isinstance(warning, str) and warning.strip():
        text = f"{text}\nWarning: {warning}"
    return text.split()


def is_warning_paragraph(passage):
    return passage.get("kind") == "paragraph" and str(passage.get("text") or "").lstrip().lower().startswith("warning:")


class Document:
    """One document: the ordered passages, their word ranges and the units that must not be cut."""

    def __init__(self, doc_id, passages):
        self.doc_id = doc_id
        self.passages = passages
        self.ranges = []
        self.words = []
        for passage in passages:
            words = passage_words(passage)
            self.ranges.append((len(self.words), len(self.words) + len(words)))
            self.words.extend(words)
        self.units = self._units()

    def _units(self):
        units, index = [], 0
        while index < len(self.passages):
            passage = self.passages[index]
            start, end = self.ranges[index]
            unit = {"start": start, "end": end, "ids": [passage["id"]], "kind": passage.get("kind"), "step_id": None, "warning_id": None}
            if passage.get("kind") == "step":
                if isinstance(passage.get("warning"), str) and passage["warning"].strip():
                    unit["step_id"], unit["warning_id"] = passage["id"], passage["id"]
                elif index + 1 < len(self.passages) and is_warning_paragraph(self.passages[index + 1]):
                    following = self.passages[index + 1]
                    unit["end"] = self.ranges[index + 1][1]
                    unit["ids"].append(following["id"])
                    unit["step_id"], unit["warning_id"] = passage["id"], following["id"]
                    index += 1
            units.append(unit)
            index += 1
        return units

    def covered_ids(self, start, end):
        return [passage["id"] for passage, (lo, hi) in zip(self.passages, self.ranges) if lo < end and hi > start]

    def chunk(self, strategy, start, end, number):
        return {"id": f"{self.doc_id}/{strategy}/{number}", "doc_id": self.doc_id, "strategy": strategy, "start": start, "end": end,
                "text": " ".join(self.words[start:end]), "passage_ids": self.covered_ids(start, end)}


def documents(passages):
    ordered, grouped = [], {}
    for passage in passages:
        doc_id = passage["doc_id"]
        if doc_id not in grouped:
            grouped[doc_id] = []
            ordered.append(doc_id)
        grouped[doc_id].append(passage)
    return [Document(doc_id, grouped[doc_id]) for doc_id in ordered]


def _fixed(document, size, overlap):
    chunks, start, total = [], 0, len(document.words)
    while start < total:
        end = min(start + size, total)
        chunks.append(document.chunk("fixed", start, end, len(chunks)))
        if end >= total:
            break
        start += size - overlap
    return chunks


def _pack(document, strategy, size, cut_before):
    """Greedy packing of units; cut_before(index, open_words) says whether a chunk must close before unit index."""
    chunks, open_start, open_end = [], None, None
    for index, unit in enumerate(document.units):
        length = unit["end"] - unit["start"]
        if open_start is not None and (open_end - open_start + length > size or cut_before(index)):
            chunks.append(document.chunk(strategy, open_start, open_end, len(chunks)))
            open_start = None
        if open_start is None:
            open_start = unit["start"]
        open_end = unit["end"]
    if open_start is not None:
        chunks.append(document.chunk(strategy, open_start, open_end, len(chunks)))
    return chunks


def cosine(left, right):
    dot = sum(a * b for a, b in zip(left, right))
    norm = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
    return dot / norm if norm else 0.0


def chunk(passages, strategy, *, size, overlap=0, embed=None, threshold=0.3):
    if strategy not in STRATEGIES:
        raise ValueError(f"unknown strategy {strategy!r}")
    if not isinstance(size, int) or size < 1:
        raise ValueError("size must be a positive integer")
    if not isinstance(overlap, int) or overlap < 0 or overlap >= size:
        raise ValueError("overlap must satisfy 0 <= overlap < size")
    if strategy == "semantic" and embed is None:
        raise ValueError("semantic chunking needs an embed function")
    chunks = []
    for document in documents(passages):
        if strategy == "fixed":
            chunks.extend(_fixed(document, size, overlap))
        elif strategy == "structural":
            chunks.extend(_pack(document, "structural", size, lambda index: document.units[index]["kind"] == "heading"))
        else:
            texts = [" ".join(document.words[unit["start"]:unit["end"]]) for unit in document.units]
            vectors = embed(texts) if texts else []
            drops = {index for index in range(1, len(texts)) if cosine(vectors[index - 1], vectors[index]) < threshold}
            chunks.extend(_pack(document, "semantic", size, lambda index: index in drops))
    return chunks


def audit(chunks, passages):
    violations = []
    spans = {}
    for item in chunks:
        spans.setdefault(item["doc_id"], []).append((item["start"], item["end"]))
    for document in documents(passages):
        for unit in document.units:
            if unit["warning_id"] is None:
                continue
            if not any(start <= unit["start"] and end >= unit["end"] for start, end in spans.get(document.doc_id, [])):
                violations.append({"doc_id": document.doc_id, "step_id": unit["step_id"], "warning_id": unit["warning_id"]})
    return violations


def _question_metrics(expected, ranking, coverage, k_values):
    expected = set(expected)
    recall, mrr = {}, {}
    for k in k_values:
        top = ranking[:k]
        covered = set()
        first = None
        for rank, chunk_id in enumerate(top, start=1):
            hits = expected & set(coverage.get(chunk_id, []))
            if hits and first is None:
                first = rank
            covered |= hits
        recall[k] = Fraction(len(covered), len(expected)) if expected else Fraction(0)
        mrr[k] = Fraction(1, first) if first else Fraction(0)
    return recall, mrr


def metrics(report):
    k_values = [int(k) for k in report["k_values"]]
    coverage = report["coverage"]
    questions = report["questions"]
    totals = {"recall": {k: Fraction(0) for k in k_values}, "mrr": {k: Fraction(0) for k in k_values}}
    for question in questions:
        recall, mrr = _question_metrics(question["expected"], question["ranking"], coverage, k_values)
        for k in k_values:
            totals["recall"][k] += recall[k]
            totals["mrr"][k] += mrr[k]
    count = len(questions) or 1
    return {name: {str(k): float(value / count) for k, value in table.items()} for name, table in totals.items()}


def evaluate(chunks, questions, embed, k_values):
    k_values = [int(k) for k in k_values]
    chunk_vectors = embed([item["text"] for item in chunks]) if chunks else []
    question_vectors = embed([question["text"] for question in questions]) if questions else []
    rows = []
    for question, vector in zip(questions, question_vectors):
        scored = [(-cosine(vector, chunk_vector), item["id"]) for item, chunk_vector in zip(chunks, chunk_vectors)]
        scored.sort()
        rows.append({"id": question["id"], "expected": list(question["expected"]), "ranking": [chunk_id for _, chunk_id in scored]})
    strategies = {item["strategy"] for item in chunks}
    report = {
        "strategy": strategies.pop() if len(strategies) == 1 else "mixed",
        "k_values": k_values,
        "chunk_count": len(chunks),
        "avg_words": (sum(len(item["text"].split()) for item in chunks) / len(chunks)) if chunks else 0.0,
        "coverage": {item["id"]: list(item["passage_ids"]) for item in chunks},
        "questions": rows,
    }
    report.update(metrics(report))
    return report


def choose(reports, target_recall, *, k):
    key = str(int(k))
    candidates = []
    for report in reports:
        recomputed = metrics(report)
        recall, mrr = recomputed["recall"][key], recomputed["mrr"][key]
        candidates.append({"strategy": report["strategy"], "recall": recall, "mrr": mrr, "chunk_count": int(report["chunk_count"]),
                           "avg_words": float(report["avg_words"]), "meets": recall + 1e-12 >= target_recall})
    meeting = [item for item in candidates if item["meets"]]
    decision = {"strategy": None, "k": int(k), "target_recall": target_recall, "candidates": candidates, "reason": ""}
    if not meeting:
        decision["reason"] = f"no strategy reaches recall@{k} {target_recall}: " + ", ".join(f"{c['strategy']} {c['recall']:.3f}" for c in candidates)
        return decision
    winner = min(meeting, key=lambda item: (item["chunk_count"], item["avg_words"], item["strategy"]))
    decision["strategy"] = winner["strategy"]
    decision["reason"] = (f"{winner['strategy']} reaches recall@{k} {winner['recall']:.3f} (target {target_recall}) with {winner['chunk_count']} chunks "
                          f"of {winner['avg_words']:.1f} words on average, the cheapest among {len(meeting)} meeting the target")
    return decision
