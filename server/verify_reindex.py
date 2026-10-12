"""Incremental indexer checks for the Reindex mission; run outside the learner workspace.

Nothing here calls a model. The embedding function is injected: a hashed bag of words salted with the model
name, a labeled test tool that counts every call. Verify owns the documents, the SQLite file and the oracle:
it recomputes every chunk from the published rule, every top-k from its own vectors, and reads the file from
its own connection between calls. A trigger installed by Verify injects a failure into the activation
statement; a fresh process reopens the file for the persistence check.
"""
import hashlib
import importlib.util
import json
import math
import os
import random
import re
import sqlite3
import subprocess
import sys

MISSION, WORKSPACE = sys.argv[1:3]
CHECKS = []
ALL = 1000

EMBED_SOURCE = r'''
import hashlib, math, re
DIMENSIONS = 96
def embed_vectors(texts, model):
    vectors = []
    for text in texts:
        vector = [0.0] * DIMENSIONS
        for token in re.findall(r"[a-z0-9]+", str(text).lower()):
            if len(token) < 3:
                continue
            digest = hashlib.sha256(f"{model}:{token}".encode("utf-8")).hexdigest()
            vector[int(digest[:8], 16) % DIMENSIONS] += 1.0 if int(digest[8], 16) % 2 == 0 else -1.0
        norm = math.sqrt(sum(value * value for value in vector))
        vectors.append([value / norm for value in vector] if norm else vector)
    return vectors
'''
exec(EMBED_SOURCE)  # defines embed_vectors for the verifier process


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def check(name, operation, optional=False):
    # An optional check is the hidden bonus of a mission: it can only add, it never fails the run.
    flag = {"optional": True} if optional else {}
    try:
        detail = operation()
        CHECKS.append({"name": name, "passed": True, "detail": detail or "Index state and answers verified against the file.", **flag})
    except Exception as error:
        CHECKS.append({"name": name, "passed": False, "detail": f"{type(error).__name__}: {error}"[:1500], **flag})


class Embedder:
    """The injected embedding function: deterministic per model name, counts every call. Never a model."""

    def __init__(self):
        self.calls = []

    def __call__(self, texts, *, model):
        require(isinstance(texts, list) and all(isinstance(text, str) for text in texts), "embed takes a list of str")
        require(isinstance(model, str) and model, "embed needs the model name as keyword argument")
        self.calls.append((model, len(texts)))
        return embed_vectors(texts, model)

    def since(self, mark):
        return self.calls[mark:]


def cosine(left, right):
    dot = sum(a * b for a, b in zip(left, right))
    norm = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
    return dot / norm if norm else 0.0


# Oracle: the published chunk rule, recomputed independently of the learner module.
def passages(content):
    return [part.strip() for part in re.split(r"\n\s*\n", content.strip()) if part.strip()]


def oracle_chunks(content, width):
    parts = passages(content)
    return ["\n\n".join(parts[start:start + width]) for start in range(0, len(parts), width)]


def squash(text):
    return " ".join(str(text).split())


class Oracle:
    """Verify's own model of the archive: documents, index versions and what each one must answer."""

    def __init__(self):
        self.documents = {}  # doc_id -> {"version", "content", "deleted"}
        self.versions = {}  # name -> {"model", "width", "held": {doc_id: (doc_version, content)}}

    def upsert(self, doc_id, content, active):
        entry = self.documents.get(doc_id)
        if entry and entry["content"] == content and not entry["deleted"]:
            return False
        version = entry["version"] + 1 if entry else 1
        self.documents[doc_id] = {"version": version, "content": content, "deleted": False}
        self.versions[active]["held"][doc_id] = (version, content)
        return True

    def delete(self, doc_id):
        self.documents[doc_id]["deleted"] = True

    def rebuild(self, name, model, width):
        held = {doc_id: (entry["version"], entry["content"]) for doc_id, entry in self.documents.items() if not entry["deleted"]}
        self.versions[name] = {"model": model, "width": width, "held": held}

    def reachable(self, name):
        version = self.versions[name]
        rows = []
        for doc_id, (doc_version, content) in sorted(version["held"].items()):
            current = self.documents.get(doc_id)
            if current is None or current["deleted"] or current["version"] != doc_version:
                continue
            for number, text in enumerate(oracle_chunks(content, version["width"])):
                rows.append((doc_id, doc_version, number, text))
        return rows

    def expected_chunks(self, name):
        return len(self.reachable(name))

    def ranked(self, name, query):
        version = self.versions[name]
        rows = self.reachable(name)
        vectors = embed_vectors([row[3] for row in rows] + [query], version["model"])
        scored = [(cosine(vectors[-1], vectors[index]), row) for index, row in enumerate(rows)]
        scored.sort(key=lambda pair: (-pair[0], pair[1][0], pair[1][2]))
        return scored

    def missing(self, name):
        held = self.versions[name]["held"]
        return sorted(doc_id for doc_id, entry in self.documents.items() if not entry["deleted"] and held.get(doc_id, (None,))[0] != entry["version"])


