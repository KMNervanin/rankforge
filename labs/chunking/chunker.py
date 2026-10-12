"""Chunker and retrieval report for the outpost archive.

Passages come from the extraction step: every passage has id, doc_id, kind (heading, step, paragraph), text and
sometimes a warning attached to a step. Questions carry the ids of the passages that answer them.
"""
import math


def chunk(passages, strategy, *, size, overlap=0, embed=None, threshold=0.3):
    """Cut every document into chunks of roughly `size` words. The strategy name is recorded on each chunk."""
    chunks = []
    documents = {}
    for passage in passages:
        documents.setdefault(passage["doc_id"], []).append(passage)
    for doc_id, items in documents.items():
        text = " ".join(item["text"] for item in items)
        width = size * 5  # about five characters per word
        position = 0
        number = 0
        consumed = 0
        while position < len(text):
            piece = text[position:position + width]
            words = piece.split()
            start = consumed
            consumed += len(words)
            covered = [item["id"] for item in items if any(word in item["text"] for word in words[:3])]
            chunks.append({"id": f"{doc_id}/{strategy}/{number}", "doc_id": doc_id, "strategy": strategy, "start": start, "end": consumed,
                           "text": piece.strip(), "passage_ids": covered})
            position += width
            number += 1
    return chunks


def audit(chunks, passages):
    """Report a step whose warning is not in the same chunk."""
    violations = []
    for passage in passages:
        if passage.get("kind") != "step" or not passage.get("warning"):
            continue
        together = [item for item in chunks if passage["id"] in item["passage_ids"]]
        if not together:
            violations.append({"doc_id": passage["doc_id"], "step_id": passage["id"], "warning_id": passage["id"]})
    return violations


def cosine(left, right):
    dot = sum(a * b for a, b in zip(left, right))
    norm = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
    return dot / norm if norm else 0.0


def evaluate(chunks, questions, embed, k_values):
    """Rank every chunk for every question by cosine similarity and aggregate recall and MRR."""
    chunk_vectors = embed([item["text"] for item in chunks])
    question_vectors = embed([question["text"] for question in questions])
    rows = []
    hits = {k: 0 for k in k_values}
    reciprocal = []
    for question, vector in zip(questions, question_vectors):
        scores = sorted(((cosine(vector, cv), item["id"]) for item, cv in zip(chunks, chunk_vectors)), reverse=True)
        ranking = [chunk_id for _, chunk_id in scores]
        coverage = {item["id"]: item["passage_ids"] for item in chunks}
        first = 0
        for rank, chunk_id in enumerate(ranking, start=1):
            if set(coverage[chunk_id]) & set(question["expected"]):
                first = rank
                break
        for k in k_values:
            if first and first <= k:
                hits[k] += 1
        reciprocal.append(1 / first if first else 0.0)
        rows.append({"id": question["id"], "expected": list(question["expected"]), "ranking": ranking, "first_hit": first})
    count = len(questions) or 1
    return {
        "strategy": chunks[0]["strategy"] if chunks else "none",
        "k_values": list(k_values),
        "chunk_count": len(chunks),
        "avg_words": sum(len(item["text"].split()) for item in chunks) / (len(chunks) or 1),
        "coverage": {item["id"]: list(item["passage_ids"]) for item in chunks},
        "questions": rows,
        "hits": {str(k): hits[k] for k in k_values},
        "recall": {str(k): hits[k] / count for k in k_values},
        "mrr": {str(k): sum(reciprocal) / count for k in k_values},
    }


def metrics(report):
    """The aggregates of a report."""
    return {"recall": dict(report["recall"]), "mrr": dict(report["mrr"])}


def choose(reports, target_recall, *, k):
    """Pick the strategy with the best recall at k."""
    column = str(k)
    candidates = [{"strategy": report["strategy"], "recall": report["recall"][column], "mrr": report["mrr"][column],
                   "chunk_count": report["chunk_count"], "avg_words": report["avg_words"], "meets": report["recall"][column] >= target_recall}
                  for report in reports]
    best = max(candidates, key=lambda item: item["recall"])
    return {"strategy": best["strategy"], "k": k, "target_recall": target_recall, "candidates": candidates,
            "reason": f"{best['strategy']} has the highest recall@{k} ({best['recall']:.3f})"}
