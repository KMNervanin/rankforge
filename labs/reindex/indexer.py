"""Indexer for the outpost archive: documents in, chunk vectors out, search by cosine.

Starter: it indexes and searches, but the archive never changes under it gracefully. See LEARN.md for the
complete contract that Verify checks: document versions, index versions, an atomic switch and rollback.
"""
import hashlib
import json
import math
import re
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (doc_id TEXT PRIMARY KEY, version INTEGER NOT NULL, content_hash TEXT NOT NULL, content TEXT NOT NULL, deleted INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS index_versions (version TEXT PRIMARY KEY, embed_model TEXT NOT NULL, chunking_version INTEGER NOT NULL, active INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS chunks (doc_id TEXT NOT NULL, chunk_no INTEGER NOT NULL, text TEXT NOT NULL, vector TEXT NOT NULL, PRIMARY KEY (doc_id, chunk_no));
"""


def chunk(content, chunking_version):
    """Split at blank lines; chunking_version passages per chunk."""
    parts = [part.strip() for part in re.split(r"\n\s*\n", content.strip()) if part.strip()]
    width = int(chunking_version)
    return ["\n\n".join(parts[index:index + width]) for index in range(0, len(parts), width)]


def cosine(left, right):
    dot = sum(a * b for a, b in zip(left, right))
    norm = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
    return dot / norm if norm else 0.0


class Indexer:
    def __init__(self, path, *, embed, embed_model="relay-embed-a", chunking_version=1):
        self.embed = embed
        self.conn = sqlite3.connect(path, isolation_level=None)  # autocommit: every statement lands at once
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        if self.conn.execute("SELECT COUNT(*) FROM index_versions").fetchone()[0] == 0:
            self.conn.execute("INSERT INTO index_versions (version, embed_model, chunking_version, active) VALUES ('live', ?, ?, 1)", (embed_model, int(chunking_version)))
        self.previous = None

    def close(self):
        self.conn.close()

    def _active(self):
        return self.conn.execute("SELECT * FROM index_versions WHERE active = 1").fetchone()

    def _index(self, doc_id, content):
        active = self._active()
        texts = chunk(content, active["chunking_version"])
        vectors = self.embed(texts, model=active["embed_model"])
        for number, (text, vector) in enumerate(zip(texts, vectors)):
            self.conn.execute("INSERT OR REPLACE INTO chunks (doc_id, chunk_no, text, vector) VALUES (?, ?, ?, ?)", (doc_id, number, text, json.dumps(vector)))
        return len(texts)

    def upsert(self, doc):
        doc_id, content = str(doc["doc_id"]), str(doc["content"])
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        existing = self.conn.execute("SELECT version FROM documents WHERE doc_id = ?", (doc_id,)).fetchone()
        version = existing["version"] + 1 if existing else 1
        self.conn.execute("INSERT OR REPLACE INTO documents (doc_id, version, content_hash, content, deleted) VALUES (?, ?, ?, ?, 0)", (doc_id, version, digest, content))
        count = self._index(doc_id, content)
        return {"doc_id": doc_id, "version": version, "changed": True, "chunks": count}

    def delete(self, doc_id):
        if self.conn.execute("SELECT 1 FROM documents WHERE doc_id = ?", (doc_id,)).fetchone() is None:
            return False
        self.conn.execute("DELETE FROM documents WHERE doc_id = ?", (doc_id,))
        return True

    def search(self, query, k, *, version=None):
        if int(k) < 1:
            raise ValueError("k must be at least 1")
        active = self._active()
        wanted = self.embed([str(query)], model=active["embed_model"])[0]
        scored = []
        for row in self.conn.execute("SELECT c.doc_id, c.chunk_no, c.text, c.vector, d.version FROM chunks c LEFT JOIN documents d ON d.doc_id = c.doc_id"):
            scored.append((cosine(wanted, json.loads(row["vector"])), row))
        scored.sort(key=lambda pair: (-pair[0], pair[1]["doc_id"], pair[1]["chunk_no"]))
        return [{"doc_id": row["doc_id"], "doc_version": row["version"] or 1, "chunk_no": row["chunk_no"], "text": row["text"], "score": score} for score, row in scored[:int(k)]]

    def rebuild(self, *, embed_model=None, chunking_version=None):
        """Re-embed everything in place with the new parameters."""
        active = self._active()
        self.previous = (active["embed_model"], active["chunking_version"])
        model = embed_model if embed_model is not None else active["embed_model"]
        width = int(chunking_version) if chunking_version is not None else active["chunking_version"]
        self.conn.execute("UPDATE index_versions SET embed_model = ?, chunking_version = ? WHERE active = 1", (model, width))
        self.conn.execute("DROP TABLE chunks")
        self.conn.execute("CREATE TABLE chunks (doc_id TEXT NOT NULL, chunk_no INTEGER NOT NULL, text TEXT NOT NULL, vector TEXT NOT NULL, PRIMARY KEY (doc_id, chunk_no))")
        for row in self.conn.execute("SELECT doc_id, content FROM documents").fetchall():
            self._index(row["doc_id"], row["content"])
        return active["version"]

    def switch(self, version):
        if self.conn.execute("SELECT 1 FROM index_versions WHERE version = ?", (version,)).fetchone() is None:
            raise ValueError(f"unknown index version {version!r}")
        self.conn.execute("UPDATE index_versions SET active = 0 WHERE active = 1")
        self.conn.execute("UPDATE index_versions SET active = 1 WHERE version = ?", (version,))

    def rollback(self):
        if self.previous is None:
            raise ValueError("no activation to roll back")
        model, width = self.previous
        return self.rebuild(embed_model=model, chunking_version=width)

    def audit(self):
        active = self._active()
        documents = self.conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        chunks = self.conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        return {"active": active["version"], "versions": [{"version": active["version"], "embed_model": active["embed_model"], "chunking_version": active["chunking_version"],
                                                           "active": True, "documents": documents, "chunks": chunks, "stale": 0, "missing": []}]}
