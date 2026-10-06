from copy import deepcopy


def build_manifest(ticket):
    facts = [{k: deepcopy(f[k]) for k in ("id", "value", "unit")} for f in ticket["facts"]]
    kinds = sorted(set(kind for fact in ticket["facts"] for kind in fact["cases"]))
    cases = [{"id": str(n), "kind": kind, "requirements": ["service"], "assumptions": [], "description": "Observe the published guarantee."}
             for n, kind in enumerate(kinds)]
    assumptions = []
    for question in ticket["questions"]:
        choice = question["options"][-1]
        assumptions.append(dict(question=question["id"], choice=choice["id"], source="assumption"))
        cases.extend(dict(id=f"choice-{question['id']}-{kind}", kind=kind, requirements=[], assumptions=[question["id"]]) for kind in choice["cases"])
    return dict(schema_version=ticket["schema_version"], ticket_id=ticket["ticket_id"], revision=ticket["revision"],
                requirements=[dict(id="service", facts=facts)], cases=cases, assumptions=assumptions,
                open_questions=[], exclusions=sorted(ticket["exclusions"]), rationale="Choose the simpler plan for review.")
