def create_schema(connection):
    connection.execute("CREATE TABLE IF NOT EXISTS items(id TEXT PRIMARY KEY,name TEXT NOT NULL)")
    connection.execute("""CREATE TABLE IF NOT EXISTS movements(
        id TEXT PRIMARY KEY,
        item_id TEXT NOT NULL REFERENCES items(id),
        quantity INTEGER NOT NULL CHECK(quantity > 0))""")
    # Foreign keys are enforced per connection; a client that forgot the pragma must still not orphan movements.
    connection.execute("""CREATE TRIGGER IF NOT EXISTS items_keep_movements BEFORE DELETE ON items
        WHEN EXISTS (SELECT 1 FROM movements WHERE item_id = OLD.id)
        BEGIN SELECT RAISE(ABORT, 'item is still referenced by movements'); END""")
