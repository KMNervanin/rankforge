def build_manifest(ticket):
    requirements, cases = [], []
    for fact in ticket["facts"]:
        identity = "require-" + fact["id"]
        requirements.append({"id": identity, "facts": [{key: fact[key] for key in ("id", "value", "unit")}]})
        for kind in fact["cases"]:
            cases.append({"id": identity + "-" + kind, "kind": kind, "requirements": [identity], "assumptions": []})
    assumptions = []
    for question in ticket["questions"]:
        option = question["options"][0]
        assumptions.append({"question": question["id"], "choice": option["id"], "source": "assumption"})
        for kind in option["cases"]:
            cases.append({"id": "choice-" + question["id"] + "-" + kind, "kind": kind, "requirements": [], "assumptions": [question["id"]]})
    return {"schema_version": 1, "ticket_id": ticket["ticket_id"], "revision": ticket["revision"],
            "requirements": requirements, "cases": cases, "assumptions": assumptions,
            "open_questions": [], "exclusions": list(ticket["exclusions"])}
