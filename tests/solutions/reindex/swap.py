"""Incremental indexer, index swap: one chunks table per index version, vectors as float64 blobs, purge on change.

rebuild creates chunks_<version> and fills it without touching the live table; switch flips the active row and
records on the target which version it replaced, so rollback is one more flip. In the active table an update
deletes the old rows and inserts the new ones in a single transaction; a delete removes the document row and
its rows from the active table. Older tables keep whatever they held: search joins documents, so a row of a
superseded or deleted document is unreachable there and audit() counts it as stale.
"""
import hashlib
import math
import re
import sqlite3
import struct

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (doc_id TEXT PRIMARY KEY, version INTEGER NOT NULL, content_hash TEXT NOT NULL, content TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS index_versions (
    version TEXT PRIMARY KEY, embed_model TEXT NOT NULL, chunking_version INTEGER NOT NULL,
    active INTEGER NOT NULL DEFAULT 0, previous TEXT, created INTEGER NOT NULL);
"""


def passages(content):
    return [part.strip() for part in re.split(r"\n\s*\n", content.strip()) if part.strip()]


def chunk(content, chunking_version):
    width = int(chunking_version)
    if width < 1:
        raise ValueError("chunking_version must be a positive integer")
    parts = passages(content)
    return ["\n\n".join(parts[index:index + width]) for index in range(0, len(parts), width)]


def pack(vector):
    return struct.pack(f"<{len(vector)}d", *vector)


def unpack(blob):
    return list(struct.unpack(f"<{len(blob) // 8}d", blob))


def cosine(left, right):
    dot = sum(a * b for a, b in zip(left, right))
    norm = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
    return dot / norm if norm else 0.0


def table(version):
    return "chunks_" + re.sub(r"[^A-Za-z0-9_]", "_", version)


class Indexer:
    def __init__(self, path, *, embed, embed_model="relay-embed-a", chunking_version=1):
        self.embed = embed
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        if self.conn.execute("SELECT COUNT(*) FROM index_versions").fetchone()[0] == 0:
            with self.conn:
                self._create_version("ix-1", str(embed_model), int(chunking_version), active=1, created=1)

    def close(self):
        self.conn.close()

    def _create_version(self, name, model, width, *, active, created):
        self.conn.execute("INSERT INTO index_versions (version, embed_model, chunking_version, active, previous, created) VALUES (?, ?, ?, ?, NULL, ?)",
                          (name, model, width, active, created))
        self.conn.execute(f"CREATE TABLE {table(name)} (doc_id TEXT NOT NULL, doc_version INTEGER NOT NULL, chunk_no INTEGER NOT NULL, "
                          "text TEXT NOT NULL, vector BLOB NOT NULL, PRIMARY KEY (doc_id, doc_version, chunk_no))")

    def _active(self):
        return self.conn.execute("SELECT * FROM index_versions WHERE active = 1").fetchone()

    def _version(self, name):
        row = self.conn.execute("SELECT * FROM index_versions WHERE version = ?", (name,)).fetchone()
        if row is None:
            raise ValueError(f"unknown index version {name!r}")
        return row

    def _embedded(self, row, doc_id, doc_version, content):
        texts = chunk(content, row["chunking_version"])
        if not texts:
            raise ValueError(f"document {doc_id!r} has no passage")
        vectors = self.embed(texts, model=row["embed_model"])
        return [(doc_id, doc_version, number, text, pack(vector)) for number, (text, vector) in enumerate(zip(texts, vectors))]

    def upsert(self, doc):
        doc_id, content = str(doc["doc_id"]), str(doc["content"])
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        active = self._active()
        existing = self.conn.execute("SELECT version, content_hash FROM documents WHERE doc_id = ?", (doc_id,)).fetchone()
        if existing is not None and existing["content_hash"] == digest:
            count = self.conn.execute(f"SELECT COUNT(*) FROM {table(active['version'])} WHERE doc_id = ? AND doc_version = ?", (doc_id, existing["version"])).fetchone()[0]
            return {"doc_id": doc_id, "version": existing["version"], "changed": False, "chunks": count}
        version = existing["version"] + 1 if existing is not None else 1
        rows = self._embedded(active, doc_id, version, content)
        with self.conn:
            self.conn.execute("INSERT OR REPLACE INTO documents (doc_id, version, content_hash, content) VALUES (?, ?, ?, ?)", (doc_id, version, digest, content))
            self.conn.execute(f"DELETE FROM {table(active['version'])} WHERE doc_id = ?", (doc_id,))
            self.conn.executemany(f"INSERT INTO {table(active['version'])} VALUES (?, ?, ?, ?, ?)", rows)
        return {"doc_id": doc_id, "version": version, "changed": True, "chunks": len(rows)}

    def delete(self, doc_id):
        if self.conn.execute("SELECT 1 FROM documents WHERE doc_id = ?", (doc_id,)).fetchone() is None:
            return False
        active = self._active()
        with self.conn:
            self.conn.execute("DELETE FROM documents WHERE doc_id = ?", (doc_id,))
            self.conn.execute(f"DELETE FROM {table(active['version'])} WHERE doc_id = ?", (doc_id,))
        return True

    def _reachable(self, name):
        return f"FROM {table(name)} c JOIN documents d ON d.doc_id = c.doc_id AND d.version = c.doc_version"

    def search(self, query, k, *, version=None):
        if int(k) < 1:
            raise ValueError("k must be at least 1")
        row = self._version(version) if version is not None else self._active()
        wanted = self.embed([str(query)], model=row["embed_model"])[0]
        scored = [(cosine(wanted, unpack(item["vector"])), item["doc_id"], item["chunk_no"], item)
                  for item in self.conn.execute(f"SELECT c.doc_id, c.doc_version, c.chunk_no, c.text, c.vector {self._reachable(row['version'])}")]
        scored.sort(key=lambda entry: (-entry[0], entry[1], entry[2]))
        return [{"doc_id": item["doc_id"], "doc_version": item["doc_version"], "chunk_no": item["chunk_no"], "text": item["text"], "score": score}
                for score, _, _, item in scored[:int(k)]]

    def rebuild(self, *, embed_model=None, chunking_version=None):
        active = self._active()
        created = self.conn.execute("SELECT COALESCE(MAX(created), 0) + 1 FROM index_versions").fetchone()[0]
        name = f"ix-{created}"
        spec = {"version": name, "embed_model": str(embed_model) if embed_model is not None else active["embed_model"],
                "chunking_version": int(chunking_version) if chunking_version is not None else active["chunking_version"]}
        rows = []
        for doc in self.conn.execute("SELECT doc_id, version, content FROM documents ORDER BY doc_id"):
            rows.extend(self._embedded(spec, doc["doc_id"], doc["version"], doc["content"]))
        with self.conn:
            self._create_version(name, spec["embed_model"], spec["chunking_version"], active=0, created=created)
            self.conn.executemany(f"INSERT INTO {table(name)} VALUES (?, ?, ?, ?, ?)", rows)
        return name

    def _missing(self, name):
        held = {(row["doc_id"], row["doc_version"]) for row in self.conn.execute(f"SELECT DISTINCT doc_id, doc_version FROM {table(name)}")}
        return sorted(row["doc_id"] for row in self.conn.execute("SELECT doc_id, version FROM documents") if (row["doc_id"], row["version"]) not in held)

    def switch(self, version):
        target = self._version(version)["version"]
        current = self._active()["version"]
        if target == current:
            return
        missing = self._missing(target)
        if missing:
            raise ValueError(f"index version {target!r} lacks current documents: {missing}")
        with self.conn:
            self.conn.execute("UPDATE index_versions SET active = CASE WHEN version = ? THEN 1 ELSE 0 END", (target,))
            self.conn.execute("UPDATE index_versions SET previous = ? WHERE version = ?", (current, target))

    def rollback(self):
        active = self._active()
        if active["previous"] is None:
            raise ValueError("no activation to roll back")
        self.switch(active["previous"])
        return active["previous"]

    def audit(self):
        versions = []
        for row in self.conn.execute("SELECT * FROM index_versions ORDER BY created"):
            reachable = self.conn.execute(f"SELECT COUNT(*) {self._reachable(row['version'])}").fetchone()[0]
            documents = self.conn.execute(f"SELECT COUNT(DISTINCT c.doc_id) {self._reachable(row['version'])}").fetchone()[0]
            total = self.conn.execute(f"SELECT COUNT(*) FROM {table(row['version'])}").fetchone()[0]
            versions.append({"version": row["version"], "embed_model": row["embed_model"], "chunking_version": row["chunking_version"],
                             "active": bool(row["active"]), "documents": documents, "chunks": reachable, "stale": total - reachable, "missing": self._missing(row["version"])})
        return {"active": self._active()["version"], "versions": versions}
