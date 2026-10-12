# Field manual — the archive changes

The archive's search works until the archive moves: a runbook is revised, an incident report is withdrawn, the relay gets a better embedding model. The starter re-embeds the revised runbook next to its old chunks, deletes a document's row but keeps its chunks searchable, and rebuilds by dropping the live table under the operator's feet. That is the deliberate defect: yesterday's runbook is still cited.

## Workshop and entry point

Python 3.10 or later, standard library only; SQLite is the store. Edit `indexer.py` and keep two names importable: the class `Indexer` and the function `chunk`. Verify imports your module, constructs an `Indexer` on a SQLite file it owns, injects its own embedding function, drives the archive through updates, a deletion, a model migration and a chunking change, and reads the file from its own connection between calls. `documents.json` is a sample archive for your own runs; Verify carries its own documents, codes and file.

`python3 -B demo.py` runs the whole scenario on `archive.sqlite` with a local hashed embedding (a test tool, never a model) and prints every step. `python3 -B demo.py --model relay-embed-b` migrates to another model name; `python3 -B demo.py --chunking 2` changes the chunking. There is no live call in this mission: the embedding function is always injected.

## The problem

A vector index is a derived view of the documents. When a document changes, every chunk derived from the old text is wrong, and search has no way to know that unless the index carries the document version with every chunk. When the embedding model changes, every vector is wrong at once, and the only safe path is to build a complete second index while the first keeps serving, then switch in one step that can be undone. PostgreSQL does this with build-then-rename: `ALTER INDEX … RENAME` runs inside a transaction, so the swap is atomic; a `CREATE INDEX CONCURRENTLY` build cannot run inside a transaction block, so the build and the swap are separate steps by design. SQLite has the same shape: a table rename, an `UPDATE` of a pointer row or both are transactional, while the long build happens outside the swap.

Worked example. Three documents, chunking version 1 (one passage per chunk), model A. RB-power has three passages, so the index holds chunks (RB-power, 1, 0..2). The operator revises RB-power to two passages: the document moves to version 2 and the index gains (RB-power, 2, 0..1) in the same transaction that records version 2. A search now reaches only version 2: the three old chunks are stale, unreachable, and counted as such. Then `rebuild(embed_model="B")` creates a second index version holding every current document under model B; it is not active, so searches still use A. `switch` makes it active in one transaction, `rollback` makes A active again, and neither call embeds anything.

## Complete public contract

```python
chunk(content, chunking_version) -> list[str]
Indexer(path, *, embed, embed_model="relay-embed-a", chunking_version=1)
    .upsert(doc) -> dict            # doc = {"doc_id": str, "content": str}
    .delete(doc_id) -> bool
    .search(query, k, *, version=None) -> list[dict]
    .rebuild(*, embed_model=None, chunking_version=None) -> str
    .switch(version) -> None
    .rollback() -> str
    .audit() -> dict
    .close() -> None
```

`embed(texts, *, model)` is injected: it takes a list of strings and the model name as a keyword argument and returns one vector per text, in order. It is deterministic per model name, so a different model name means a different vector for the same text. Verify counts every call and every text. Batch as you like; the counts below are totals of texts.

