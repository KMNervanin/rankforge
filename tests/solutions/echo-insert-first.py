import sqlite3


def ingest(connection, event):
    if not isinstance(event, dict):
        raise ValueError("Expected event")
    identity, item, quantity = (event.get(key) for key in ("id", "item", "quantity"))
    if not isinstance(identity, str) or not identity or not isinstance(item, str) or not item:
        raise ValueError("Invalid identity or item")
    if type(quantity) is not int or not 1 <= quantity <= 9223372036854775807:
        raise ValueError("Invalid quantity")
    connection.execute("CREATE TABLE IF NOT EXISTS events(quantity INTEGER, item TEXT, id TEXT, PRIMARY KEY(id))")
    try:
        connection.execute("INSERT INTO events(id,item,quantity) VALUES(?,?,?)", (identity, item, quantity))
        return True
    except sqlite3.IntegrityError:
        prior = connection.execute("SELECT item,quantity FROM events WHERE id=?", (identity,)).fetchone()
        if prior != (item, quantity):
            raise ValueError("Conflicting identity")
        return False
