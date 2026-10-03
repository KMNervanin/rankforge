import sqlite3
from store import create_schema

with sqlite3.connect("vault.sqlite") as connection:
    connection.execute("PRAGMA foreign_keys=ON")
    create_schema(connection)
    for row in connection.execute("SELECT name,sql FROM sqlite_master WHERE type='table'"):
        print(*row, sep="\n")
