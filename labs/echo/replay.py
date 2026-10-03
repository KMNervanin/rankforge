import sqlite3
from ingest import ingest

event = {"id": "delivery-17", "item": "power-cell", "quantity": 3}
with sqlite3.connect("events.sqlite") as connection:
    print("first:", ingest(connection, event))
    print("retry:", ingest(connection, event))
    print("stored:", connection.execute("SELECT * FROM events").fetchall())
