"""Context builder: retrieval of the most relevant passages, dataclasses and a deque."""
import re
from collections import deque
from dataclasses import dataclass, field

WORD = re.compile(r"\w+")


class BudgetError(Exception):
    """Raised when the mandatory sections alone do not fit the budget."""


def estimate(text):
    return len(text.encode("utf-8"))


@dataclass
class Slot:
    id: str
    kind: str
    text: str
    role: str = "system"
    priority: int = 0
    status: str = "dropped"
    content: str = ""
    parts: list = field(default_factory=list)


class Budget:
    def __init__(self, limit, overhead, count):
        self.limit, self.overhead, self.count, self.spent = limit, overhead, count, 0

    def cost(self, text):
        return self.count(text) + self.overhead

    def fits(self, text):
        return self.spent + self.cost(text) <= self.limit

    def take(self, slot, content, status):
        slot.content, slot.status = content, status
        self.spent += self.cost(content)

    def release(self, slot):
        self.spent -= self.cost(slot.content)
        slot.content, slot.status = "", "dropped"


def split_passages(text):
    return [part.strip() for part in re.split(r"\n\s*\n", text.strip()) if part.strip()]


def relevance(passage, question):
    wanted = {word.lower() for word in WORD.findall(question)}
    return sum(1 for word in WORD.findall(passage) if word.lower() in wanted)


def shortened(slot, question, budget):
    """Rank passages by overlap with the question, keep those that fit, emit them in original order."""
    ranked = sorted(range(len(slot.parts)), key=lambda index: (-relevance(slot.parts[index], question), index))
    chosen = []
    for index in ranked:
        candidate = sorted(chosen + [index])
        content = "\n\n".join([slot.parts[i] for i in candidate] + [f"[shortened: kept {len(candidate)} of {len(slot.parts)} passages]"])
        if len(candidate) < len(slot.parts) and budget.fits(content):
            chosen = candidate
    if not chosen:
        return None
    return "\n\n".join([slot.parts[i] for i in chosen] + [f"[shortened: kept {len(chosen)} of {len(slot.parts)} passages]"])


def build(sections, *, window, reserve_output, overhead, count=estimate):
    budget = Budget(window - reserve_output, overhead, count)
    slots = [Slot(id=str(section["id"]), kind=section["kind"], text=section["text"], role=section.get("role", "system"),
                  priority=int(section.get("priority", 0)), parts=split_passages(section["text"]) if section["kind"] == "document" else [])
             for section in sections]
    instructions = [slot for slot in slots if slot.kind == "instructions"]
    pinned = [slot for slot in slots if slot.kind == "pinned"]
    documents = sorted(((slot.priority, index, slot) for index, slot in enumerate(slots) if slot.kind == "document"))
    history = deque(slot for slot in slots if slot.kind == "history")
    newest = history.pop() if history else None

    for slot in instructions + pinned + ([newest] if newest else []):
        budget.take(slot, slot.text, "kept")
    if budget.spent > budget.limit:
        raise BudgetError(f"mandatory sections need {budget.spent} tokens of a {budget.limit} budget")

    question = newest.text if newest else ""
    for _, _, slot in documents:
        whole = "\n\n".join(slot.parts)
        if budget.fits(whole):
            budget.take(slot, whole, "kept")
        else:
            content = shortened(slot, question, budget)
            if content is not None:
                budget.take(slot, content, "shortened")

    kept = deque()
    while history:
        turn = history.pop()
        if not budget.fits(turn.text):
            break
        budget.take(turn, turn.text, "kept")
        kept.appendleft(turn)
    while kept and kept[0].role == "assistant":
        budget.release(kept.popleft())

    messages = [{"role": "system", "content": slot.content} for slot in instructions + pinned]
    messages += [{"role": "system", "content": slot.content} for _, _, slot in documents if slot.status != "dropped"]
    messages += [{"role": slot.role, "content": slot.content} for slot in slots if slot.kind == "history" and slot.status != "dropped"]
    report = {
        "window": window, "reserve_output": reserve_output, "budget": budget.limit, "overhead": overhead, "method": count.__name__,
        "total": budget.spent,
        "sections": [{"id": slot.id, "kind": slot.kind, "status": slot.status, "tokens": budget.cost(slot.text),
                      "kept": budget.cost(slot.content) if slot.status != "dropped" else 0} for slot in slots],
    }
    return messages, report
