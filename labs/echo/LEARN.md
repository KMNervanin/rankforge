# Field manual — The event conduit

## Why a retry happens

A sender sends a delivery event. The receiver commits it, but the reply is lost. The sender cannot tell whether the write happened, so it tries again. Rejecting all retries is not a useful protocol; counting every delivery again is incorrect.

Separate event identity from delivery attempts. An exact replay has the same identity and payload. A conflicting event reuses an identity but changes its meaning. It must be rejected rather than silently replacing history.

## Explore

Run `python3 replay.py` and inspect the stored rows. Then run it again. Where must remembered identities live if a process can restart? Could a Python set alone satisfy the contract?

Your function receives a SQLite connection. A parameterized query uses `?` placeholders and a tuple of values. A database primary key can enforce identity even when your application accidentally attempts another insert. Advice, not checked here: use placeholders rather than string interpolation for SQL values; Verify never sends an id containing quotes.

## Validate at the boundary

Check input before making a durable change. Python's `bool` is a subclass of `int`; the mission requires an `int` quantity, not True/False and not a float such as `7.0`. Keep a conflicting existing row intact.

An event is a dictionary with nonempty string `id` and `item`, and `int` `quantity` in SQLite's positive INTEGER range, 1 through 9223372036854775807. Do not trim or case-fold identities; ignore extra fields. Non-dictionaries, any missing required field and any invalid field value raise `ValueError` without changing existing events. A new identity returns exactly `True`; an exact replay returns exactly `False`. Return the bool objects, not 1 and 0. The persistent `events` table must have `id` as its primary key; column order is your choice. `ingest` creates the table if it does not exist: Verify supplies fresh connections without a schema.

The caller owns the supplied connection and commits and closes it. Verify commits before reconnecting. Reading an existing record first and trying an insert first are both valid when replay, conflict and invalid-input behavior agree. Concurrent writers and schema migration are outside this exercise. Existing saved manuals are preserved; the game's objectives show the current contract.

The verifier checks behavior across fresh connections. Your local scratch `events.sqlite` may still contain the original permissive schema; use a new scratch filename when investigating a changed schema rather than assuming IF NOT EXISTS migrates it.

## Later connection

Kafka and other event systems also involve delivery, acknowledgement and retry. This mission teaches the receiver's responsibility before introducing a broker.
