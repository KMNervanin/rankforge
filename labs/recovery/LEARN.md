# Field manual — The recovery core

## A backup is a hypothesis until you restore it

The archive contains facts from which you can rebuild a database. A recovery operation needs two promises: valid input establishes the requested state, and invalid input preserves the previous trusted state.

Write down what must remain true if the third record is invalid after two good records. Then decide where validation ends and durable replacement begins.

## A transaction boundary

A transaction lets several database changes commit or roll back together. Read Python's SQLite transaction documentation carefully: the placement of a context manager matters, and statements executed before a transaction may not roll back as you expect.

You can validate and deduplicate the entire archive before replacement for this small lab. Another design can use a staging structure and an atomic commit. The checker accepts behavior, not a particular implementation.

## A transfer challenge

Start without a hint if you can. Connect what you learned about identity, validation, constraints and repeatability. If you need help, ask: a guided completion still restores the core, while the journal honestly records the assistance.

Use `python3 drill.py` for exploration. Also consider an empty archive and a conflict late in the archive. The verifier creates its own scratch databases and tests that failed recovery leaves old data intact.

## The handover

Explain the restored state, the failure boundary and your evidence to the next operator. Imagine they must run the procedure tomorrow without guessing what you meant.
