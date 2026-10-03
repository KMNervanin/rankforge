# Field manual — The memory vault

## Why the schema matters

Suppose two different clients write to one database. A check in one client does not protect writes from the other. A database constraint protects the shared boundary.

An item is an entity; a movement is a fact about that item. The movement stores the item's identity, not another editable copy of its name. A primary key gives each row an identity. A foreign key requires a referenced entity to exist. NOT NULL and CHECK reject values your model cannot accept.

## Investigate

Run `python3 inspect_vault.py` to see the actual schema. Read the CREATE TABLE output, then compare it with each requirement. Modify `create_schema` and inspect a **new scratch database** when changing constraints: CREATE TABLE IF NOT EXISTS does not migrate an old table.

The built-in verifier starts fresh databases and also checks repeated schema creation. Your existing `vault.sqlite` remains your own exploration file. To inspect a new schema without deleting your previous work, change the scratch filename in `inspect_vault.py`.

## SQLite details

Foreign key enforcement is enabled for each connection with `PRAGMA foreign_keys=ON`. The verifier does this before calling your function. Use `connection.execute` for SQL. Do not catch integrity exceptions inside schema creation to hide an invalid contract.

Useful questions: Can a movement reference an unknown item? Can it have quantity zero? What happens if setup runs twice? Which rules belong in SQL, and which would need a richer business operation?

## A first design explanation

Explain one choice in this shape: a rule, the bad state it blocks, and an example. Correct meaning matters more than a fancy sentence.
