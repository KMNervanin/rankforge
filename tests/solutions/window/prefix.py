"""Context builder: prefix truncation of documents, plain lists and dicts."""
import re

PASSAGE_BREAK = re.compile(r"\n[ \t]*\n+")


class BudgetError(Exception):
    """Raised when the mandatory sections alone do not fit the budget."""


def estimate(text):
    return len(text.encode("utf-8"))


def passages(text):
    return [part.strip() for part in PASSAGE_BREAK.split(text.strip()) if part.strip()]


def marker(kept, total):
    return f"[shortened: kept {kept} of {total} passages]"


def build(sections, *, window, reserve_output, overhead, count=estimate):
    budget = window - reserve_output

    def cost(text):
        return count(text) + overhead

    entries = [dict(section, index=index, status="dropped", content=None) for index, section in enumerate(sections)]
    history = [entry for entry in entries if entry["kind"] == "history"]
    mandatory = [entry for entry in entries if entry["kind"] in ("instructions", "pinned")] + history[-1:]
    documents = sorted((entry for entry in entries if entry["kind"] == "document"), key=lambda entry: (int(entry["priority"]), entry["index"]))
    older = history[:-1]

    for entry in mandatory:
        entry["content"], entry["status"] = entry["text"], "kept"
    spent = sum(cost(entry["content"]) for entry in mandatory)
    if spent > budget:
        raise BudgetError(f"instructions, pinned facts and the newest turn need {spent} tokens, the budget is {budget}")

    for entry in documents:
        parts = passages(entry["text"])
        whole = "\n\n".join(parts)
        if spent + cost(whole) <= budget:
            entry["content"], entry["status"] = whole, "kept"
            spent += cost(whole)
            continue
        for kept in range(len(parts) - 1, 0, -1):
            content = "\n\n".join(parts[:kept] + [marker(kept, len(parts))])
            if spent + cost(content) <= budget:
                entry["content"], entry["status"] = content, "shortened"
                spent += cost(content)
                break
        else:
            continue  # a dropped document does not end the fill

    kept_history = []
    for entry in reversed(older):
        if spent + cost(entry["text"]) > budget:
            break
        kept_history.insert(0, entry)
        spent += cost(entry["text"])
    # The bonus rule: an answer whose question was cut only confuses the model, so a kept run never starts with an assistant turn.
    while kept_history and kept_history[0]["role"] == "assistant":
        spent -= cost(kept_history[0]["text"])
        kept_history.pop(0)
    for entry in kept_history:
        entry["content"], entry["status"] = entry["text"], "kept"

    ordered = [entry for entry in entries if entry["kind"] == "instructions"] + [entry for entry in entries if entry["kind"] == "pinned"] + documents + history
    messages = [{"role": entry["role"] if entry["kind"] == "history" else "system", "content": entry["content"]} for entry in ordered if entry["status"] != "dropped"]
    report = {
        "window": window, "reserve_output": reserve_output, "budget": budget, "overhead": overhead, "method": count.__name__,
        "total": spent,
        "sections": [{"id": entry["id"], "kind": entry["kind"], "status": entry["status"], "tokens": cost(entry["text"]),
                      "kept": cost(entry["content"]) if entry["status"] != "dropped" else 0} for entry in entries],
    }
    return messages, report
