def ingest(connection, event):
    connection.execute("CREATE TABLE IF NOT EXISTS events (id TEXT, item TEXT, quantity INTEGER)")
    connection.execute("INSERT INTO events VALUES (?, ?, ?)",
                       (event["id"], event["item"], event["quantity"]))
    return True
