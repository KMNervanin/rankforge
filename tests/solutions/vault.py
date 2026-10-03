def create_schema(connection):
    connection.execute("CREATE TABLE IF NOT EXISTS items(id TEXT PRIMARY KEY,name TEXT NOT NULL)")
    connection.execute("""CREATE TABLE IF NOT EXISTS movements(
        id TEXT PRIMARY KEY,
        item_id TEXT NOT NULL REFERENCES items(id),
        quantity INTEGER NOT NULL CHECK(quantity > 0))""")
