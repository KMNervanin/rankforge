"""Embedding store for the outpost archive.

Starter: it embeds passages and ranks them, but the store forgets which model made the vectors,
scores them with a bare dot product and keeps the vectors in memory. See LEARN.md for the
complete contract that Verify checks.
"""
import json
import os
import sqlite3
import urllib.request

MAX_BATCH = 16


class ModelMismatch(ValueError):
    """The vectors or the query come from a different embedding model or version than the store."""


class DimensionMismatch(ValueError):
    """The vectors or the query have a different dimension than the store."""


def cosine(a, b):
    return sum(x * y for x, y in zip(a, b))


def embed(texts, *, base_url, model, batch_size=MAX_BATCH):
    body = json.dumps({"model": model, "input": list(texts)}).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    key = os.environ.get("LLM_API_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    request = urllib.request.Request(base_url.rstrip("/") + "/embeddings", data=body, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return [item["embedding"] for item in payload["data"]]


class EmbeddingStore:
    def __init__(self, path):
        self.connection = sqlite3.connect(path)
        self.connection.execute("CREATE TABLE IF NOT EXISTS passages (id TEXT PRIMARY KEY, text TEXT NOT NULL)")
        self.connection.commit()
        self.vectors = {}
        self.model = None
        self.version = None
        self.usage = []

    def close(self):
        self.connection.close()

    def metadata(self):
        if not self.vectors:
            return None
        dimension = len(next(iter(self.vectors.values())))
        return {"model": self.model, "version": self.version, "dimension": dimension, "passages": len(self.vectors)}

    def add(self, passages, vectors, *, model, version):
        self.model, self.version = model, version
        with self.connection:
            self.connection.executemany("INSERT OR REPLACE INTO passages (id, text) VALUES (?, ?)", [(passage["id"], passage["text"]) for passage in passages])
        for passage, vector in zip(passages, vectors):
            self.vectors[passage["id"]] = list(vector)
        return len(passages)

    def ingest(self, passages, *, base_url, model, version, batch_size=MAX_BATCH):
        passages = list(passages)
        vectors = embed([passage["text"] for passage in passages], base_url=base_url, model=model)
        self.add(passages, vectors, model=model, version=version)
        record = {"model": model, "version": version, "dimension": len(vectors[0]), "inputs": len(passages), "prompt_tokens": 0, "total_tokens": 0}
        self.usage.append(record)
        return [record]

    def batches(self):
        return list(self.usage)

    def search(self, query_vector, k, *, model, version=None):
        scored = [(passage_id, cosine(query_vector, vector)) for passage_id, vector in self.vectors.items()]
        scored.sort(key=lambda item: -item[1])
        return scored[:k]

    def re_embed(self, new_model, embed_fn, *, version, batch_size=MAX_BATCH):
        rows = self.connection.execute("SELECT id, text FROM passages ORDER BY id").fetchall()
        if not rows:
            return 0
        vectors = embed_fn([text for _, text in rows])
        for (passage_id, _), vector in zip(rows, vectors):
            self.vectors[f"{new_model}:{passage_id}"] = list(vector)
        self.model, self.version = new_model, version
        return len(rows)
