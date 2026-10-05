def ingest(connection, event):
    if not isinstance(event, dict) or not isinstance(event.get("id"), str) or not event["id"] or not isinstance(event.get("item"), str) or not event["item"] or type(event.get("quantity")) is not int or not 1 <= event["quantity"] <= 9223372036854775807:
        raise ValueError("Invalid event")
    connection.execute("CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY,item TEXT NOT NULL,quantity INTEGER NOT NULL CHECK(quantity>0))")
    existing = connection.execute("SELECT item,quantity FROM events WHERE id=?", (event["id"],)).fetchone()
    if existing:
        if existing != (event["item"], event["quantity"]):
            raise ValueError("Conflicting identity")
        return False
    connection.execute("INSERT INTO events(id,item,quantity) VALUES (?,?,?)", (event["id"], event["item"], event["quantity"]))
    return True
