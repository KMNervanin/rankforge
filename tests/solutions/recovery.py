import sqlite3


def recover(db_path, events):
    valid = {}
    for event in events:
        if not isinstance(event, dict) or not isinstance(event.get("id"), str) or not event["id"] or not isinstance(event.get("item"), str) or not event["item"] or type(event.get("quantity")) is not int or event["quantity"] <= 0:
            raise ValueError("Invalid event")
        payload = (event["item"], event["quantity"])
        if event["id"] in valid and valid[event["id"]] != payload:
            raise ValueError("Conflicting identity")
        valid[event["id"]] = payload
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY,item TEXT,quantity INTEGER)")
        connection.execute("DELETE FROM events")
        connection.executemany("INSERT INTO events VALUES (?,?,?)", [(key, *value) for key, value in valid.items()])
    return {"event_count": len(valid), "total_quantity": sum(value[1] for value in valid.values())}
