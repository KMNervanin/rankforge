def build_manifest(ticket):
    """Turn a versioned ticket into the manifest described in LEARN.md."""
    return {
        "schema_version": 1,
        "ticket_id": ticket["ticket_id"],
        "revision": ticket["revision"],
        "requirements": [],
        "cases": [],
        "assumptions": [],
        "open_questions": [],
        "exclusions": [],
    }
