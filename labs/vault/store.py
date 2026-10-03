def create_schema(connection):
    """Create the inventory contract described in MISSION.md."""
    connection.execute("CREATE TABLE IF NOT EXISTS items (id TEXT, name TEXT)")
    connection.execute(
        "CREATE TABLE IF NOT EXISTS movements (id TEXT, item_id TEXT, quantity INTEGER)"
    )
