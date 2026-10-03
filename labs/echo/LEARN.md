# Field manual — The event conduit

## Why a retry happens

A sender sends a delivery event. The receiver commits it, but the reply is lost. The sender cannot tell whether the write happened, so it tries again. Rejecting all retries is not a useful protocol; counting every delivery again is incorrect.

Separate event identity from delivery attempts. An exact replay has the same identity and payload. A conflicting event reuses an identity but changes its meaning. It must be rejected rather than silently replacing history.

## Explore

Run `python3 replay.py` and inspect the stored rows. Then run it again. Where must remembered identities live if a process can restart? Could a Python set alone satisfy the contract?

Your function receives a SQLite connection. A parameterized query uses `?` placeholders and a tuple of values. A database primary key can enforce identity even when your application accidentally attempts another insert. Do not use string interpolation for SQL values.

## Validate at the boundary

Check input before making a durable change. Python's `bool` is a subclass of `int`; the mission requires an integer quantity, not True/False. Keep a conflicting existing row intact.

The verifier checks behavior across fresh connections. Your local scratch `events.sqlite` may still contain the original permissive schema; use a new scratch filename when investigating a changed schema rather than assuming IF NOT EXISTS migrates it.

## Later connection

Kafka and other event systems also involve delivery, acknowledgement and retry. This mission teaches the receiver's responsibility before introducing a broker.
