"""Context builder for the operator assistant.

Starter: it turns instructions, pinned facts, documents and history into messages
and prints a budget report, but the policy behind the report is guesswork. See
LEARN.md for the complete contract that Verify checks.
"""


class BudgetError(Exception):
    """Raised when the mandatory sections alone do not fit the budget."""


def estimate(text):
    return len(text) // 4


def build(sections, *, window, reserve_output, overhead, count=estimate):
    budget = window - reserve_output
    ordered = sorted(sections, key=lambda section: section.get("priority", 99))
    messages, entries, total = [], [], 0
    for section in ordered:
        text = section["text"]
        tokens = count(text) + overhead
        status, content = "kept", text
        if total + tokens > window:
            room = window - total - overhead
            if room <= 0 or section["kind"] != "document":
                status, content = "dropped", ""
            else:
                status, content = "shortened", text[: room * 4]
        kept = count(content) + overhead if status != "dropped" else 0
        if status != "dropped":
            messages.append({"role": section.get("role", "system"), "content": content})
            total += kept
        entries.append({"id": section["id"], "kind": section["kind"], "status": status, "tokens": tokens, "kept": kept})
    report = {"window": window, "reserve_output": reserve_output, "budget": budget, "overhead": overhead, "method": count.__name__, "total": total, "sections": entries}
    return messages, report
