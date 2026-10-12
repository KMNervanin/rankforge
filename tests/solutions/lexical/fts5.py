"""Lexical versus dense retrieval: SQLite FTS5 with a code-preserving tokenizer, bm25() ascending.

Reference solution A. The index is an FTS5 virtual table over pre-tokenized text; the tokenizer
keeps part numbers and error codes as single tokens; the ranking is ORDER BY rank (lower bm25 is
better) with ties on the lower id; the report carries per-category recall@k and normalized scores.
"""
import json
import math
import re
import sqlite3

CODE_PATTERNS = [r"[A-Z]{2,4}-\d{2,4}[A-Z]?", r"E\d{4}"]
WORD = re.compile(r"[^\W_]+")
TOKENCHARS = "-/.:#_"


def _matcher(code_patterns):
    if not code_patterns:
        return None
    return re.compile("|".join(f"(?<![^\\W_])(?:{pattern})(?![^\\W_])" for pattern in code_patterns), re.IGNORECASE)


def tokenize(text, *, code_patterns=CODE_PATTERNS):
    matcher = _matcher(code_patterns)
    tokens, position = [], 0
    for match in (matcher.finditer(text) if matcher else ()):
        tokens.extend(word.lower() for word in WORD.findall(text[position:match.start()]))
        tokens.append(match.group(0).lower())
        position = match.end()
    tokens.extend(word.lower() for word in WORD.findall(text[position:]))
    return tokens


def _connect(path):
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA journal_mode=MEMORY")
    return connection


def build_index(passages, path, *, code_patterns=CODE_PATTERNS):
    patterns = list(code_patterns)
    connection = _connect(path)
    try:
        with connection:
            connection.execute("DROP TABLE IF EXISTS passages")
            connection.execute("DROP TABLE IF EXISTS meta")
            connection.execute(f"CREATE VIRTUAL TABLE passages USING fts5(id UNINDEXED, body, text UNINDEXED, tokenize=\"unicode61 tokenchars '{TOKENCHARS}'\")")
            connection.execute("CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            connection.execute("INSERT INTO meta VALUES ('code_patterns', ?)", (json.dumps(patterns),))
            rows = [(str(passage["id"]), " ".join(tokenize(passage["text"], code_patterns=patterns)), passage["text"]) for passage in passages]
            connection.executemany("INSERT INTO passages(id, body, text) VALUES (?, ?, ?)", rows)
        return len(rows)
    finally:
        connection.close()


def _patterns(connection):
    row = connection.execute("SELECT value FROM meta WHERE key = 'code_patterns'").fetchone()
    return json.loads(row[0]) if row else list(CODE_PATTERNS)


def _lexical_scored(path, query, k):
    connection = _connect(path)
    try:
        tokens = tokenize(query, code_patterns=_patterns(connection))
        if not tokens:
            return []
        match = " OR ".join('"' + token.replace('"', '""') + '"' for token in dict.fromkeys(tokens))
        rows = connection.execute("SELECT id, bm25(passages) FROM passages WHERE passages MATCH ? ORDER BY rank, id LIMIT ?", (match, k)).fetchall()
        return [(pid, -rank) for pid, rank in rows]
    finally:
        connection.close()


def search_lexical(path, query, k):
    return [pid for pid, _ in _lexical_scored(path, query, k)]


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _dense_scored(path, query, k, embed):
    connection = _connect(path)
    try:
        rows = connection.execute("SELECT id, text FROM passages").fetchall()
    finally:
        connection.close()
    vector = embed(query)
    scored = [(pid, cosine(vector, embed(text))) for pid, text in rows]
    scored.sort(key=lambda item: (-item[1], item[0]))
    return scored[:k]


def search_dense(path, query, k, embed):
    return [pid for pid, _ in _dense_scored(path, query, k, embed)]


def _normalized(scored):
    if not scored:
        return []
    values = [score for _, score in scored]
    top, bottom = max(values), min(values)
    if top == bottom:
        return [[pid, 1.0] for pid, _ in scored]
    return [[pid, (score - bottom) / (top - bottom)] for pid, score in scored]


def _recall(expected, ranked):
    if not expected:
        raise ValueError("every query needs at least one expected passage id")
    return len(set(expected) & set(ranked)) / len(set(expected))


def _summary(entries):
    return {
        "queries": len(entries),
        "lexical_recall": sum(entry["lexical_recall"] for entry in entries) / len(entries) if entries else 0.0,
        "dense_recall": sum(entry["dense_recall"] for entry in entries) / len(entries) if entries else 0.0,
    }


def evaluate(path, queries, k, embed):
    entries = []
    for query in queries:
        lexical = _lexical_scored(path, query["query"], k)
        dense = _dense_scored(path, query["query"], k, embed)
        expected = [str(pid) for pid in query["expected"]]
        entries.append({
            "id": query["id"], "category": query["category"], "query": query["query"], "expected": expected,
            "lexical": [pid for pid, _ in lexical], "dense": [pid for pid, _ in dense],
            "lexical_recall": _recall(expected, [pid for pid, _ in lexical]), "dense_recall": _recall(expected, [pid for pid, _ in dense]),
            "lexical_scored": _normalized(lexical), "dense_scored": _normalized(dense),
        })
    categories = {}
    for entry in entries:
        categories.setdefault(entry["category"], []).append(entry)
    return {
        "k": k, "queries": entries,
        "categories": {name: _summary(group) for name, group in categories.items()},
        "overall": _summary(entries),
    }


def compare(report):
    verdict = {}
    for name, summary in report["categories"].items():
        gap = summary["lexical_recall"] - summary["dense_recall"]
        verdict[name] = "tie" if abs(gap) <= 1e-9 else ("lexical" if gap > 0 else "dense")
    return verdict
