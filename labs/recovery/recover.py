import sqlite3


def recover(db_path, events):
    with sqlite3.connect(db_path) as connection:
        connection.execute("DROP TABLE IF EXISTS events")
        connection.execute("CREATE TABLE events (id TEXT, item TEXT, quantity INTEGER)")
        for event in events:
            connection.execute("INSERT INTO events VALUES (?,?,?)",
                               (event["id"], event["item"], event["quantity"]))
    return {"event_count": len(events), "total_quantity": 0}
