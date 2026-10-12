# Field manual — words still matter

The archive answers from runbooks and incident reports, and the operator asks in two voices: "what does E0417 mean" and "how do I bring the relay back after an outage". The starter has one FTS5 index whose tokenizer cuts `FLT-220A` into `flt` and `220a`, sorts the matches worst-first and reports one average recall for each retriever, so nobody can see that the lexical side wins on codes and loses on paraphrases. That is the deliberate defect.

## Workshop and entry point

Python 3.10 or later, standard library only; SQLite with FTS5 is the intended index, and `python3 -c "import sqlite3; sqlite3.connect(':memory:').execute('create virtual table t using fts5(x)')"` tells you whether your build has it (python.org and Homebrew builds do; Verify reports **Environment blocked** when it is missing). Edit `lexical.py` and keep seven names importable: `CODE_PATTERNS`, `tokenize`, `build_index`, `search_lexical`, `search_dense`, `evaluate` and `compare`. Verify imports your module, builds an index from its own passages with fresh codes, searches it, reads the report `evaluate` returns and reopens the index file from a separate Python process.

`python3 -B demo.py` builds `archive.sqlite` from `passages.json`, runs `queries.json` through both retrievers and prints the report with the winner per category. `python3 -B demo.py "flt-220a"` shows the tokens and both rankings for one query. There is no live call in this mission: the dense side receives an `embed` function from the caller, and the demo's one is a stand-in (a hashed bag of words with a tiny thesaurus, normalized). Verify injects its own stand-in of the same kind; it is a labeled test tool, not a model.

## The problem

