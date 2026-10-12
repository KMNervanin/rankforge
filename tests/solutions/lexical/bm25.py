"""Lexical versus dense retrieval: BM25 computed by hand over an inverted index in plain SQLite tables.

Reference solution B. No FTS5: build_index writes a postings table, search_lexical scores with the
published formula (k1 = 1.2, b = 0.75, FTS5's idf with the positive clamp) and sorts by score
descending, id ascending. Dense search, the report and compare follow the same contract.
"""
import json
import math
import re
import sqlite3
from collections import Counter

CODE_PATTERNS = [r"[A-Z]{2,4}-\d{2,4}[A-Z]?", r"E\d{4}"]
K1, B = 1.2, 0.75
WORD = re.compile(r"[^\W_]+")


def tokenize(text, *, code_patterns=CODE_PATTERNS):
    if not code_patterns:
        return [word.lower() for word in WORD.findall(text)]
    matcher = re.compile("|".join(f"(?<![^\\W_])(?:{pattern})(?![^\\W_])" for pattern in code_patterns), re.IGNORECASE)
    tokens, position = [], 0
    for match in matcher.finditer(text):
        tokens.extend(word.lower() for word in WORD.findall(text[position:match.start()]))
        tokens.append(match.group(0).lower())
        position = match.end()
    tokens.extend(word.lower() for word in WORD.findall(text[position:]))
    return tokens


def build_index(passages, path, *, code_patterns=CODE_PATTERNS):
    patterns = list(code_patterns)
    connection = sqlite3.connect(path)
    try:
        with connection:
            for table in ("postings", "passages", "meta"):
                connection.execute(f"DROP TABLE IF EXISTS {table}")
            connection.execute("CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            connection.execute("CREATE TABLE passages(id TEXT PRIMARY KEY, text TEXT NOT NULL, length INTEGER NOT NULL)")
            connection.execute("CREATE TABLE postings(term TEXT NOT NULL, id TEXT NOT NULL, tf INTEGER NOT NULL, PRIMARY KEY (term, id))")
            connection.execute("INSERT INTO meta VALUES ('code_patterns', ?)", (json.dumps(patterns),))
            for passage in passages:
                tokens = tokenize(passage["text"], code_patterns=patterns)
                connection.execute("INSERT INTO passages VALUES (?, ?, ?)", (str(passage["id"]), passage["text"], len(tokens)))
                connection.executemany("INSERT INTO postings VALUES (?, ?, ?)", [(term, str(passage["id"]), tf) for term, tf in Counter(tokens).items()])
        return len(passages)
    finally:
        connection.close()


def _scored_lexical(path, query, k):
    connection = sqlite3.connect(path)
    try:
        patterns = json.loads(connection.execute("SELECT value FROM meta WHERE key = 'code_patterns'").fetchone()[0])
        terms = list(dict.fromkeys(tokenize(query, code_patterns=patterns)))
        if not terms:
            return []
        total, average = connection.execute("SELECT COUNT(*), AVG(length) FROM passages").fetchone()
        lengths = dict(connection.execute("SELECT id, length FROM passages").fetchall())
        scores = {}
        for term in terms:
            rows = connection.execute("SELECT id, tf FROM postings WHERE term = ?", (term,)).fetchall()
            if not rows:
                continue
            idf = math.log((total - len(rows) + 0.5) / (len(rows) + 0.5))
            if idf <= 0.0:
                idf = 1e-6
            for pid, tf in rows:
                part = idf * tf * (K1 + 1) / (tf + K1 * (1 - B + B * lengths[pid] / average))
                scores[pid] = scores.get(pid, 0.0) + part
        ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
        return ranked[:k]
    finally:
        connection.close()


def search_lexical(path, query, k):
    return [pid for pid, _ in _scored_lexical(path, query, k)]


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0


def _scored_dense(path, query, k, embed):
    connection = sqlite3.connect(path)
    try:
        rows = connection.execute("SELECT id, text FROM passages ORDER BY id").fetchall()
    finally:
        connection.close()
    vector = embed(query)
    ranked = sorted(((pid, cosine(vector, embed(text))) for pid, text in rows), key=lambda item: (-item[1], item[0]))
    return ranked[:k]


def search_dense(path, query, k, embed):
    return [pid for pid, _ in _scored_dense(path, query, k, embed)]


def _normalize(pairs):
    if not pairs:
        return []
    top, bottom = max(score for _, score in pairs), min(score for _, score in pairs)
    return [[pid, 1.0 if top == bottom else (score - bottom) / (top - bottom)] for pid, score in pairs]


def _recall(expected, ranked):
    wanted = set(expected)
    if not wanted:
        raise ValueError("a query needs at least one expected passage id")
    return len(wanted & set(ranked)) / len(wanted)


def _mean(entries, key):
    return sum(entry[key] for entry in entries) / len(entries) if entries else 0.0


def evaluate(path, queries, k, embed):
    entries = []
    for query in queries:
        lexical = _scored_lexical(path, query["query"], k)
        dense = _scored_dense(path, query["query"], k, embed)
        expected = [str(pid) for pid in query["expected"]]
        entry = {"id": query["id"], "category": query["category"], "query": query["query"], "expected": expected,
                 "lexical": [pid for pid, _ in lexical], "dense": [pid for pid, _ in dense]}
        entry["lexical_recall"] = _recall(expected, entry["lexical"])
        entry["dense_recall"] = _recall(expected, entry["dense"])
        entry["lexical_scored"] = _normalize(lexical)
        entry["dense_scored"] = _normalize(dense)
        entries.append(entry)
    names = list(dict.fromkeys(entry["category"] for entry in entries))
    categories = {}
    for name in names:
        group = [entry for entry in entries if entry["category"] == name]
        categories[name] = {"queries": len(group), "lexical_recall": _mean(group, "lexical_recall"), "dense_recall": _mean(group, "dense_recall")}
    overall = {"queries": len(entries), "lexical_recall": _mean(entries, "lexical_recall"), "dense_recall": _mean(entries, "dense_recall")}
    return {"k": k, "queries": entries, "categories": categories, "overall": overall}


def compare(report):
    verdict = {}
    for name, summary in report["categories"].items():
        lexical, dense = summary["lexical_recall"], summary["dense_recall"]
        if abs(lexical - dense) <= 1e-9:
            verdict[name] = "tie"
        else:
            verdict[name] = "lexical" if lexical > dense else "dense"
    return verdict
