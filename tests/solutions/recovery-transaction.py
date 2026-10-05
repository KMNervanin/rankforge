import sqlite3
from importlib import import_module

ingest = import_module("ingest").ingest


def recover(db_path, events):
    connection = sqlite3.connect(db_path)
    try:
        with connection:
            connection.execute("BEGIN")
            connection.execute("CREATE TABLE IF NOT EXISTS events(quantity INTEGER, item TEXT, id TEXT PRIMARY KEY)")
            connection.execute("DELETE FROM events")
            for event in events:
                ingest(connection, event)
            quantities = [row[0] for row in connection.execute("SELECT quantity FROM events")]
            return {"event_count": len(quantities), "total_quantity": sum(quantities)}
    finally:
        connection.close()