Dense retrieval compares meanings: "power dip" lands near "brownout" because the embedding model saw them in the same contexts. It is also why a dense index is poor at `FLT-220A`: a part number has no meaning to average, and most models shred it into sub-word pieces shared with hundreds of other codes. Lexical retrieval compares tokens, and BM25 ranks a passage by how many query tokens it contains, how often, how rare they are across the corpus and how long the passage is (Robertson's k1 = 1.2 and b = 0.75 are the published defaults). It cannot know that "outage" is "brownout", but it never confuses `FLT-220A` with `FLT-220B`, provided the tokenizer keeps the code whole.

SQLite ships this as FTS5: a virtual table whose `bm25()` function returns a **negative** number where **lower is better**, and whose hidden `rank` column sorts ascending to put the best match first. PostgreSQL's `ts_rank` and `ts_rank_cd` are not BM25 (frequency and cover density, no length normalization by the same rule); BM25 there needs an extension or your own scoring. The comparison only means something per query type: one aggregate number averages the strength of one retriever against the strength of the other and hides both.

## Complete public contract

```python
CODE_PATTERNS: list[str]                                   # regular expressions, one per code format
tokenize(text, *, code_patterns=CODE_PATTERNS) -> list[str]
build_index(passages, path, *, code_patterns=CODE_PATTERNS) -> int
search_lexical(path, query, k) -> list[str]
search_dense(path, query, k, embed) -> list[str]
evaluate(path, queries, k, embed) -> dict
compare(report) -> dict
```

A passage is `{"id": str, "text": str}`; ids are unique. A query is `{"id": str, "category": str, "query": str, "expected": [ids]}` with at least one expected id. `embed(text)` returns a list of floats of one fixed length for any text; a text without content may embed to the zero vector.

1. **Tokens.** `tokenize` scans the text left to right. At each position the patterns are tried in list order, case-insensitively, and a match counts only when the character before and after it is not a letter or digit; the matched span becomes **one** token, lowercased. Everything between matches splits into maximal runs of letters and digits, lowercased. No stemming, no stop words: `gasket` and `gaskets` are different tokens, `flt-220a` is one token and `FLT-220A` is the same token. `tokenize("Replace FLT-220A before E0417 recurs.")` is `["replace", "flt-220a", "before", "e0417", "recurs"]`; `kit 220A` gives `["kit", "220a"]` because `220A` alone matches no pattern. The published list is `[r"[A-Z]{2,4}-\d{2,4}[A-Z]?", r"E\d{4}"]`; a new code format such as `RB/7731-K` is one more entry, `r"[A-Z]{2}/\d{4}-[A-Z]"`, and nothing else changes.
2. **Index.** `build_index` creates or replaces the index at `path` (a SQLite file; FTS5 or your own tables) over `tokenize(text, code_patterns=…)` of every passage, stores the pattern list next to it and returns the passage count. `search_lexical` tokenizes the query with the **stored** patterns, so a search needs no patterns of its own and a fresh process that opens the file answers the same rankings. With FTS5, store the tokens joined by spaces in a column whose tokenizer keeps the code characters (`tokenize="unicode61 tokenchars '-/'"`), and query with each token in double quotes joined by `OR`: a bare `flt-220a` is a syntax error in the MATCH grammar and `"flt-220a"` without `tokenchars` is split again.
3. **Lexical ranking.** A passage matches when it contains **any** token of the query (BM25's usual disjunction; FTS5's implicit `AND` is not it). The result is the matching passages by BM25 score, best first, at most `k`, ties on the lower id (`ORDER BY rank, id` in FTS5; FTS5's `bm25()` is the negated score). With k1 = 1.2 and b = 0.75 a passage that holds the term four times in twelve tokens outranks one that holds it once in twenty, which outranks one that holds it once in thirty-five. A query with no tokens returns `[]`. Note that the passage length is its token count, so adding a pattern shortens every passage that carries the new format and can move it for other queries; queries that touch no such passage are unchanged.
4. **Dense ranking.** `search_dense` embeds the query and every stored passage text with `embed`, scores each by cosine (dot product over both lengths, `0.0` when either length is zero) and returns the best `k` ids, ties on the lower id. Verify recomputes every dense ranking from the same vectors exactly.
5. **Report.** `evaluate` runs both searches for every query and returns `{"k", "queries", "categories", "overall"}`. Each entry of `queries` is, in input order: `id`, `category`, `query`, `expected` (verbatim), `lexical` and `dense` (the ranked ids, at most `k`), `lexical_recall` and `dense_recall`. Recall@k of one query is `|expected ∩ ranked| / |expected|`. `categories` maps every category present to `{"queries": n, "lexical_recall", "dense_recall"}`, each recall the mean over that category's queries; `overall` has the same keys over all queries. Verify recomputes every number with exact fractions from the rankings in the entries, tolerance 1e-9, and rejects a report whose categories are missing or merged: part numbers and error codes (`exact_code`), paraphrases and synonyms are read separately.
6. **Verdict.** `compare(report)` returns, for every key of `report["categories"]`, `"lexical"` when its `lexical_recall` is higher, `"dense"` when lower, `"tie"` when equal within 1e-9. It reads the report, not the index.

Optional keys in a query entry are allowed. For the next mission, which fuses two rankings, `lexical_scored` and `dense_scored` hold `[[id, score], …]` in ranking order with scores min-max normalized within that list: the best is `1.0`, the worst `0.0`, every score `1.0` when all are equal.

## What Verify runs

- Builds an index from thirteen fresh passages whose codes change on every run (`FLT-…`, `E0…`, `RB/…-…`), with decoys that carry the pieces of each code as separate words.
- Checks `tokenize` on those codes in both casings and with an extra pattern, then exact-code queries (only the passage carrying the code may come back), the ordering on `fuse` and `spare gaskets` (hand-derived from term frequency and length), four dense rankings against its own cosines including an exact tie and a zero query vector, the report's per-category and overall recall with `Fraction`, `compare` on the report and on a hand-built report with a tie, the transfer with `RB/…` stored in a second index, and a separate Python process reopening both files.
- No model is called. Expect the dense side to score zero on exact codes with Verify's vectors, which drop anything containing a digit: that is the point of the mission, not a defect of yours.

Two different implementations pass: an FTS5 virtual table with `bm25()` and a hand-written BM25 over a postings table in plain SQLite both satisfy the contract.

## Sources

- SQLite FTS5: `bm25()` returns lower-is-better values, the hidden `rank` column, the `unicode61` tokenizer and its `tokenchars` option, the MATCH grammar with quoted strings and `OR`.
- Robertson and Zaragoza, "The Probabilistic Relevance Framework: BM25 and Beyond" (2009): the formula with k1 and b.
- PostgreSQL 18 "Controlling Text Search": `ts_rank` and `ts_rank_cd` are frequency and cover-density rankings, not BM25.
- Sentence-Transformers, "Retrieve & Re-Rank": lexical search as the complement of dense retrieval for exact terms.