def fixtures(rng):
    code, code2 = (f"K-{rng.randint(1000, 4999)}", f"K-{rng.randint(5000, 9999)}")
    bay, fuse, days = rng.randint(11, 99), rng.randint(20, 80), rng.randint(5, 30)
    incident = rng.randint(100, 999)
    liters = rng.randint(200, 900)
    docs = {
        "RB-power": "Runbook: power dip on the relay.\n\n"
                    f"Step 1. Confirm the dip on the panel and read fuse F{fuse}; the relay fuse rotates every {days} days.\n\n"
                    f"Step 2. Switch the relay to the reserve battery in bay {bay} and log the access code {code} in the shift journal.\n\n"
                    "Warning: never reset the relay while the reserve battery is still charging.",
        "RB-water": "Runbook: water purifier filters.\n\n"
                    f"Replace the purifier cartridge after {liters} liters or when the turbidity lamp blinks amber.\n\n"
                    "Order replacement cartridges from the supplies desk two weeks before the expected change.",
        "RB-reserve": "Runbook: reserving supplies.\n\n"
                      "Only an operator with the reservation permission may hold stock; the assistant reserves under that operator's name.\n\n"
                      "A reservation older than three shifts is released automatically by the ledger.",
        f"IR-{incident}": f"Incident report {incident}: the relay dropped twice during the night shift.\n\n"
                          "Cause: a loose terminal on the reserve battery. Fixed by the morning crew; the terminal was replaced.",
    }
    updated_power = ("Runbook: power dip on the relay, revised after the night incident.\n\n"
                     f"Switch the relay to the reserve battery in bay {bay}, log the access code {code2} in the shift journal and call the morning crew.")
    return docs, updated_power, code, code2, f"IR-{incident}"


def db(path):
    connection = sqlite3.connect(path, timeout=1.0)
    connection.row_factory = sqlite3.Row
    return connection


def version_rows(path):
    with db(path) as connection:
        rows = connection.execute("SELECT version, embed_model, chunking_version, active FROM index_versions").fetchall()
    connection.close()
    return [dict(row) for row in rows]


def active_version(path):
    rows = [row for row in version_rows(path) if row["active"] == 1]
    require(len(rows) == 1, f"index_versions must hold exactly one active row, found {len(rows)}: {version_rows(path)}")
    return rows[0]["version"]


def document_row(path, doc_id):
    with db(path) as connection:
        row = connection.execute("SELECT * FROM documents WHERE doc_id = ?", (doc_id,)).fetchone()
    connection.close()
    return dict(row) if row is not None else None


def sql_literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def install_refusal(path, version):
    with db(path) as connection:
        connection.execute(f"CREATE TRIGGER verify_refuse_update BEFORE UPDATE OF active ON index_versions FOR EACH ROW "
                           f"WHEN NEW.active = 1 AND NEW.version = {sql_literal(version)} BEGIN SELECT RAISE(ABORT, 'verify: activation refused'); END")
        connection.execute(f"CREATE TRIGGER verify_refuse_insert BEFORE INSERT ON index_versions FOR EACH ROW "
                           f"WHEN NEW.active = 1 AND NEW.version = {sql_literal(version)} BEGIN SELECT RAISE(ABORT, 'verify: activation refused'); END")
    connection.close()


