"""Chunking checks for the Chunking mission; run outside the learner workspace.

Every verdict comes from code. Verify builds its own passages with fresh ids and numbers, injects a scripted
embedding function (a hashed bag of words, a labeled test tool and never a model), recomputes word streams,
units, rankings, recall@k and MRR@k with Fractions, and compares. There is no live part and no network.
"""
import copy
import hashlib
import importlib.util
import json
import math
import os
import random
import re
import sys
import time
from fractions import Fraction

MISSION, WORKSPACE = sys.argv[1:3]
CHECKS = []
TOLERANCE = Fraction(1, 10**9)
DIMENSIONS = 256


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def check(name, operation, optional=False):
    # An optional check is the hidden bonus of a mission: it can only add, it never fails the run.
    flag = {"optional": True} if optional else {}
    try:
        detail = operation()
        CHECKS.append({"name": name, "passed": True, "detail": detail or "Verified against fresh fixtures.", **flag})
    except Exception as error:
        CHECKS.append({"name": name, "passed": False, "detail": f"{type(error).__name__}: {error}"[:1500], **flag})


# Scripted embedding: hashed bag of words, L2-normalised. Deterministic, no model, no network.
def embed(texts):
    vectors = []
    for text in texts:
        vector = [0.0] * DIMENSIONS
        for token in re.findall(r"[a-z0-9]+", str(text).lower()):
            if len(token) < 4:
                continue
            slot = int(hashlib.sha256(token.encode("utf-8")).hexdigest()[:8], 16) % DIMENSIONS
            vector[slot] += 1.0
        norm = math.sqrt(sum(value * value for value in vector))
        vectors.append([value / norm for value in vector] if norm else vector)
    return vectors


def cosine(left, right):
    return sum(a * b for a, b in zip(left, right))  # both unit vectors


# Oracle: the published rules, recomputed here independently of the learner module.
def oracle_words(passage):
    text = passage["text"]
    if passage.get("warning"):
        text = f"{text}\nWarning: {passage['warning']}"
    return text.split()


def oracle_stream(passages):
    """Per document: word list, passage ranges and units (a step plus its attached warning)."""
    docs = {}
    for passage in passages:
        docs.setdefault(passage["doc_id"], []).append(passage)
    out = {}
    for doc_id, items in docs.items():
        words, ranges = [], []
        for passage in items:
            own = oracle_words(passage)
            ranges.append((len(words), len(words) + len(own)))
            words.extend(own)
        units, index = [], 0
        while index < len(items):
            passage = items[index]
            unit = {"start": ranges[index][0], "end": ranges[index][1], "ids": [passage["id"]], "kind": passage["kind"], "warning": None}
            if passage["kind"] == "step":
                if passage.get("warning"):
                    unit["warning"] = (passage["id"], passage["id"])
                elif index + 1 < len(items) and items[index + 1]["kind"] == "paragraph" and items[index + 1]["text"].lstrip().lower().startswith("warning:"):
                    unit["end"] = ranges[index + 1][1]
                    unit["ids"].append(items[index + 1]["id"])
                    unit["warning"] = (passage["id"], items[index + 1]["id"])
                    index += 1
            units.append(unit)
            index += 1
        out[doc_id] = {"words": words, "ranges": ranges, "passages": items, "units": units}
    return out


def oracle_fixed(stream, size, overlap):
    spans, start, total = [], 0, len(stream["words"])
    while start < total:
        end = min(start + size, total)
        spans.append((start, end))
        if end >= total:
            break
        start += size - overlap
    return spans


def oracle_violations(chunks, passages):
    spans = {}
    for item in chunks:
        spans.setdefault(item["doc_id"], []).append((item["start"], item["end"]))
    found = set()
    for doc_id, stream in oracle_stream(passages).items():
        for unit in stream["units"]:
            if unit["warning"] and not any(s <= unit["start"] and e >= unit["end"] for s, e in spans.get(doc_id, [])):
                found.add(unit["warning"])
    return found


def oracle_metrics(questions, coverage, k_values):
    totals = {"recall": {k: Fraction(0) for k in k_values}, "mrr": {k: Fraction(0) for k in k_values}}
    for question in questions:
        expected = set(question["expected"])
        for k in k_values:
            covered, first = set(), None
            for rank, chunk_id in enumerate(question["ranking"][:k], start=1):
                hits = expected & set(coverage[chunk_id])
                if hits and first is None:
                    first = rank
                covered |= hits
            totals["recall"][k] += Fraction(len(covered), len(expected))
            totals["mrr"][k] += Fraction(1, first) if first else Fraction(0)
    count = len(questions)
    return {name: {k: value / count for k, value in table.items()} for name, table in totals.items()}


def oracle_ranking(chunks, question_text):
    vectors = embed([item["text"] for item in chunks] + [question_text])
    scored = sorted(((-cosine(vectors[-1], vector), item["id"]) for item, vector in zip(chunks, vectors)))
    return [chunk_id for _, chunk_id in scored]


