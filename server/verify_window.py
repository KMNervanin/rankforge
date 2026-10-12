"""Context builder checks for the Window mission; run outside the learner workspace.

Nothing here calls a model. Every fixture is tiny, its costs are recomputed with Verify's own
counters, and the budgets are derived from those costs so the expected outcome is fixed by hand:
"room for exactly these sections, one short of the next".
"""
import importlib.util
import json
import os
import random
import re
import sys

MISSION, WORKSPACE = sys.argv[1:3]
CHECKS = []
MARKER = re.compile(r"^\[shortened: kept (\d+) of (\d+) passages\]$")


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def check(name, operation, optional=False):
    # An optional check is the hidden bonus of a mission: it can only add, it never fails the run.
    flag = {"optional": True} if optional else {}
    try:
        detail = operation()
        CHECKS.append({"name": name, "passed": True, "detail": detail or "Assembled messages and the budget report verified.", **flag})
    except Exception as error:
        CHECKS.append({"name": name, "passed": False, "detail": f"{type(error).__name__}: {error}"[:1500], **flag})


# Verify's counters: deliberately unlike any tokenizer, and unlike each other.
def words(text):
    return len(text.split())


def thirds(text):
    return -(-len(text.encode("utf-8")) // 3)


def passages(text):
    return [part.strip() for part in re.split(r"\n\s*\n", text.strip()) if part.strip()]


def fresh():
    rng = random.Random()
    code = f"K-{rng.randint(1000, 9999)}"
    bay = f"bay-{rng.randint(11, 99)}"
    reserve = rng.randint(12, 40)
    return code, bay, reserve


def instructions_section():
    return {"id": "ops", "kind": "instructions", "text": "You are the outpost operator assistant. Answer only from the sections below and name the runbook you used."}


def pinned_section(code):
    return {"id": "pin-code", "kind": "pinned", "text": f"Relay access code is {code} until the next rotation."}


def runbook(bay):
    return {"id": "runbook-filters", "kind": "document", "priority": 1, "text": "\n\n".join([
        "Filter cartridges are stored in the cold store and must be counted before every reservation.",
        "A reservation that exceeds the counted stock is refused and logged for the quartermaster.",
        f"Damaged cartridges go to {bay} for inspection and never back to the cold store.",
    ])}


def incident():
    return {"id": "incident-0412", "kind": "document", "priority": 2, "text": "\n\n".join([
        "Night shift reported a relay brownout at 02:10 that lasted about eleven minutes in total.",
        "Stock queries during the brownout returned stale counts because the cache never expired.",
        "The cache lease now expires after sixty seconds instead of being renewed on every read.",
        "Nobody noticed because the dashboard rendered cached values with a fresh green timestamp.",
    ])}


def memo():
    return {"id": "memo-coffee", "kind": "document", "priority": 3, "text": "The canteen reminds every outpost that coffee supplies are not reservable through the assistant and that requests for mugs, kettles or filters for the kitchen belong to the catering desk, which answers on its own channel during the day shift only."}


def turns(*texts):
    roles = ["user", "assistant"]
    result = []
    for index, text in enumerate(texts):
        role = roles[(len(texts) - 1 - index) % 2]  # the newest turn is always the operator's question
        result.append({"id": f"turn-{index + 1}", "kind": "history", "role": role, "text": text})
    return result


def trial():
    require(MISSION == "window", "Unknown mission")
    sys.path.insert(0, WORKSPACE)
    spec = importlib.util.spec_from_file_location("candidate_window", os.path.join(WORKSPACE, "context.py"))
    if spec is None or spec.loader is None:
        raise ImportError("Cannot load context.py")
    candidate = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = candidate
    spec.loader.exec_module(candidate)
    require(callable(getattr(candidate, "build", None)), "context.py must define build(sections, *, window, reserve_output, overhead, count=estimate)")
    require(callable(getattr(candidate, "estimate", None)), "context.py must define estimate(text)")
    require(isinstance(getattr(candidate, "BudgetError", None), type) and issubclass(candidate.BudgetError, BaseException), "context.py must define the BudgetError exception class")

    def cost_with(count, overhead):
        return lambda text: count(text) + overhead

    def build(sections, *, budget, reserve, overhead=2, count=words):
        window = budget + reserve
        result = candidate.build(sections, window=window, reserve_output=reserve, overhead=overhead, count=count)
        require(isinstance(result, tuple) and len(result) == 2, "build must return a (messages, report) tuple")
        messages, report = result
        require(isinstance(messages, list) and all(isinstance(message, dict) and isinstance(message.get("role"), str) and isinstance(message.get("content"), str) for message in messages), "messages must be a list of {role, content} dicts with string values")
        require(isinstance(report, dict), "report must be a dict")
        for key, wanted in (("window", window), ("reserve_output", reserve), ("budget", budget), ("overhead", overhead), ("method", count.__name__)):
            require(report.get(key) == wanted, f"report[{key!r}] must be {wanted!r}, got {report.get(key)!r}")
        recomputed = sum(count(message["content"]) + overhead for message in messages)
        require(report.get("total") == recomputed, f"report['total'] {report.get('total')!r} must equal the recomputed {recomputed} (sum of {count.__name__}(content) + overhead over the messages)")
        require(recomputed <= budget, f"The messages cost {recomputed} tokens by {count.__name__}, over the budget of {budget} = window {window} - reserve_output {reserve}")
        entries = report.get("sections")
        require(isinstance(entries, list) and [entry.get("id") for entry in entries] == [section["id"] for section in sections], "report['sections'] must list every input section by id, in input order")
        for entry, section in zip(entries, sections):
            require(entry.get("kind") == section["kind"] and entry.get("status") in ("kept", "shortened", "dropped"), f"section {section['id']}: kind and a status of kept, shortened or dropped are required")
            require(entry.get("tokens") == count(section["text"]) + overhead, f"section {section['id']}: tokens must be {count.__name__}(text) + overhead")
            require(type(entry.get("kept")) is int and (entry["kept"] == 0) == (entry["status"] == "dropped"), f"section {section['id']}: kept is 0 exactly when the section is dropped")
        require(sum(entry["kept"] for entry in entries) == recomputed, "The kept tokens of the sections must add up to the total")
        return messages, report, {section["id"]: entry for entry, section in zip(entries, sections)}

    def contents(messages):
        return [message["content"] for message in messages]

    def document_state(section, messages):
        """Returns (status, kept passage count) for a document as the messages show it, validating the shortened form."""
        parts = passages(section["text"])
        whole = "\n\n".join(parts)
        for content in contents(messages):
            if content == whole:
                return "kept", len(parts)
            lines = content.rstrip().splitlines()
            match = MARKER.match(lines[-1].strip()) if lines else None
            if match is None:
                continue
            body = passages("\n".join(lines[:-1]))
            if not body or not all(part in parts for part in body):
                continue
            indexes = [parts.index(part) for part in body]
            require(indexes == sorted(indexes) and len(set(indexes)) == len(indexes), f"{section['id']}: shortened passages must keep their original order without repeats")
            require(int(match.group(1)) == len(body) and int(match.group(2)) == len(parts), f"{section['id']}: the marker says {match.group(1)} of {match.group(2)}, the message holds {len(body)} of {len(parts)} passages")
            require(len(body) < len(parts), f"{section['id']}: a marker on a complete document is wrong")
            return "shortened", len(body)
        for content in contents(messages):
            if any(part[:40] in content for part in parts):
                raise AssertionError(f"{section['id']}: a message holds part of the document but neither the whole text nor whole passages followed by the line [shortened: kept K of N passages]: {content[:160]!r}")
        return "dropped", 0

    def under_budget():
        code, bay, reserve = fresh()
        history = turns("How many cartridges are in the cold store?", "Forty-two were counted this morning.", "Reserve ten for the relay team.")
        sections = [instructions_section(), pinned_section(code), memo(), incident(), runbook(bay)] + history
        budget = sum(words(section["text"]) + 2 for section in sections)
        messages, report, entries = build(sections, budget=budget, reserve=reserve)
        wanted = [("system", instructions_section()["text"]), ("system", pinned_section(code)["text"]), ("system", runbook(bay)["text"]), ("system", incident()["text"]), ("system", memo()["text"])]
        wanted += [(turn["role"], turn["text"]) for turn in history]
        got = [(message["role"], message["content"]) for message in messages]
        require(got == wanted, "Everything fits, so the messages must be: instructions, pinned facts, documents by ascending priority, history in order, each verbatim. Got roles " + str([role for role, _ in got]) + " with contents starting " + str([content[:24] for _, content in got]))
        require(all(entry["status"] == "kept" for entry in entries.values()), "Every section is reported as kept when everything fits")
        require(report["total"] == budget, f"Total {report['total']} must be exactly the budget {budget} that was cut to fit everything")
        return f"Eight sections kept in the published order at a budget of {budget} words with {reserve} reserved."
    check("Under budget: every section is kept in the published order and the report accounts for each", under_budget)

    def mandatory():
        code, bay, reserve = fresh()
        history = turns("Is the relay healthy?", "The relay answered within the usual time at the last check.", "Where do damaged cartridges go?")
        note = {"id": "note-paint", "kind": "document", "priority": 3, "text": f"{bay} is closed for repainting until Friday."}
        sections = [memo(), note, incident(), instructions_section(), runbook(bay)] + history[:1] + [pinned_section(code)] + history[1:]
        cost = cost_with(words, 2)
        budget = cost(instructions_section()["text"]) + cost(pinned_section(code)["text"]) + cost(history[-1]["text"]) + cost(runbook(bay)["text"]) + cost(note["text"])
        reserve = max(reserve, cost(history[1]["text"]) + 4)  # ignoring the reserve would make room for one more turn
        messages, report, entries = build(sections, budget=budget, reserve=reserve)
        require(instructions_section()["text"] in contents(messages) and messages[0]["content"] == instructions_section()["text"] and messages[0]["role"] == "system", "The instructions must survive verbatim as the first system message")
        require(pinned_section(code)["text"] in contents(messages), f"The pinned fact (code {code}) must survive verbatim")
        require(history[-1]["text"] in contents(messages) and messages[-1]["content"] == history[-1]["text"], "The newest turn is the operator's question and is never dropped; it closes the messages")
        require(any(bay in content for content in contents(messages)), f"The highest-priority document carries the fact {bay!r}; it fits whole and must survive")
        require(document_state(runbook(bay), messages)[0] == "kept", "The priority-1 runbook fits whole and must be kept whole")
        require(document_state(incident(), messages)[0] == "dropped" and document_state(memo(), messages)[0] == "dropped", "The priority-2 incident report and the priority-3 memo do not fit, not even one passage with the marker: dropped")
        require(document_state(note, messages)[0] == "kept", "A dropped document does not end the fill: the small priority-3 note behind the dropped incident report fits and must be kept")
        require(contents(messages).index(note["text"]) > contents(messages).index(runbook(bay)["text"]), "Documents keep ascending priority: the note follows the runbook")
        require(entries["ops"]["status"] == "kept" and entries["pin-code"]["status"] == "kept" and entries["runbook-filters"]["status"] == "kept" and entries["note-paint"]["status"] == "kept", "The report must mark the surviving sections as kept")
        return f"Budget {budget} with {reserve} reserved: instructions, pinned fact, newest turn, the priority-1 runbook and a small priority-3 note survived; the priority-2 report and the memo were dropped."
    check("Over budget: instructions, pinned facts and the newest turn survive and the total respects the reserved output", mandatory)

    def history_order():
        code, bay, reserve = fresh()
        history = turns(
            "Good morning, I am taking over the desk from the night shift today.",
            "Welcome to the day shift; the night count is already in the ledger.",
            "Open reservations?",
            "There are two open reservations, both for filter cartridges, pickup at noon.",
            "Cancel the second one and keep the first.",
            "The second reservation is cancelled; the first stays open for noon.",
            "What is the relay access code?",
        )
        sections = [instructions_section(), pinned_section(code), runbook(bay)] + history
        cost = cost_with(words, 2)
        budget = sum(cost(section["text"]) for section in sections[:3]) + cost(history[6]["text"]) + cost(history[5]["text"]) + cost(history[4]["text"]) + cost(history[3]["text"]) - 1
        messages, report, entries = build(sections, budget=budget, reserve=reserve)
        kept = [message["content"] for message in messages if message["role"] in ("user", "assistant")]
        require(kept == [turn["text"] for turn in history[4:]], "Room for exactly the three newest turns: turn-5, turn-6 and turn-7 are kept whole and in order, turn-1 to turn-4 are dropped (turn-3 is tiny, but older than turn-4, which did not fit). Got " + str([text[:30] for text in kept]))
        require([entries[f"turn-{n}"]["status"] for n in range(1, 8)] == ["dropped"] * 4 + ["kept"] * 3, "The report must mark turn-1..turn-4 dropped and turn-5..turn-7 kept")
        return "Three newest turns kept as a contiguous run; four older turns dropped, including a tiny one behind the first that did not fit."
    check("History is dropped oldest-first as whole turns: the kept turns are a contiguous newest run", history_order)

    def shortening():
        code, bay, reserve = fresh()
        history = turns(
            "Please check the night shift notes about the brownout before we reserve anything else today.",
            "The notes are in incident report 0412; I can summarize them if you want.",
            "Why did stock queries show stale counts during the brownout and what changed in the cache?",
        )
        sections = [instructions_section(), pinned_section(code), runbook(bay), incident(), memo()] + history
        cost = cost_with(words, 2)
        parts = passages(incident()["text"])
        two = "\n\n".join(parts[:2] + ["[shortened: kept 2 of 4 passages]"])
        budget = sum(cost(section["text"]) for section in sections[:3]) + cost(history[-1]["text"]) + cost(two)
        messages, report, entries = build(sections, budget=budget, reserve=reserve)
        require(document_state(runbook(bay), messages) == ("kept", 3) and any(bay in content for content in contents(messages)), f"The priority-1 runbook fits whole, so all three passages and the fact {bay!r} must survive")
        status, kept = document_state(incident(), messages)
        require(status == "shortened", f"The incident report does not fit whole but its passages do: it must be shortened at passage boundaries with the marker line, not {status}")
        require(1 <= kept <= 2, f"Room for two passages and the marker: {kept} kept")
        require(entries["incident-0412"]["status"] == "shortened", "The report must mark the incident report as shortened")
        require(document_state(memo(), messages)[0] == "dropped" and entries["memo-coffee"]["status"] == "dropped", "The priority-3 memo is one passage that does not fit: dropped, not cut")
        require(not any("brownout at 02:10 that lasted" in content and "the dashboard rendered" in content for content in contents(messages)), "The whole incident report cannot fit the budget")
        return f"Runbook kept whole, incident report shortened to {kept} of 4 whole passages with the marker, memo dropped; budget {budget} words."
    check("A document that does not fit is shortened at passage boundaries with a visible marker, never cut mid-sentence", shortening)

    def counters():
        code, bay, reserve = fresh()
        require(candidate.estimate("ёж") == 4 and candidate.estimate("relay") == 5, "estimate(text) is the byte bound: len(text.encode('utf-8'))")
        history = turns("The relay team asks for ten cartridges.", "Ten cartridges can be reserved from the counted stock.", "Where do damaged cartridges go and who inspects them?")
        sections = [instructions_section(), pinned_section(code), runbook(bay), incident(), memo()] + history
        details = []
        for count, overhead in ((thirds, 3), (candidate.estimate, 7), (words, 2)):
            cost = cost_with(count, overhead)
            parts = passages(incident()["text"])
            one = "\n\n".join(parts[:1] + ["[shortened: kept 1 of 4 passages]"])
            budget = sum(cost(section["text"]) for section in sections[:3]) + cost(history[-1]["text"]) + cost(one) + 1
            messages, report, entries = build(sections, budget=budget, reserve=reserve, overhead=overhead, count=count)
            require(pinned_section(code)["text"] in contents(messages) and any(bay in content for content in contents(messages)), f"With {count.__name__}: the pinned code and the runbook fact must survive")
            require(document_state(incident(), messages)[0] == "shortened", f"With {count.__name__}: room for one passage and the marker, so the incident report is shortened")
            details.append(f"{count.__name__}: {report['total']} of {budget}")
        return "The limit held under three counters, " + "; ".join(details) + "."
    check("Any counter: the injected count function decides the fit and the report names it; the default is the byte bound", counters)

    def transfer():
        code, bay, reserve = fresh()
        reserve = min(reserve, 28)  # half of a window this small must still hold the mandatory sections and the runbook
        history = turns("Reserve twelve cartridges for the relay team.", "Twelve cartridges are reserved for pickup at noon.", "Repeat the relay access code, please.")
        sections = [instructions_section(), pinned_section(code), runbook(bay), incident(), memo()] + history
        cost = cost_with(words, 2)
        mandatory_cost = cost(instructions_section()["text"]) + cost(pinned_section(code)["text"]) + cost(history[-1]["text"])
        full_budget = sum(cost(section["text"]) for section in sections)
        window = full_budget + reserve
        messages, _, _ = build(sections, budget=full_budget, reserve=reserve)
        require(len(messages) == 8, "The full window holds every section")
        half = window // 2
        messages, report, entries = build(sections, budget=half - reserve, reserve=reserve)
        require(messages[0]["content"] == instructions_section()["text"] and pinned_section(code)["text"] in contents(messages) and messages[-1]["content"] == history[-1]["text"], "Half the window: instructions, pinned fact and the newest turn still survive")
        require(any(bay in content for content in contents(messages)), "Half the window: the priority-1 runbook still fits and its fact survives")
        require(report["total"] <= half - reserve, "Half the window: the total stays within window // 2 - reserve_output")
        raised = False
        try:
            candidate.build(sections, window=mandatory_cost + reserve - 1, reserve_output=reserve, overhead=2, count=words)
        except candidate.BudgetError:
            raised = True
        require(raised, "When the mandatory sections alone exceed window - reserve_output, build raises BudgetError instead of cutting them")
        return f"Window {window} held eight sections; window {half} kept the mandatory sections and the runbook at {report['total']} tokens; a window one short of the mandatory cost raised BudgetError."
    check("Transfer: half the window keeps the mandatory sections and still fits; an impossible budget raises BudgetError", transfer)

    def deterministic():
        code, bay, reserve = fresh()
        rival = {"id": "incident-0377", "kind": "document", "priority": 2, "text": "A forklift blocked the cold store door for twenty minutes while the morning count was running, so the count restarted from zero."}
        history = turns("Any blockers in the cold store today?")
        sections = [instructions_section(), pinned_section(code), incident(), rival] + history
        cost = cost_with(words, 2)
        budget = cost(instructions_section()["text"]) + cost(pinned_section(code)["text"]) + cost(history[0]["text"]) + cost(incident()["text"]) + cost(rival["text"]) - 1
        first = build(sections, budget=budget, reserve=reserve)
        second = build(sections, budget=budget, reserve=reserve)
        require(first[0] == second[0] and first[1] == second[1], "The same inputs must build the same messages and the same report")
        messages, _, entries = first
        require(document_state(incident(), messages)[0] == "kept", "Equal priority 2: the document earlier in the input is included first and fits whole")
        require(document_state(rival, messages)[0] == "dropped" and entries["incident-0377"]["status"] == "dropped", "Equal priority 2: the later document does not fit (one passage plus a marker) and is dropped")
        swapped = [instructions_section(), pinned_section(code), rival, incident()] + history
        messages, _, entries = build(swapped, budget=budget, reserve=reserve)
        require(document_state(rival, messages)[0] == "kept" and entries["incident-0412"]["status"] != "kept", "Swapping two equal-priority documents swaps which one is included first")
        return "Two builds agreed byte for byte; equal priorities followed input order both ways."
    check("Deterministic: the same inputs build the same context; equal priorities keep input order", deterministic)

    def alternation():
        code, bay, reserve = fresh()
        history = turns(
            "Good morning, I am taking over the desk from the night shift today.",
            "Noted, welcome to the day shift at the relay desk.",
            "Please list every open reservation for the relay team and their pickup times.",
            "There are two open reservations, both for filter cartridges, pickup at noon.",
            "Cancel the second one and keep the first.",
            "The second reservation is cancelled; the first stays open for noon.",
            "What is the relay access code?",
        )
        sections = [instructions_section(), pinned_section(code), runbook(bay)] + history
        cost = cost_with(words, 2)
        budget = sum(cost(section["text"]) for section in sections[:3]) + sum(cost(turn["text"]) for turn in history[3:]) + cost(history[2]["text"]) - 1
        messages, _, entries = build(sections, budget=budget, reserve=reserve)
        kept = [message for message in messages if message["role"] in ("user", "assistant")]
        require(kept and kept[0]["role"] == "user", "The kept history starts with an assistant turn whose question was dropped; drop that answer too so the run starts with the operator")
        require([message["content"] for message in kept] == [turn["text"] for turn in history[4:]], "turn-4 (an answer) goes with its dropped question; turn-5..turn-7 stay")
        return "A leading assistant turn was dropped with its question; the kept run starts with the operator."
    check("bonus: the kept history starts with an operator turn, never with an orphaned answer", alternation, optional=True)


# Fixture sanity, outside every check: a verifier bug must crash loudly, never read as a learner failure.
# The transfer fixture clamps the reserve to 28, so the worst case is checked here with placeholder values.
_sections = [instructions_section(), pinned_section("K-0000"), runbook("bay-00"), incident(), memo()] + turns("Reserve twelve cartridges for the relay team.", "Twelve cartridges are reserved for pickup at noon.", "Repeat the relay access code, please.")
_cost = lambda text: words(text) + 2
_window = sum(_cost(section["text"]) for section in _sections) + 28
if _window // 2 - 28 < sum(_cost(section["text"]) for section in _sections[:3]) + _cost(_sections[-1]["text"]):
    raise RuntimeError("verifier bug: half of the transfer window cannot hold the mandatory sections and the runbook")

try:
    trial()
except Exception as error:
    CHECKS.append({"name": "Load context builder", "passed": False, "detail": f"{type(error).__name__}: {error}"[:1500]})
print(json.dumps({"checks": CHECKS}))
sys.exit(0 if CHECKS and all(item["passed"] for item in CHECKS if not item.get("optional")) else 1)
