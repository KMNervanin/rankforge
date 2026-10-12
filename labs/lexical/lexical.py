"""Lexical and dense retrieval over the archive, compared per query type.

Starter: an FTS5 index with the default tokenizer, a dense search by cosine over injected vectors
and a report with one average per retriever. See LEARN.md for the complete contract Verify checks.
"""
import math
import re
import sqlite3

# Formats the archive must find exactly. The tokenizer below does not use them yet.
CODE_PATTERNS = [r"[A-Z]{2,4}-\d{2,4}[A-Z]?", r"E\d{4}"]


def tokenize(text, *, code_patterns=CODE_PATTERNS):
    return re.findall(r"[a-z0-9]+", text.lower())


def build_index(passages, path, *, code_patterns=CODE_PATTERNS):
    connection = sqlite3.connect(path)
    try:
        with connection:
            connection.execute("DROP TABLE IF EXISTS passages")
            connection.execute("CREATE VIRTUAL TABLE passages USING fts5(id UNINDEXED, text)")
            connection.executemany("INSERT INTO passages(id, text) VALUES (?, ?)", [(passage["id"], passage["text"]) for passage in passages])
        return len(passages)
    finally:
        connection.close()


def search_lexical(path, query, k):
    tokens = tokenize(query)
    if not tokens:
        return []
    match = " OR ".join(f'"{token}"' for token in tokens)
    connection = sqlite3.connect(path)
    try:
        rows = connection.execute("SELECT id FROM passages WHERE passages MATCH ? ORDER BY rank DESC LIMIT ?", (match, k)).fetchall()
    finally:
        connection.close()
    return [pid for (pid,) in rows]


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def search_dense(path, query, k, embed):
    connection = sqlite3.connect(path)
    try:
        rows = connection.execute("SELECT id, text FROM passages").fetchall()
    finally:
        connection.close()
    vector = embed(query)
    scored = sorted(((pid, cosine(vector, embed(text))) for pid, text in rows), key=lambda item: (-item[1], item[0]))
    return [pid for pid, _ in scored[:k]]


def evaluate(path, queries, k, embed):
    entries = []
    for query in queries:
        lexical = search_lexical(path, query["query"], k)
        dense = search_dense(path, query["query"], k, embed)
        hits = lambda ranked: len(set(query["expected"]) & set(ranked)) / len(query["expected"])
        entries.append({"id": query["id"], "query": query["query"], "lexical": lexical, "dense": dense, "lexical_recall": hits(lexical), "dense_recall": hits(dense)})
    return {
        "k": k,
        "queries": entries,
        "lexical_recall": sum(entry["lexical_recall"] for entry in entries) / len(entries),
        "dense_recall": sum(entry["dense_recall"] for entry in entries) / len(entries),
    }


def compare(report):
    if report["lexical_recall"] > report["dense_recall"]:
        return "lexical"
    if report["lexical_recall"] < report["dense_recall"]:
        return "dense"
    return "tie"