RNG = random.Random()
RUN = f"{RNG.randrange(16**5):05x}"
SECONDS = RNG.choice([45, 60, 90, 120, 150])
BAR = RNG.choice([2, 3, 4, 5])
DEGREES = RNG.choice([35, 40, 45, 50])
VALVE = RNG.randint(11, 97)
FILTER = RNG.randint(3, 29)
ANTENNA = RNG.choice(["north", "south", "east", "west"])
K_VALUES = RNG.choice([[1, 3, 5], [1, 2, 5], [1, 3, 10]])


def fixture():
    coolant, relay, incident = f"rb-coolant-{RUN}", f"rb-antenna-{RUN}", f"ir-outage-{RUN}"
    passages = [
        {"id": f"{coolant}#h1", "doc_id": coolant, "kind": "heading", "text": "Coolant loop restart"},
        {"id": f"{coolant}#p1", "doc_id": coolant, "kind": "paragraph", "text": "This runbook restarts the coolant loop of the relay after a planned stop. Every step is performed by the operator on shift."},
        {"id": f"{coolant}#s1", "doc_id": coolant, "kind": "step", "text": f"Step 1. Close the intake valve V-{VALVE} and confirm that the pressure gauge reads below {BAR} bar before continuing."},
        {"id": f"{coolant}#s2", "doc_id": coolant, "kind": "step", "text": "Step 2. Drain the reservoir into the holding tank through drain line D-2 and watch the level indicator.",
         "warning": f"Drain only when the loop temperature is under {DEGREES} degrees; hot coolant flashes to steam and scalds the operator."},
        {"id": f"{coolant}#s3", "doc_id": coolant, "kind": "step", "text": f"Step 3. Replace the particulate filter cartridge in housing F-{FILTER}, then tighten the clamp by hand."},
        {"id": f"{coolant}#p2", "doc_id": coolant, "kind": "paragraph", "text": f"Warning: The housing stays pressurised for {SECONDS} seconds after the pump stops. Wait that long before opening the clamp of the filter housing."},
        {"id": f"{coolant}#s4", "doc_id": coolant, "kind": "step", "text": "Step 4. Open the intake valve slowly and bleed air at the top vent until the coolant runs clear without bubbles."},
        {"id": f"{coolant}#s5", "doc_id": coolant, "kind": "step", "text": "Step 5. Record the restart in the relay journal together with the final gauge reading and the cartridge serial."},
        {"id": f"{coolant}#h2", "doc_id": coolant, "kind": "heading", "text": "Rollback"},
        {"id": f"{coolant}#p3", "doc_id": coolant, "kind": "paragraph", "text": "If the loop does not reach working pressure within ten minutes, close the intake valve again and open an incident report."},
        {"id": f"{relay}#h1", "doc_id": relay, "kind": "heading", "text": "Relay antenna alignment"},
        {"id": f"{relay}#p1", "doc_id": relay, "kind": "paragraph", "text": f"Align the {ANTENNA} antenna of the relay mast after a storm or whenever the signal margin drops below the floor."},
        {"id": f"{relay}#s1", "doc_id": relay, "kind": "step", "text": "Step 1. Lock the mast brake and attach the safety line to the harness anchor before climbing the ladder.",
         "warning": "Never climb the mast while the transmitter is powered; the radiated field burns skin within seconds."},
        {"id": f"{relay}#s2", "doc_id": relay, "kind": "step", "text": "Step 2. Loosen the azimuth bolts a quarter turn and rotate the dish until the signal meter peaks.",
         "warning": "Keep one hand on the mast rail while the dish rotates."},
        {"id": f"{relay}#p3", "doc_id": relay, "kind": "paragraph", "text": "Warning: A loose azimuth bolt lets the dish swing in the wind; check both bolts before leaving the platform."},
        {"id": f"{relay}#s3", "doc_id": relay, "kind": "step", "text": "Step 3. Tighten the azimuth bolts and the elevation bolts with the torque wrench at the marked value."},
        {"id": f"{relay}#p2", "doc_id": relay, "kind": "paragraph", "text": "Warning: An over-torqued elevation bolt cracks the bracket; stop at the first click of the wrench."},
        {"id": f"{relay}#s4", "doc_id": relay, "kind": "step", "text": "Step 4. Release the mast brake, climb down and log the new signal margin in the relay journal."},
        {"id": f"{incident}#h1", "doc_id": incident, "kind": "heading", "text": "Incident report: relay outage"},
        {"id": f"{incident}#p1", "doc_id": incident, "kind": "paragraph", "text": "The relay lost uplink for forty minutes during the night shift. The generator transfer switch had tripped on a voltage dip."},
        {"id": f"{incident}#p2", "doc_id": incident, "kind": "paragraph", "text": "Root cause: the transfer switch threshold was left at the factory default after the generator service. Action: set the threshold per the generator runbook."},
    ]
    questions = [
        {"id": f"q-{RUN}-1", "text": "How long does the filter housing stay pressurised after the pump stops, and when may I open the clamp of the housing?", "expected": [f"{coolant}#s3", f"{coolant}#p2"]},
        {"id": f"q-{RUN}-2", "text": "Which valve do I close first and what should the pressure gauge read?", "expected": [f"{coolant}#s1"]},
        {"id": f"q-{RUN}-3", "text": "Under which temperature must the loop be before draining the reservoir into the holding tank?", "expected": [f"{coolant}#s2"]},
        {"id": f"q-{RUN}-4", "text": "Why must the transmitter be off before climbing the mast with the safety line?", "expected": [f"{relay}#s1"]},
        {"id": f"q-{RUN}-5", "text": "How tight do the elevation bolts go with the torque wrench?", "expected": [f"{relay}#s3", f"{relay}#p2"]},
        {"id": f"q-{RUN}-6", "text": "What tripped the generator transfer switch during the outage?", "expected": [f"{incident}#p1", f"{incident}#p2"]},
    ]
    return passages, questions, (coolant, relay, incident)


