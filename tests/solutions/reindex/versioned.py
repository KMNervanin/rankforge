"""Incremental indexer, versioned rows: one chunks table, every row tagged with its index version and document version.

Nothing is ever updated in place. An upsert writes the new document version's chunks next to the old ones and bumps
documents.version in the same transaction; search joins on the current version, so the old rows become unreachable
at the commit and stay in the file as stale rows that audit() counts. A delete tombstones the document row.
"""
import hashlib
import json
import math
import re
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    doc_id TEXT PRIMARY KEY, version INTEGER NOT NULL, content_hash TEXT NOT NULL, content TEXT NOT NULL,
    deleted INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS index_versions (
    version TEXT PRIMARY KEY, embed_model TEXT NOT NULL, chunking_version INTEGER NOT NULL,
    active INTEGER NOT NULL DEFAULT 0, created INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS chunks (
    index_version TEXT NOT NULL, doc_id TEXT NOT NULL, doc_version INTEGER NOT NULL, chunk_no INTEGER NOT NULL,
    text TEXT NOT NULL, vector TEXT NOT NULL,
    PRIMARY KEY (index_version, doc_id, doc_version, chunk_no));
CREATE TABLE IF NOT EXISTS activations (seq INTEGER PRIMARY KEY AUTOINCREMENT, previous TEXT NOT NULL, version TEXT NOT NULL);
"""
REACHABLE = "FROM chunks c JOIN documents d ON d.doc_id = c.doc_id AND d.version = c.doc_version AND d.deleted = 0 WHERE c.index_version = ?"


def passages(content):
    return [part.strip() for part in re.split(r"\n\s*\n", content.strip()) if part.strip()]


def chunk(content, chunking_version):
    parts = passages(content)
    width = int(chunking_version)
    if width < 1:
        raise ValueError("chunking_version must be a positive integer")
    return ["\n\n".join(parts[start:start + width]) for start in range(0, len(parts), width)]


def content_hash(content):
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def cosine(left, right):
    dot = sum(a * b for a, b in zip(left, right))
    norm = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
    return dot / norm if norm else 0.0


class Indexer:
    def __init__(self, path, *, embed, embed_model="relay-embed-a", chunking_version=1):
        self.embed = embed
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        if self.conn.execute("SELECT COUNT(*) FROM index_versions").fetchone()[0] == 0:
            with self.conn:
                self.conn.execute("INSERT INTO index_versions (version, embed_model, chunking_version, active, created) VALUES (?, ?, ?, 1, 1)",
                                  ("v1", str(embed_model), int(chunking_version)))

    def close(self):
        self.conn.close()

    # --- versions -------------------------------------------------------------------------------------------------
    def _active(self):
        row = self.conn.execute("SELECT * FROM index_versions WHERE active = 1").fetchone()
        if row is None:
            raise RuntimeError("no active index version")
        return row

    def _version(self, name):
        row = self.conn.execute("SELECT * FROM index_versions WHERE version = ?", (name,)).fetchone()
        if row is None:
            raise ValueError(f"unknown index version {name!r}")
        return row

    def _missing(self, name):
        current = self.conn.execute("SELECT doc_id, version FROM documents WHERE deleted = 0").fetchall()
        held = {(row["doc_id"], row["doc_version"]) for row in self.conn.execute("SELECT DISTINCT doc_id, doc_version FROM chunks WHERE index_version = ?", (name,))}
        return sorted(row["doc_id"] for row in current if (row["doc_id"], row["version"]) not in held)

    def _rows(self, name, model, width, doc_id, doc_version, content):
        texts = chunk(content, width)
        if not texts:
            raise ValueError(f"document {doc_id!r} has no passage")
        vectors = self.embed(texts, model=model)
        return [(name, doc_id, doc_version, number, text, json.dumps(vector)) for number, (text, vector) in enumerate(zip(texts, vectors))]

    # --- documents ------------------------------------------------------------------------------------------------
    def upsert(self, doc):
        doc_id, content = str(doc["doc_id"]), str(doc["content"])
        digest = content_hash(content)
        active = self._active()
        existing = self.conn.execute("SELECT version, content_hash, deleted FROM documents WHERE doc_id = ?", (doc_id,)).fetchone()
        if existing is not None and existing["content_hash"] == digest and not existing["deleted"]:
            count = self.conn.execute("SELECT COUNT(*) FROM chunks WHERE index_version = ? AND doc_id = ? AND doc_version = ?",
                                      (active["version"], doc_id, existing["version"])).fetchone()[0]
            return {"doc_id": doc_id, "version": existing["version"], "changed": False, "chunks": count}
        version = existing["version"] + 1 if existing is not None else 1
        rows = self._rows(active["version"], active["embed_model"], active["chunking_version"], doc_id, version, content)
        with self.conn:
            self.conn.execute("INSERT INTO documents (doc_id, version, content_hash, content, deleted) VALUES (?, ?, ?, ?, 0) "
                              "ON CONFLICT(doc_id) DO UPDATE SET version = excluded.version, content_hash = excluded.content_hash, content = excluded.content, deleted = 0",
                              (doc_id, version, digest, content))
            self.conn.executemany("INSERT INTO chunks (index_version, doc_id, doc_version, chunk_no, text, vector) VALUES (?, ?, ?, ?, ?, ?)", rows)
        return {"doc_id": doc_id, "version": version, "changed": True, "chunks": len(rows)}

    def delete(self, doc_id):
        row = self.conn.execute("SELECT deleted FROM documents WHERE doc_id = ?", (doc_id,)).fetchone()
        if row is None or row["deleted"]:
            return False
        with self.conn:
            self.conn.execute("UPDATE documents SET deleted = 1 WHERE doc_id = ?", (doc_id,))
        return True

    # --- search ---------------------------------------------------------------------------------------------------
    def search(self, query, k, *, version=None):
        if int(k) < 1:
            raise ValueError("k must be at least 1")
        row = self._version(version) if version is not None else self._active()
        query_vector = self.embed([str(query)], model=row["embed_model"])[0]
        scored = []
        for item in self.conn.execute(f"SELECT c.doc_id, c.doc_version, c.chunk_no, c.text, c.vector {REACHABLE}", (row["version"],)):
            scored.append((cosine(query_vector, json.loads(item["vector"])), item))
        scored.sort(key=lambda pair: (-pair[0], pair[1]["doc_id"], pair[1]["chunk_no"]))
        return [{"doc_id": item["doc_id"], "doc_version": item["doc_version"], "chunk_no": item["chunk_no"], "text": item["text"], "score": score}
                for score, item in scored[:int(k)]]

    # --- index versions -------------------------------------------------------------------------------------------
    def rebuild(self, *, embed_model=None, chunking_version=None):
        active = self._active()
        model = str(embed_model) if embed_model is not None else active["embed_model"]
        width = int(chunking_version) if chunking_version is not None else active["chunking_version"]
        created = self.conn.execute("SELECT COALESCE(MAX(created), 0) + 1 FROM index_versions").fetchone()[0]
        name = f"v{created}"
        rows = []
        for doc in self.conn.execute("SELECT doc_id, version, content FROM documents WHERE deleted = 0 ORDER BY doc_id"):
            rows.extend(self._rows(name, model, width, doc["doc_id"], doc["version"], doc["content"]))
        with self.conn:
            self.conn.execute("INSERT INTO index_versions (version, embed_model, chunking_version, active, created) VALUES (?, ?, ?, 0, ?)", (name, model, width, created))
            self.conn.executemany("INSERT INTO chunks (index_version, doc_id, doc_version, chunk_no, text, vector) VALUES (?, ?, ?, ?, ?, ?)", rows)
        return name

    def switch(self, version):
        target = self._version(version)["version"]
        current = self._active()["version"]
        if target == current:
            return
        missing = self._missing(target)
        if missing:
            raise ValueError(f"index version {target!r} lacks current documents: {missing}")
        with self.conn:
            self.conn.execute("UPDATE index_versions SET active = 0 WHERE active = 1")
            self.conn.execute("UPDATE index_versions SET active = 1 WHERE version = ?", (target,))
            self.conn.execute("INSERT INTO activations (previous, version) VALUES (?, ?)", (current, target))

    def rollback(self):
        last = self.conn.execute("SELECT previous, version FROM activations ORDER BY seq DESC LIMIT 1").fetchone()
        if last is None:
            raise ValueError("no activation to roll back")
        self.switch(last["previous"])
        return last["previous"]

    def audit(self):
        versions = []
        for row in self.conn.execute("SELECT * FROM index_versions ORDER BY created"):
            reachable = self.conn.execute(f"SELECT COUNT(*) {REACHABLE}", (row["version"],)).fetchone()[0]
            documents = self.conn.execute(f"SELECT COUNT(DISTINCT c.doc_id) {REACHABLE}", (row["version"],)).fetchone()[0]
            total = self.conn.execute("SELECT COUNT(*) FROM chunks WHERE index_version = ?", (row["version"],)).fetchone()[0]
            versions.append({"version": row["version"], "embed_model": row["embed_model"], "chunking_version": row["chunking_version"],
                             "active": bool(row["active"]), "documents": documents, "chunks": reachable, "stale": total - reachable,
                             "missing": self._missing(row["version"])})
        return {"active": self._active()["version"], "versions": versions}