1. **Chunking rule.** `chunk(content, v)` splits the content at blank lines (`re.split(r"\n\s*\n", content.strip())`), strips each passage, drops empty ones and joins `v` consecutive passages with one blank line per chunk, so a document with P passages has `ceil(P / v)` chunks numbered `chunk_no` 0, 1, 2 … in order. A document with no passage is refused with `ValueError`. `v` is a positive integer.
2. **Documents are versioned.** The table `documents` has `doc_id TEXT PRIMARY KEY`, `version INTEGER` and `content_hash TEXT` (the SHA-256 hex digest of the UTF-8 content); extra columns are yours. A new document gets version 1. `upsert` of content whose hash equals the stored one makes **zero** embed calls and returns `{"doc_id", "version", "changed": False, "chunks"}` with the current counts. Changed content gets `version + 1`, is chunked and embedded with the active index version's chunking and model (exactly its chunk count of texts), and its new chunks are written in the **same transaction** that records the new version. From that commit on, no chunk of the old version is reachable by search. The old chunks may stay in the file; they are stale. `upsert` returns `{"doc_id", "version", "changed": True, "chunks": n}`.
3. **Delete.** `delete(doc_id)` removes the row from `documents` or keeps it with `deleted = 1`; either way no chunk of the document is reachable afterwards in any index version. It returns `True` when the document was current, `False` when unknown or already deleted, and never embeds. Re-adding a deleted document is out of scope.
4. **Search.** `search(query, k)` embeds the query once with the model of the index version it reads (the active one, or `version=` for a pinned reader) and returns at most `k` results, each `{"doc_id", "doc_version", "chunk_no", "text", "score"}`, from the chunks of **current document versions** held by that index version, sorted by cosine score descending, ties by `doc_id` then `chunk_no` ascending. `k < 1` raises `ValueError`; fewer than `k` results when fewer chunks are reachable. With a large `k` the result set is exactly the reachable chunks. The text of a result is the chunk text from rule 1.
5. **Index versions.** The table `index_versions` has `version TEXT PRIMARY KEY`, `embed_model TEXT`, `chunking_version INTEGER` and `active INTEGER`; at every moment between calls **exactly one** row has `active = 1`. The constructor on a fresh file creates the first version from its arguments; on an existing file the arguments are ignored and the active version stays. `rebuild(embed_model=…, chunking_version=…)` creates a new version under a new name (an unspecified parameter is inherited from the active version), fills it with every current document at its current version, chunked with its chunking version and embedded with its model (exactly that many texts, all with that model), leaves the active version untouched and still serving the same answers, and returns the new name. `upsert` and `delete` apply to the active version; other versions can fall behind.
6. **Switch and rollback.** `switch(version)` activates a version in **one transaction**: deactivate the current, activate the target, record the previous. If any statement of it fails, the exception propagates and the previously active version is still the only active one. An unknown version raises. `switch` and `rollback` never embed and never drop a version: a reader that asks for the old version by name still gets its answers. `rollback()` activates the version that was active before the most recent activation and returns its name; on a file with no activation yet it raises `ValueError`. Rolling back a rollback goes forward again.
7. **Audit.** `audit()` returns `{"active": name, "versions": [...]}` with one entry per index version: `version`, `embed_model`, `chunking_version`, `active` (bool), `documents` (current documents held at their current version), `chunks` (reachable chunks), `stale` (chunks held for superseded versions or deleted documents) and `missing` (sorted `doc_id`s of current documents the version does not hold at their current version). The counts come from the file, not from memory.
8. **The file is the state.** `close()` closes the connection. A new `Indexer(path, embed=…)` in another process answers the same active version and the same results. Every method commits before it returns; no transaction stays open between calls.

## What Verify runs

Verify constructs the indexer on its own SQLite file with an injected embedding (a hashed bag of words salted with the model name; a labeled test tool, not a model), indexes four documents with fresh codes, re-runs the upserts and expects zero embed calls, revises a runbook and searches for the old text with a large `k`, deletes a runbook and searches for it, migrates to `relay-embed-b` and compares both versions with its own chunk and cosine oracle, injects a failure into the activation statement with a database trigger and expects the old version to stay the only active one, switches, rolls back twice, changes the chunking to 2 on the live index, closes the file and reopens it in a separate Python process. The hidden bonus is a rumour from the relay room.

Two different implementations pass: versioned rows in one chunks table and one chunks table per index version both satisfy the contract. No specific structure of `indexer.py` is required beyond the two importable names and the two published tables.

## Sources

- PostgreSQL 18, `ALTER INDEX … RENAME`: a rename is transactional, so build-then-rename swaps an index atomically.
- PostgreSQL 18, `REINDEX` and `CREATE INDEX CONCURRENTLY`: a concurrent build cannot run inside a transaction block; build first, swap afterwards.
- SQLite, `ALTER TABLE … RENAME TO` and transactions: a rename and an update of a pointer row commit together or not at all.
- Python `sqlite3`: transaction control; a connection used as a context manager commits or rolls back the open transaction.