def long_runbook(doc_id, sections, size):
    """A generated runbook: sections of steps with field and paragraph warnings, every unit well under size."""
    verbs = ["Close", "Open", "Inspect", "Tighten", "Record", "Flush", "Measure", "Isolate", "Reset", "Label"]
    objects = ["the bypass valve", "the pressure gauge", "the relay breaker", "the fuel line", "the coolant pump", "the mast brake", "the signal meter", "the drain clamp"]
    passages = []
    for section in range(sections):
        passages.append({"id": f"{doc_id}#h{section}", "doc_id": doc_id, "kind": "heading", "text": f"Section {section + 1}: {verbs[section % len(verbs)]} procedure"})
        passages.append({"id": f"{doc_id}#p{section}", "doc_id": doc_id, "kind": "paragraph", "text": f"This section covers {objects[section % len(objects)]} of outpost unit {section * 7 % 13 + 1} and takes about {section % 5 + 3} minutes."})
        for step in range(5):
            text = f"Step {step + 1}. {verbs[(section + step) % len(verbs)]} {objects[(section * 3 + step) % len(objects)]} and confirm reading {section * 5 + step} on the panel before moving on."
            passage = {"id": f"{doc_id}#s{section}-{step}", "doc_id": doc_id, "kind": "step", "text": text}
            if step % 3 == 1:
                passage["warning"] = f"Keep hands clear of {objects[(section + step) % len(objects)]} while it moves."
            passages.append(passage)
            if step % 3 == 2:
                passages.append({"id": f"{doc_id}#w{section}-{step}", "doc_id": doc_id, "kind": "paragraph", "text": f"Warning: {objects[(section * 3 + step) % len(objects)]} stays live for {section % 9 + 2} seconds after the switch."})
    stream = oracle_stream(passages)[doc_id]
    require(max(unit["end"] - unit["start"] for unit in stream["units"]) < size, "fixture: every generated unit must fit the size bound")
    return passages


