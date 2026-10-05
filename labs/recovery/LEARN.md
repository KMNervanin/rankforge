# Field manual — The recovery core

## A backup is a hypothesis until you restore it

The archive contains facts from which you can rebuild a database. A recovery operation needs two promises: valid input establishes the requested state, and invalid input preserves the previous trusted state.

The archive is a list of dictionaries with nonempty string `id`/`item` and integer `quantity` from 1 through 9223372036854775807, excluding bool. Ignore extra fields; do not trim or case-fold identities. Exact duplicates count once; malformed records and either an item or quantity conflict raise `ValueError`.

A successful recovery replaces the entire old event set, even when both old and new archives are nonempty. Empty input clears old events. The persistent table uses the column names and `id` primary key in the contract; physical column order may vary. Return the count and quantity sum of the resulting events, not the input length.

Write down what must remain true if the third record is invalid after two good records. Then decide where validation ends and durable replacement begins.

## A transaction boundary

A transaction lets several database changes commit or roll back together. Read Python's SQLite transaction documentation carefully: the placement of a context manager matters, and statements executed before a transaction may not roll back as you expect.

You can validate and deduplicate the entire archive before replacement for this small lab. Another design can use a staging structure and an atomic commit. The checker accepts behavior, not a particular implementation.

Validation inside a rollback-capable transaction is also valid. A late invalid record must preserve previous rows, schema and unrelated data after reconnecting. This means logical state, not byte-for-byte equality of SQLite files. Power loss, disk exhaustion and concurrent recovery are not exercised here. Existing saved manuals are preserved; the game's objectives show the current contract.

## A transfer challenge

Start without a hint if you can. Connect what you learned about identity, validation, constraints and repeatability. If you need help, ask: a guided completion still restores the core, while the journal honestly records the assistance.

Use `python3 drill.py` for exploration. Also consider an empty archive and a conflict late in the archive. The verifier creates its own scratch databases and tests that failed recovery leaves old data intact.

## The handover

Explain the restored state, the failure boundary and your evidence to the next operator. Imagine they must run the procedure tomorrow without guessing what you meant.