def remove_refusal(path):
    try:
        with db(path) as connection:
            connection.execute("DROP TRIGGER IF EXISTS verify_refuse_update")
            connection.execute("DROP TRIGGER IF EXISTS verify_refuse_insert")
        connection.close()
    except sqlite3.Error:
        pass


SUBPROCESS = EMBED_SOURCE + r'''
import importlib.util, json, sys
workspace, path, query = sys.argv[1:4]
sys.path.insert(0, workspace)
spec = importlib.util.spec_from_file_location("candidate_reindex", workspace + "/indexer.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
def embed(texts, *, model):
    return embed_vectors(texts, model)
indexer = module.Indexer(path, embed=embed)
audit = indexer.audit()
results = indexer.search(query, 3)
print(json.dumps({"active": audit["active"], "results": [[r["doc_id"], r["doc_version"], r["chunk_no"]] for r in results]}))
'''


def trial():
    require(MISSION == "reindex", "Unknown mission")
    sys.path.insert(0, WORKSPACE)
    spec = importlib.util.spec_from_file_location("candidate_reindex", os.path.join(WORKSPACE, "indexer.py"))
    if spec is None or spec.loader is None:
        raise ImportError("Cannot load indexer.py")
    candidate = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = candidate
    spec.loader.exec_module(candidate)
    require(isinstance(getattr(candidate, "Indexer", None), type), "indexer.py must define the class Indexer")
    require(callable(getattr(candidate, "chunk", None)), "indexer.py must define chunk(content, chunking_version)")

    rng = random.Random()
    docs, updated_power, code, code2, incident_id = fixtures(rng)
    embedder = Embedder()
    oracle = Oracle()
    path = os.path.join(WORKSPACE, ".verify-archive.sqlite")
    for suffix in ("", "-journal", "-wal", "-shm"):
        if os.path.exists(path + suffix):
            os.remove(path + suffix)
    state = {"indexer": None, "first": None, "before_switch": None, "migrated": None, "rechunked": None}

    def results_key(rows):
        return [(row["doc_id"], row["doc_version"], row["chunk_no"]) for row in rows]

    def search(query, k, version=None):
        mark = len(embedder.calls)
        rows = state["indexer"].search(query, k, version=version) if version is not None else state["indexer"].search(query, k)
        require(isinstance(rows, list) and all(isinstance(row, dict) for row in rows), "search must return a list of dicts")
        for row in rows:
            missing = {"doc_id", "doc_version", "chunk_no", "text", "score"} - set(row)
            require(not missing, f"a search result is missing keys {sorted(missing)}")
        name = version if version is not None else active_version(path)
        model = oracle.versions[name]["model"]
        require(embedder.since(mark) == [(model, 1)], f"search must embed the query once with the version's model {model!r}; saw {embedder.since(mark)}")
        return rows

    def expect_top(name, query, rows, label):
        ranked = oracle.ranked(name, query)
        require(ranked, "oracle has nothing reachable")
        top_score, top = ranked[0]
        if len(ranked) > 1 and top_score - ranked[1][0] < 1e-6:
            return
        require(rows and (rows[0]["doc_id"], rows[0]["doc_version"], rows[0]["chunk_no"]) == top[:3],
                f"{label}: the best answer must be {top[:3]} by cosine, got {results_key(rows)[:3]}")
        require(abs(float(rows[0]["score"]) - top_score) < 1e-6, f"{label}: score {rows[0]['score']!r} is not the cosine {top_score:.6f}")

    def expect_reachable(name, label):
        rows = search(f"relay reserve battery supplies runbook {code2}", ALL, version=None if name == active_version(path) else name)
        wanted = {(row[0], row[1], row[2]) for row in oracle.reachable(name)}
        got = results_key(rows)
        require(len(got) == len(set(got)), f"{label}: a chunk appears twice in the results")
        require(set(got) == wanted, f"{label}: reachable chunks {sorted(set(got))} differ from the current documents' chunks {sorted(wanted)}")
        for row in rows:
            text = next(item[3] for item in oracle.reachable(name) if item[:3] == (row["doc_id"], row["doc_version"], row["chunk_no"]))
            require(squash(row["text"]) == squash(text), f"{label}: chunk {row['doc_id']}/{row['chunk_no']} text differs from the published chunk rule")
        return rows

    def version_entry(name):
        audit = state["indexer"].audit()
        require(isinstance(audit, dict) and isinstance(audit.get("versions"), list), "audit() must return {active, versions: [...]}")
        entries = [entry for entry in audit["versions"] if entry.get("version") == name]
        require(len(entries) == 1, f"audit() must list version {name!r} exactly once")
        return audit, entries[0]

    def expect_audit(name, label):
        audit, entry = version_entry(name)
        wanted_docs = len({row[0] for row in oracle.reachable(name)})
        require(entry.get("documents") == wanted_docs, f"{label}: audit documents {entry.get('documents')!r} for {name}, expected {wanted_docs}")
        require(entry.get("chunks") == oracle.expected_chunks(name), f"{label}: audit chunks {entry.get('chunks')!r} for {name}, expected {oracle.expected_chunks(name)}")
        require(entry.get("missing") == oracle.missing(name), f"{label}: audit missing {entry.get('missing')!r} for {name}, expected {oracle.missing(name)}")
        require(entry.get("active") == (active_version(path) == name), f"{label}: audit active flag for {name} disagrees with the file")
        require(audit.get("active") == active_version(path), f"{label}: audit active {audit.get('active')!r} differs from the file's active row")
        return entry

    def incremental():
        state["indexer"] = candidate.Indexer(path, embed=embedder, embed_model="relay-embed-a", chunking_version=1)
        first = active_version(path)
        state["first"] = first
        rows = version_rows(path)
        require(rows[0]["embed_model"] == "relay-embed-a" and int(rows[0]["chunking_version"]) == 1, f"the first version must carry the constructor's parameters, found {rows}")
        oracle.rebuild(first, "relay-embed-a", 1)
        mark = len(embedder.calls)
        for doc_id, content in docs.items():
            report = state["indexer"].upsert({"doc_id": doc_id, "content": content})
            oracle.upsert(doc_id, content, first)
            require(isinstance(report, dict) and report.get("doc_id") == doc_id and report.get("version") == 1 and report.get("changed") is True
                    and report.get("chunks") == len(oracle_chunks(content, 1)), f"upsert of a new document must report version 1, changed True and {len(oracle_chunks(content, 1))} chunks, got {report!r}")
        wanted = oracle.expected_chunks(first)
        require(sum(count for _, count in embedder.since(mark)) == wanted, f"indexing {len(docs)} documents must embed exactly {wanted} chunk texts, saw {sum(count for _, count in embedder.since(mark))}")
        require(all(model == "relay-embed-a" for model, _ in embedder.since(mark)), "every chunk is embedded with the active version's model")
        mark = len(embedder.calls)
        for doc_id, content in docs.items():
            report = state["indexer"].upsert({"doc_id": doc_id, "content": content})
            require(report.get("changed") is False and report.get("version") == 1, f"re-upserting unchanged content must report changed False at version 1, got {report!r}")
        require(embedder.since(mark) == [], f"re-running upsert on unchanged documents must make zero embed calls, saw {embedder.since(mark)}")
        expect_reachable(first, "initial index")
        expect_audit(first, "initial index")
        query = f"log the access code {code}"
        expect_top(first, query, search(query, 3), "initial search")
        row = document_row(path, "RB-power")
        require(row is not None and int(row["version"]) == 1 and row["content_hash"] == hashlib.sha256(docs["RB-power"].encode("utf-8")).hexdigest(),
                f"documents row must carry version 1 and the sha256 of the content, found {row}")
        return f"{len(docs)} documents, {wanted} chunks embedded once; the unchanged re-run embedded nothing."
    check("Unchanged documents cost zero embed calls", incremental)

    def updated():
        first = state["first"]
        before = document_row(path, "RB-power")
        require(before is not None, "documents must hold a row for RB-power")
        previous = int(before["version"])
        mark = len(embedder.calls)
        report = state["indexer"].upsert({"doc_id": "RB-power", "content": updated_power})
        update_calls = embedder.since(mark)
        oracle.upsert("RB-power", updated_power, active_version(path))
        new_count = len(oracle_chunks(updated_power, 1))
        old_query = f"log the access code {code} in the shift journal"
        rows = search(old_query, ALL)
        for item in rows:
            require(not (item["doc_id"] == "RB-power" and int(item["doc_version"]) <= previous), f"the old version of RB-power is still answered: {results_key([item])}")
            require(code not in str(item["text"]), f"a chunk still carries the old code {code}: {item['doc_id']}/{item['chunk_no']} at document version {item['doc_version']}")
        require(report.get("version") == previous + 1 and report.get("changed") is True and report.get("chunks") == new_count, f"the update must report version {previous + 1}, changed True and {new_count} chunks, got {report!r}")
        require(sum(count for _, count in update_calls) == new_count, f"an update embeds only the changed document's {new_count} chunks, saw {update_calls}")
        row = document_row(path, "RB-power")
        require(row is not None and int(row["version"]) == 2 and row["content_hash"] == hashlib.sha256(updated_power.encode("utf-8")).hexdigest(), f"documents row must be at version 2 with the new hash, found {row}")
        new_query = f"access code {code2} call the morning crew"
        rows = search(new_query, 3)
        expect_top(first, new_query, rows, "search after the update")
        require(rows and rows[0]["doc_id"] == "RB-power" and int(rows[0]["doc_version"]) == 2 and code2 in str(rows[0]["text"]), f"the new content must be found at version 2, got {results_key(rows)[:3]}")
        expect_reachable(first, "after the update")
        expect_audit(first, "after the update")
        return f"RB-power moved from 3 chunks at version 1 to {new_count} at version 2; no old chunk reachable, the old code absent."
    check("An updated document is never answered from its old version", updated)

    def deleted():
        first = state["first"]
        mark = len(embedder.calls)
        require(state["indexer"].delete("RB-water") is True, "delete of a current document returns True")
        oracle.delete("RB-water")
        require(state["indexer"].delete("RB-water") is False, "a second delete of the same document returns False")
        require(state["indexer"].delete("RB-nothing") is False, "delete of an unknown document returns False")
        require(embedder.since(mark) == [], "delete never embeds")
        row = document_row(path, "RB-water")
        require(row is None or int(row.get("deleted", 0)) == 1, f"the documents row must be gone or marked deleted = 1, found {row}")
        query = "replace the purifier cartridge turbidity lamp blinks amber"
        rows = search(query, ALL)
        require(all(item["doc_id"] != "RB-water" for item in rows), f"the deleted runbook is still cited: {[results_key([item]) for item in rows if item['doc_id'] == 'RB-water']}")
        expect_top(first, query, search(query, 3), "search after the delete")
        expect_reachable(first, "after the delete")
        expect_audit(first, "after the delete")
        return "RB-water deleted: no chunk of it reachable, audit counts agree with the file."
    check("A deleted runbook is unreachable", deleted)

    def migration():
        first = state["first"]
        query = f"access code {code2} reserve battery"
        state["before_switch"] = results_key(search(query, 3))
        mark = len(embedder.calls)
        name = state["indexer"].rebuild(embed_model="relay-embed-b")
        require(isinstance(name, str) and name and name != first, f"rebuild must return the new version's name, got {name!r}")
        oracle.rebuild(name, "relay-embed-b", 1)
        state["migrated"] = name
        wanted = oracle.expected_chunks(name)
        require(all(model == "relay-embed-b" for model, _ in embedder.since(mark)), f"a rebuild for relay-embed-b embeds with that model only, saw {embedder.since(mark)}")
        require(sum(count for _, count in embedder.since(mark)) == wanted, f"the rebuild must embed every current document: {wanted} chunks, saw {sum(count for _, count in embedder.since(mark))}")
        rows = version_rows(path)
        require(len(rows) == 2, f"two index versions must exist after the rebuild, found {rows}")
        require(active_version(path) == first, "the active version must not change on rebuild")
        new_row = next(row for row in rows if row["version"] == name)
        require(new_row["embed_model"] == "relay-embed-b" and int(new_row["chunking_version"]) == 1 and int(new_row["active"]) == 0, f"the new row must carry relay-embed-b, chunking 1 and active 0: {new_row}")
        require(results_key(search(query, 3)) == state["before_switch"], "the active version keeps serving the same answers while the new one exists")
        expect_reachable(name, "the rebuilt version")
        expect_audit(name, "the rebuilt version")
        expect_audit(first, "the active version after the rebuild")
        return f"{name} built with relay-embed-b: {wanted} chunks, every current document present; {first} still active."
    check("A model migration builds a complete new version while the active one keeps serving", migration)

    def atomic():
        first = state["first"]
        if state["migrated"] is None:
            # The migration check did not get a usable version; build one here so the switch itself is still exercised.
            state["migrated"] = state["indexer"].rebuild(embed_model="relay-embed-b")
            oracle.rebuild(state["migrated"], "relay-embed-b", 1)
        name = state["migrated"]
        failed = False
        try:
            state["indexer"].switch("no-such-version")
        except Exception:
            failed = True
        require(failed and active_version(path) == first, "switching to an unknown version raises and changes nothing")
        install_refusal(path, name)
        try:
            failed = False
            mark = len(embedder.calls)
            try:
                state["indexer"].switch(name)
            except Exception:
                failed = True
            require(failed, "when the activation statement fails the exception must propagate")
            require(embedder.since(mark) == [], "a switch never embeds")
            require(active_version(path) == first, f"a failed switch must leave {first} as the only active version")
        finally:
            remove_refusal(path)
        mark = len(embedder.calls)
        state["indexer"].switch(name)
        require(embedder.since(mark) == [], "a switch never embeds")
        require(active_version(path) == name, f"after the switch {name} must be the only active version")
        require(len(version_rows(path)) == 2, "a switch keeps both versions in the file")
        query = f"access code {code2} reserve battery"
        rows = search(query, 3)
        expect_top(name, query, rows, "search after the switch")
        pinned = search(query, 3, version=first)
        require(results_key(pinned) == state["before_switch"], f"a reader pinned to {first} must still get its answers after the switch")
        expect_audit(name, "after the switch")
        expect_audit(first, "the previous version after the switch")
        return f"Injected activation failure left {first} active with one active row; the real switch activated {name} in one step."
    check("The switch is atomic: one transaction, exactly one active version", atomic)

    def rollback():
        first, name = state["first"], state["migrated"]
        mark = len(embedder.calls)
        returned = state["indexer"].rollback()
        require(returned == first, f"rollback returns the version it activated ({first}), got {returned!r}")
        require(embedder.since(mark) == [], "rollback flips the active pointer; it never re-embeds")
        require(active_version(path) == first, f"after rollback {first} must be the only active version")
        require(len(version_rows(path)) == 2, "rollback keeps both versions")
        query = f"access code {code2} reserve battery"
        require(results_key(search(query, 3)) == state["before_switch"], "after rollback the answers are the previous version's answers")
        mark = len(embedder.calls)
        require(state["indexer"].rollback() == name and active_version(path) == name, "a second rollback returns to the version active before the first rollback")
        require(state["indexer"].rollback() == first and active_version(path) == first, "rollback is reversible again")
        require(embedder.since(mark) == [], "no rollback embeds")
        fresh_path = os.path.join(WORKSPACE, ".verify-fresh.sqlite")
        if os.path.exists(fresh_path):
            os.remove(fresh_path)
        fresh = candidate.Indexer(fresh_path, embed=embedder)
        try:
            failed = False
            try:
                fresh.rollback()
            except ValueError:
                failed = True
            require(failed, "rollback with no activation raises ValueError")
        finally:
            fresh.close()
            os.remove(fresh_path)
        return f"Rolled back to {first} without an embed call; the previous answers returned; rollback of the rollback reactivated {name}."
    check("Rollback restores the previous version without re-embedding", rollback)

    def rechunk():
        first = state["first"]
        require(active_version(path) == first, f"expected {first} active before the chunking change")
        query = f"access code {code2} reserve battery"
        before = results_key(search(query, 3))
        mark = len(embedder.calls)
        name = state["indexer"].rebuild(chunking_version=2)
        require(isinstance(name, str) and name not in (first, state["migrated"]), f"rebuild must create a third version, got {name!r}")
        oracle.rebuild(name, "relay-embed-a", 2)
        state["rechunked"] = name
        wanted = oracle.expected_chunks(name)
        require(sum(count for _, count in embedder.since(mark)) == wanted and all(model == "relay-embed-a" for model, _ in embedder.since(mark)),
                f"the rechunk embeds {wanted} chunks with the inherited model relay-embed-a, saw {embedder.since(mark)}")
        row = next(item for item in version_rows(path) if item["version"] == name)
        require(row["embed_model"] == "relay-embed-a" and int(row["chunking_version"]) == 2 and int(row["active"]) == 0, f"the new row inherits the model and carries chunking 2: {row}")
        entry = expect_audit(name, "the rechunked version")
        old_entry = expect_audit(first, "the live version during the rechunk")
        require(entry["chunks"] != old_entry["chunks"], f"chunking 2 must change the chunk count ({entry['chunks']} vs {old_entry['chunks']})")
        require(results_key(search(query, 3)) == before, "the live index keeps answering unchanged until the switch")
        state["indexer"].switch(name)
        require(active_version(path) == name, "the switch to the rechunked version activates it")
        rows = expect_reachable(name, "the rechunked version after the switch")
        require(any("\n\n" in str(row["text"]) or len(passages(row["text"])) == 2 for row in rows), "a chunk of chunking version 2 holds two passages")
        expect_top(name, query, search(query, 3), "search on the rechunked version")
        return f"{name}: {entry['chunks']} chunks at chunking 2 against {old_entry['chunks']} at chunking 1; the live index served until the switch."
    check("Changing the chunking on a live index is a new version with its own chunk counts", rechunk)

    def persistence():
        name = state["rechunked"]
        require(name, "no rechunked version to reopen")
        state["indexer"].close()
        state["indexer"] = None
        query = f"access code {code2} reserve battery"
        completed = subprocess.run([sys.executable, "-I", "-B", "-c", SUBPROCESS, WORKSPACE, path, query], capture_output=True, text=True, timeout=20, cwd=WORKSPACE)
        require(completed.returncode == 0, f"a fresh process could not reopen the archive: {completed.stderr.strip()[-600:]}")
        parsed = json.loads(completed.stdout.strip().splitlines()[-1])
        require(parsed["active"] == name, f"a fresh process must see {name} active, saw {parsed['active']!r}")
        ranked = oracle.ranked(name, query)
        if len(ranked) > 1 and ranked[0][0] - ranked[1][0] >= 1e-6:
            require(parsed["results"] and tuple(parsed["results"][0]) == ranked[0][1][:3], f"a fresh process must answer {ranked[0][1][:3]} first, got {parsed['results']}")
        state["indexer"] = candidate.Indexer(path, embed=embedder)
        require(active_version(path) == name, "reopening the file must not change the active version")
        return f"A separate python process reopened the file, saw {name} active and answered from it."
    check("A fresh process reads the same active version and answers from the file", persistence)

    def refusal():
        if state["indexer"] is None:
            state["indexer"] = candidate.Indexer(path, embed=embedder)
        current = active_version(path)
        name = state["indexer"].rebuild(embed_model="relay-embed-c")
        oracle.rebuild(name, "relay-embed-c", oracle.versions[current]["width"])
        late = {"doc_id": f"IR-{rng.randint(1000, 9999)}", "content": "Incident report: a late filing.\n\nThe supplies desk received the cartridges one shift after the reservation expired."}
        state["indexer"].upsert(late)
        oracle.upsert(late["doc_id"], late["content"], current)
        audit, entry = version_entry(name)
        require(entry.get("missing") == [late["doc_id"]], f"audit must name the document {name} lacks, got {entry.get('missing')!r}")
        failed = False
        try:
            state["indexer"].switch(name)
        except ValueError:
            failed = True
        require(failed, f"switching to {name} without {late['doc_id']} must raise ValueError")
        require(active_version(path) == current, "a refused switch leaves the active version alone")
        return f"{name} lacked {late['doc_id']}; the switch was refused and {current} stayed active."
    check("bonus: switching to a version that lacks a current document is refused", refusal, optional=True)

    if state["indexer"] is not None:
        try:
            state["indexer"].close()
        except Exception:
            pass


try:
    trial()
except Exception as error:
    CHECKS.append({"name": "Load incremental indexer", "passed": False, "detail": f"{type(error).__name__}: {error}"[:1500]})
print(json.dumps({"checks": CHECKS}))
sys.exit(0 if CHECKS and all(item["passed"] for item in CHECKS if not item.get("optional")) else 1)