def trial():
    require(MISSION == "chunking", "Unknown mission")
    sys.path.insert(0, WORKSPACE)
    spec = importlib.util.spec_from_file_location("candidate_chunking", os.path.join(WORKSPACE, "chunker.py"))
    if spec is None or spec.loader is None:
        raise ImportError("Cannot load chunker.py")
    candidate = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = candidate
    spec.loader.exec_module(candidate)
    for name in ("chunk", "evaluate", "metrics", "choose", "audit"):
        require(callable(getattr(candidate, name, None)), f"chunker.py must define {name}(...)")

    passages, questions, (coolant, relay, incident) = fixture()
    streams = oracle_stream(passages)
    planted = next(unit for unit in streams[coolant]["units"] if unit["warning"] == (f"{coolant}#s3", f"{coolant}#p2"))

    def run_chunk(strategy, size, overlap=0, items=None, **extra):
        items = passages if items is None else items
        chunks = candidate.chunk(copy.deepcopy(items), strategy, size=size, overlap=overlap, **extra)
        require(isinstance(chunks, list) and chunks, f"chunk({strategy!r}) must return a non-empty list")
        ids = []
        for item in chunks:
            require(isinstance(item, dict), "every chunk is a dict")
            for key in ("id", "doc_id", "strategy", "start", "end", "text", "passage_ids"):
                require(key in item, f"chunk is missing {key!r}: {item!r}"[:300])
            require(isinstance(item["id"], str) and item["id"], "chunk id must be a non-empty string")
            require(item["strategy"] == strategy, f"chunk strategy must be {strategy!r}, got {item['strategy']!r}")
            require(type(item["start"]) is int and type(item["end"]) is int and 0 <= item["start"] < item["end"], f"start/end must be integers with start < end: {item['start']!r}, {item['end']!r}")
            require(isinstance(item["passage_ids"], list), "passage_ids must be a list")
            ids.append(item["id"])
        require(len(set(ids)) == len(ids), "chunk ids must be unique within one chunk() result")
        return chunks

    def verify_slices(chunks, items):
        local = oracle_stream(items)
        for item in chunks:
            stream = local.get(item["doc_id"])
            require(stream is not None, f"unknown doc_id {item['doc_id']!r}")
            require(item["end"] <= len(stream["words"]), f"chunk {item['id']} ends at {item['end']} beyond the {len(stream['words'])}-word stream of {item['doc_id']}")
            require(item["text"].split() == stream["words"][item["start"]:item["end"]], f"chunk {item['id']}: text must be the words {item['start']}..{item['end']} of the document stream (passage text, then 'Warning: <warning>' for a warning field)")
            wanted = [p["id"] for p, (lo, hi) in zip(stream["passages"], stream["ranges"]) if lo < item["end"] and hi > item["start"]]
            require(item["passage_ids"] == wanted, f"chunk {item['id']} covers words {item['start']}..{item['end']}: passage_ids must be {wanted}, got {item['passage_ids']}")

    def by_doc(chunks):
        grouped = {}
        for item in chunks:
            grouped.setdefault(item["doc_id"], []).append(item)
        return grouped

    def fixed():
        size, overlap = RNG.randint(24, 40), RNG.randint(4, 10)
        for ov in (0, overlap):
            chunks = run_chunk("fixed", size, ov)
            verify_slices(chunks, passages)
            grouped = by_doc(chunks)
            require(set(grouped) == set(streams), f"fixed chunks must cover every document: {sorted(streams)}")
            for doc_id, stream in streams.items():
                spans = [(item["start"], item["end"]) for item in grouped[doc_id]]
                require(spans == oracle_fixed(stream, size, ov), f"{doc_id}, size {size}, overlap {ov}: windows must start every {size - ov} words until one reaches the end; got {spans}")
        for bad in (size, size + 3, -1):
            try:
                candidate.chunk(copy.deepcopy(passages), "fixed", size=size, overlap=bad)
            except ValueError:
                continue
            raise AssertionError(f"overlap {bad} with size {size} must raise ValueError")
        try:
            candidate.chunk(copy.deepcopy(passages), "sliding", size=size)
        except ValueError:
            return f"Size {size}, overlap 0 and {overlap}: every window is the exact stream slice with the right coverage ids; invalid overlap and strategy rejected."
        raise AssertionError("an unknown strategy must raise ValueError")
    check("Fixed chunks follow size, overlap and the word stream", fixed)

    def structural_invariants(chunks, items, size, strategy="structural"):
        verify_slices(chunks, items)
        local = oracle_stream(items)
        grouped = by_doc(chunks)
        require(set(grouped) == set(local), "chunks must cover every document")
        for doc_id, stream in local.items():
            own = sorted(grouped[doc_id], key=lambda item: item["start"])
            starts = {unit["start"]: unit for unit in stream["units"]}
            ends = {unit["end"] for unit in stream["units"]}
            cursor = 0
            for item in own:
                require(item["start"] == cursor, f"{doc_id}: {strategy} chunks must be contiguous and disjoint; a chunk starts at {item['start']} but the previous ended at {cursor}")
                require(item["start"] in starts and item["end"] in ends, f"{doc_id}: chunk {item['id']} cuts inside a unit (words {item['start']}..{item['end']}); cut only between a step-with-warning unit and the next passage")
                single = starts[item["start"]]["end"] == item["end"]
                require(item["end"] - item["start"] <= size or single, f"{doc_id}: chunk {item['id']} holds {item['end'] - item['start']} words over the size {size} and is not a single unit")
                cursor = item["end"]
            require(cursor == len(stream["words"]), f"{doc_id}: the last chunk must reach the end of the stream ({cursor} of {len(stream['words'])} words)")
        require(not oracle_violations(chunks, items), f"{strategy}: a step was separated from its warning")
        return grouped

    def structural():
        size = RNG.randint(28, 44)
        chunks = run_chunk("structural", size)
        grouped = structural_invariants(chunks, passages, size)
        for doc_id, stream in streams.items():
            own = sorted(grouped[doc_id], key=lambda item: item["start"])
            units = {unit["start"]: unit for unit in stream["units"]}
            for previous, following in zip(own, own[1:]):
                nxt = units[following["start"]]
                if nxt["kind"] != "heading":
                    require(previous["end"] - previous["start"] + nxt["end"] - nxt["start"] > size, f"{doc_id}: chunk {previous['id']} closed early although the next unit ({nxt['ids']}) is not a heading and still fits in {size} words")
        require(candidate.audit(copy.deepcopy(chunks), copy.deepcopy(passages)) == [], "audit must return [] for structural chunks")
        require(len(chunks) > len(streams), "structural chunking at this size must produce more than one chunk per document")
        return f"Size {size}: {len(chunks)} chunks, whole passages only, every step kept with its warning, no early cut before a non-heading unit."
    check("Structural chunks never separate a step from its warning", structural)

    def audit():
        stream = streams[coolant]
        only = [p for p in passages if p["doc_id"] == coolant]
        step2 = next(unit for unit in stream["units"] if unit["warning"] == (f"{coolant}#s2", f"{coolant}#s2"))
        total = len(stream["words"])

        def handmade(spans):
            return [{"id": f"hand/{index}", "doc_id": coolant, "strategy": "fixed", "start": s, "end": e, "text": " ".join(stream["words"][s:e]),
                     "passage_ids": [p["id"] for p, (lo, hi) in zip(stream["passages"], stream["ranges"]) if lo < e and hi > s]} for index, (s, e) in enumerate(spans)]

        def names(found):
            return sorted((item.get("step_id"), item.get("warning_id")) for item in found)

        mid_planted = planted["start"] + (planted["end"] - planted["start"]) // 2
        mid_step2 = step2["start"] + (step2["end"] - step2["start"]) // 2
        split_both = handmade([(0, mid_step2), (mid_step2, mid_planted), (mid_planted, total)])
        found = candidate.audit(copy.deepcopy(split_both), copy.deepcopy(only))
        require(isinstance(found, list) and all(isinstance(item, dict) for item in found), "audit must return a list of dicts")
        require(names(found) == sorted([(f"{coolant}#s2", f"{coolant}#s2"), (f"{coolant}#s3", f"{coolant}#p2")]), f"two separated units expected (a warning field cut from its step, a Warning paragraph cut from its step), got {found!r}")
        for item in found:
            require(item.get("doc_id") == coolant, "each violation names doc_id")
        whole = handmade([(0, planted["start"]), (planted["start"], planted["end"]), (planted["end"], total)])
        require(candidate.audit(copy.deepcopy(whole), copy.deepcopy(only)) == [], "cutting exactly around the step+warning unit is no violation")
        step1 = stream["units"][2]
        require(step1["warning"] is None, "fixture: step 1 has no warning")
        mid_step1 = step1["start"] + 3
        plain = handmade([(0, mid_step1), (mid_step1, total)])
        require(candidate.audit(copy.deepcopy(plain), copy.deepcopy(only)) == [], "a step without a warning may be cut; audit reports only separated warnings")
        partial = handmade([(0, planted["end"] - 2), (planted["end"] - 2, total)])
        require(names(candidate.audit(copy.deepcopy(partial), copy.deepcopy(only))) == [(f"{coolant}#s3", f"{coolant}#p2")], "a chunk that holds the step and only part of its Warning paragraph still separates them")
        antenna = streams[relay]
        both = next(index for index, unit in enumerate(antenna["units"]) if unit["warning"] == (f"{relay}#s2", f"{relay}#s2"))
        require(antenna["units"][both + 1]["kind"] == "paragraph" and antenna["units"][both + 1]["warning"] is None, "fixture: the paragraph after a step with a warning field is its own unit")
        edge = antenna["units"][both]["end"]
        relay_only = [p for p in passages if p["doc_id"] == relay]
        around = [{"id": f"edge/{index}", "doc_id": relay, "strategy": "fixed", "start": s, "end": e, "text": " ".join(antenna["words"][s:e]),
                   "passage_ids": [p["id"] for p, (lo, hi) in zip(antenna["passages"], antenna["ranges"]) if lo < e and hi > s]}
                  for index, (s, e) in enumerate([(0, edge), (edge, len(antenna["words"]))])]
        got = names(candidate.audit(copy.deepcopy(around), copy.deepcopy(relay_only)))
        require(got == [], f"a step with a warning field does not absorb the following Warning paragraph: cutting between them is no violation, got {got}")
        inside = [{**item} for item in around]
        inside[0]["end"], inside[1]["start"] = edge - 2, edge - 2
        for item in inside:
            item["text"] = " ".join(antenna["words"][item["start"]:item["end"]])
            item["passage_ids"] = [p["id"] for p, (lo, hi) in zip(antenna["passages"], antenna["ranges"]) if lo < item["end"] and hi > item["start"]]
        got = names(candidate.audit(copy.deepcopy(inside), copy.deepcopy(relay_only)))
        require(got == [(f"{relay}#s2", f"{relay}#s2")], f"cutting two words before the end of that step's own warning field separates it, got {got}")
        size, overlap = RNG.randint(24, 40), RNG.randint(0, 6)
        chunks = run_chunk("fixed", size, overlap)
        verify_slices(chunks, passages)
        wanted = sorted(oracle_violations(chunks, passages))
        got = names(candidate.audit(copy.deepcopy(chunks), copy.deepcopy(passages)))
        require(got == wanted, f"fixed chunks of size {size}, overlap {overlap}: audit must report exactly {wanted}, got {got}")
        return f"Hand-cut chunks: both warning forms reported when split, none when whole, a field-step keeps a following Warning paragraph separate; fixed size {size} overlap {overlap} reported {len(wanted)} separated units."
    check("audit reports every step separated from its warning", audit)

    def run_evaluate(chunks):
        report = candidate.evaluate(copy.deepcopy(chunks), copy.deepcopy(questions), embed, list(K_VALUES))
        require(isinstance(report, dict), "evaluate must return a dict")
        for key in ("strategy", "k_values", "chunk_count", "avg_words", "coverage", "questions", "recall", "mrr"):
            require(key in report, f"report is missing {key!r}")
        require([int(k) for k in report["k_values"]] == K_VALUES, "report.k_values echoes the k values")
        require(report["chunk_count"] == len(chunks), f"chunk_count must be {len(chunks)}")
        words = Fraction(sum(len(item["text"].split()) for item in chunks), len(chunks))
        require(abs(Fraction(str(report["avg_words"])) - words) <= Fraction(1, 10**6), f"avg_words must be {float(words)!r}")
        require(report["coverage"] == {item["id"]: item["passage_ids"] for item in chunks}, "coverage maps every chunk id to its passage_ids")
        require(isinstance(report["questions"], list) and len(report["questions"]) == len(questions), "one row per question, in order")
        all_ids = sorted(item["id"] for item in chunks)
        for row, question in zip(report["questions"], questions):
            require(row.get("id") == question["id"] and row.get("expected") == question["expected"], "each row carries the question id and its expected passage ids")
            require(sorted(row.get("ranking", [])) == all_ids, f"ranking for {question['id']} must list every chunk id exactly once")
            require(row["ranking"] == oracle_ranking(chunks, question["text"]), f"ranking for {question['id']} must be sorted by cosine similarity (descending) with ties broken by chunk id ascending")
        return report

    def aggregates(report):
        out = {}
        for name in ("recall", "mrr"):
            table = report[name]
            require(isinstance(table, dict), f"report.{name} must be a dict keyed by k")
            out[name] = {}
            for k in K_VALUES:
                value = table.get(str(k), table.get(k))
                require(isinstance(value, (int, float, Fraction)) and not isinstance(value, bool), f"report.{name}[{k!r}] must be a number")
                out[name][k] = Fraction(str(value))
        return out

    def same(left, right, label):
        for name in ("recall", "mrr"):
            for k in K_VALUES:
                require(abs(left[name][k] - right[name][k]) <= TOLERANCE, f"{label}: {name}@{k} is {float(left[name][k])!r}, expected {float(right[name][k])!r}")

    reports = {}

    def recompute():
        size = RNG.randint(24, 40)
        for strategy in ("fixed", "structural"):
            chunks = run_chunk(strategy, size, overlap=RNG.randint(0, 6) if strategy == "fixed" else 0)
            verify_slices(chunks, passages)
            report = run_evaluate(chunks)
            require(report["strategy"] == strategy, f"report.strategy must be {strategy!r}")
            wanted = oracle_metrics(report["questions"], report["coverage"], K_VALUES)
            same(aggregates(report), wanted, f"{strategy} aggregates")
            same(aggregates(candidate.metrics(copy.deepcopy(report))), wanted, f"metrics({strategy} report)")
            reports[strategy] = report
        tampered = copy.deepcopy(reports["fixed"])
        tampered["recall"] = {str(k): 0.0 for k in K_VALUES}
        tampered["mrr"] = {str(k): 0.0 for k in K_VALUES}
        wanted = oracle_metrics(tampered["questions"], tampered["coverage"], K_VALUES)
        require(any(value != 0 for table in wanted.values() for value in table.values()), "fixture: the tampered aggregates differ from the truth")
        same(aggregates(candidate.metrics(copy.deepcopy(tampered))), wanted, "metrics() on a report with tampered aggregates must recompute from the rankings")
        fixed_report = reports["fixed"]
        return f"Size {size}: rankings match cosine order; recall@{K_VALUES[0]} {float(fixed_report['recall'].get(str(K_VALUES[0]), 0)):.3f} fixed, recomputed with Fractions; tampered aggregates ignored by metrics()."
    check("Recall@k and MRR@k recompute from the raw rankings", recompute)

    def synthetic_report(strategy, rankings, coverage, chunk_count, avg_words):
        rows = [{"id": f"s{index}", "expected": expected, "ranking": ranking} for index, (expected, ranking) in enumerate(rankings)]
        report = {"strategy": strategy, "k_values": [1, 2], "chunk_count": chunk_count, "avg_words": avg_words, "coverage": coverage, "questions": rows}
        truth = oracle_metrics(rows, coverage, [1, 2])
        report["recall"] = {str(k): float(v) for k, v in truth["recall"].items()}
        report["mrr"] = {str(k): float(v) for k, v in truth["mrr"].items()}
        return report, truth

    def chosen():
        coverage = {"a": ["p1"], "b": ["p2"], "c": ["p3"], "d": ["p1", "p2"], "e": ["p4"]}
        # recall@1: rich 1.0; lean 0.75 (second question hits half); mid 0.75 at a higher average size; poor 0.25, but 1.0 at k=2.
        rich, rich_truth = synthetic_report("rich", [(["p1"], ["a", "b", "c"]), (["p1", "p2"], ["d", "e", "c"])], coverage, 40, 30.0)
        lean, lean_truth = synthetic_report("lean", [(["p1"], ["a", "b", "c"]), (["p1", "p2"], ["a", "e", "b"])], coverage, 10, 28.0)
        mid, _ = synthetic_report("mid", [(["p1"], ["a", "b", "c"]), (["p1", "p2"], ["b", "a", "e"])], coverage, 10, 31.5)
        poor, poor_truth = synthetic_report("poor", [(["p1"], ["b", "a", "c"]), (["p1", "p2"], ["a", "b", "e"])], coverage, 4, 12.0)
        require(rich_truth["recall"][1] == 1 and lean_truth["recall"][1] == Fraction(3, 4) and poor_truth["recall"] == {1: Fraction(1, 4), 2: Fraction(1)}, "fixture: synthetic recalls")
        target = 0.7
        decision = candidate.choose(copy.deepcopy([rich, lean, mid, poor]), target, k=1)
        require(isinstance(decision, dict), "choose must return a dict")
        require(decision.get("strategy") == "lean", f"target {target} at k=1: lean (recall 0.75, 10 chunks of 28 words) is the cheapest strategy meeting the target, got {decision.get('strategy')!r}")
        require(decision.get("k") == 1 and abs(float(decision.get("target_recall", -1)) - target) < 1e-9, "decision carries k and target_recall")
        candidates = decision.get("candidates")
        require(isinstance(candidates, list) and [item.get("strategy") for item in candidates] == ["rich", "lean", "mid", "poor"], "decision.candidates lists every report in order")
        for item, wanted in zip(candidates, [(1, True, 40), (Fraction(3, 4), True, 10), (Fraction(3, 4), True, 10), (Fraction(1, 4), False, 4)]):
            require(abs(Fraction(str(item.get("recall"))) - wanted[0]) <= TOLERANCE, f"candidate {item.get('strategy')} must cite recall {float(wanted[0])}")
            require(item.get("meets") is wanted[1] and item.get("chunk_count") == wanted[2], f"candidate {item.get('strategy')} must cite meets={wanted[1]} and chunk_count {wanted[2]}")
        require(isinstance(decision.get("reason"), str) and "lean" in decision["reason"] and "0.75" in decision["reason"], "reason names the chosen strategy and its recall")
        require(candidate.choose(copy.deepcopy([rich, poor]), 0.8, k=1).get("strategy") == "rich", "when only the expensive strategy meets the target it is chosen")
        require(candidate.choose(copy.deepcopy([lean, mid, poor]), 0.9, k=1).get("strategy") is None, "strategy is None when no report meets the target")
        require(candidate.choose(copy.deepcopy([lean, poor]), 1.0, k=2).get("strategy") == "poor", "at k=2 poor reaches recall 1.0 with four chunks and wins")
        forged = copy.deepcopy(poor)
        forged["recall"] = {"1": 1.0, "2": 1.0}
        decision = candidate.choose(copy.deepcopy([lean, forged]), 0.7, k=1)
        require(decision.get("strategy") == "lean", "choose must recompute recall from the rankings: a report with forged aggregates (poor claiming 1.0) must not win")
        forged_row = next(item for item in decision["candidates"] if item["strategy"] == "poor")
        require(abs(Fraction(str(forged_row["recall"])) - Fraction(1, 4)) <= TOLERANCE, "the forged candidate is cited with its recomputed recall 0.25")
        return "Cheapest strategy meeting the target chosen at k=1 and k=2; None when nothing meets it; forged aggregates recomputed."
    check("The chosen strategy meets the declared recall at the lowest cost", chosen)

    def retrievable():
        require("structural" in reports and "fixed" in reports, "the recompute check must pass first")
        unit_length = planted["end"] - planted["start"]
        # Find a size where fixed chunking cuts the planted unit while structural keeps it, so that the declared recall separates them.
        choice = None
        for size in range(max(24, unit_length - 6), unit_length + 12):
            for overlap in (0, 4, 8):
                if oracle_violations([{"doc_id": coolant, "start": s, "end": e} for s, e in oracle_fixed(streams[coolant], size, overlap)], passages) >= {planted["warning"]}:
                    choice = (size, overlap)
                    break
            if choice:
                break
        require(choice, "fixture: a fixed size that cuts the planted unit")
        size, overlap = choice
        fixed_chunks = run_chunk("fixed", size, overlap)
        structural_chunks = run_chunk("structural", size)
        verify_slices(fixed_chunks, passages)
        structural_invariants(structural_chunks, passages, size)
        fixed_report = run_evaluate(fixed_chunks)
        structural_report = run_evaluate(structural_chunks)
        k = K_VALUES[0]
        truth_fixed = oracle_metrics(fixed_report["questions"], fixed_report["coverage"], [k])["recall"][k]
        truth_structural = oracle_metrics(structural_report["questions"], structural_report["coverage"], [k])["recall"][k]
        same(aggregates(fixed_report), oracle_metrics(fixed_report["questions"], fixed_report["coverage"], K_VALUES), "fixed aggregates")
        same(aggregates(structural_report), oracle_metrics(structural_report["questions"], structural_report["coverage"], K_VALUES), "structural aggregates")
        planted_row = next(row for row in structural_report["questions"] if row["id"] == questions[0]["id"])
        top = structural_report["coverage"][planted_row["ranking"][0]]
        require(set(questions[0]["expected"]) <= set(top), f"the question about the filter housing must retrieve one structural chunk holding both the step and its warning at rank 1; the top chunk covers {top}")
        require(truth_structural > truth_fixed, f"fixture: structural recall@{k} {float(truth_structural):.3f} must exceed fixed {float(truth_fixed):.3f} at size {size}")
        target = math.floor(float(truth_structural) * 100) / 100
        require(target > truth_fixed, "fixture: the declared target separates the strategies")
        decision = candidate.choose(copy.deepcopy([fixed_report, structural_report]), target, k=k)
        require(decision.get("strategy") == "structural", f"with target recall@{k} {target} only structural ({float(truth_structural):.3f}) meets it; fixed reaches {float(truth_fixed):.3f}; got {decision.get('strategy')!r}")
        return f"Size {size}: fixed recall@{k} {float(truth_fixed):.3f} cuts the filter step from its warning; structural {float(truth_structural):.3f} meets the declared {target} and is chosen."
    check("A procedure step stays retrievable with its warning", retrievable)

    def longer():
        size, overlap = RNG.randint(30, 44), RNG.randint(0, 8)
        sections = RNG.randint(80, 95)
        doc_id = f"rb-long-{RUN}"
        items = long_runbook(doc_id, sections, size)
        stream = oracle_stream(items)[doc_id]
        base = len(streams[coolant]["words"])
        require(len(stream["words"]) >= 50 * base, "fixture: the generated runbook is at least fifty times the coolant runbook")
        started = time.perf_counter()
        fixed_chunks = run_chunk("fixed", size, overlap, items=items)
        structural_chunks = run_chunk("structural", size, items=items)
        elapsed = time.perf_counter() - started
        require(elapsed < 8, f"chunking {len(stream['words'])} words took {elapsed:.1f} s; keep it linear")
        verify_slices(fixed_chunks, items)
        require([(c["start"], c["end"]) for c in fixed_chunks] == oracle_fixed(stream, size, overlap), "fixed windows on the long runbook must follow the stride rule")
        structural_invariants(structural_chunks, items, size)
        require(all(item["end"] - item["start"] <= size for item in structural_chunks), f"every structural chunk of the long runbook fits in {size} words")
        covered = set()
        for item in structural_chunks:
            covered.update(item["passage_ids"])
        require(covered == {p["id"] for p in items}, "every passage of the long runbook is covered by a structural chunk")
        require(candidate.audit(copy.deepcopy(structural_chunks), copy.deepcopy(items)) == [], "structural chunks of the long runbook keep every step with its warning")
        found = candidate.audit(copy.deepcopy(fixed_chunks), copy.deepcopy(items))
        wanted = oracle_violations(fixed_chunks, items)
        require(sorted((v.get("step_id"), v.get("warning_id")) for v in found) == sorted(wanted), "audit on the long runbook reports exactly the separated units")
        return f"{len(stream['words'])} words ({len(stream['words']) // base}x the coolant runbook), {sections} sections: {len(fixed_chunks)} fixed and {len(structural_chunks)} structural chunks in {elapsed * 1000:.0f} ms, all under {size} words, {len(wanted)} separations in fixed and none in structural."
    check("A fifty-times longer runbook chunks under the same guarantees", longer)

    def semantic():
        size = RNG.randint(60, 72)
        # Threshold inside the spread of adjacent-unit similarities, so that cuts and joins both exist.
        sims = []
        for stream in streams.values():
            vectors = embed([" ".join(stream["words"][u["start"]:u["end"]]) for u in stream["units"]])
            sims.extend(cosine(a, b) for a, b in zip(vectors, vectors[1:]))
        ordered = sorted(sims)
        threshold = round((ordered[len(ordered) // 3] + ordered[len(ordered) // 3 + 1]) / 2, 4)
        chunks = run_chunk("semantic", size, embed=embed, threshold=threshold)
        grouped = structural_invariants(chunks, passages, size, strategy="semantic")
        cuts = joins = 0
        for doc_id, stream in streams.items():
            units = stream["units"]
            vectors = embed([" ".join(stream["words"][u["start"]:u["end"]]) for u in units])
            own = sorted(grouped[doc_id], key=lambda item: item["start"])
            boundaries = {item["start"] for item in own[1:]}
            for index in range(1, len(units)):
                similarity = cosine(vectors[index - 1], vectors[index])
                here = units[index]["start"]
                if here in boundaries:
                    closed = next(item for item in own if item["end"] == here)
                    overflow = closed["end"] - closed["start"] + units[index]["end"] - units[index]["start"] > size
                    require(similarity < threshold - 1e-9 or overflow, f"{doc_id}: a semantic cut at word {here} although adjacent similarity {similarity:.3f} >= threshold {threshold} and the unit still fits")
                    cuts += 1
                else:
                    require(similarity >= threshold - 1e-9, f"{doc_id}: no cut at word {here} although adjacent similarity {similarity:.3f} < threshold {threshold}")
                    joins += 1
        require(cuts and joins, "the threshold must produce both cuts and joins")
        return f"Threshold {threshold}, size {size}: {cuts} cuts where adjacent similarity dropped, {joins} joins where it held; no step separated from its warning."
    check("bonus: semantic chunking cuts where adjacent similarity drops", semantic, optional=True)


try:
    trial()
except Exception as error:
    CHECKS.append({"name": "Load chunker", "passed": False, "detail": f"{type(error).__name__}: {error}"[:1500]})
print(json.dumps({"checks": CHECKS}))
sys.exit(0 if CHECKS and all(item["passed"] for item in CHECKS if not item.get("optional")) else 1)
