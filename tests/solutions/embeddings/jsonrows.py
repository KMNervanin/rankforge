"""Embedding store: urllib.request, vectors stored as JSON text, cosine computed on every search."""
import json
import math
import os
import sqlite3
import urllib.request

MAX_BATCH = 16


class ModelMismatch(ValueError):
    """The vectors or the query come from a different embedding model or version than the store."""


class DimensionMismatch(ValueError):
    """The vectors or the query have a different dimension than the store."""


def cosine(a, b):
    if len(a) != len(b):
        raise DimensionMismatch(f"cosine needs equal dimensions, got {len(a)} and {len(b)}")
    dot = math.fsum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(math.fsum(x * x for x in a))
    norm_b = math.sqrt(math.fsum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _post(base_url, model, texts):
    body = json.dumps({"model": model, "input": list(texts)}).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    key = os.environ.get("LLM_API_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    request = urllib.request.Request(base_url.rstrip("/") + "/embeddings", data=body, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))
    data = sorted(payload["data"], key=lambda item: item["index"])
    vectors = [[float(value) for value in item["embedding"]] for item in data]
    if len(vectors) != len(texts):
        raise ValueError(f"asked for {len(texts)} embeddings, received {len(vectors)}")
    usage = payload.get("usage") or {}
    return vectors, int(usage.get("prompt_tokens") or 0), int(usage.get("total_tokens") or 0)


def _batches(texts, batch_size):
    texts = list(texts)
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")
    for start in range(0, len(texts), batch_size):
        yield texts[start:start + batch_size]


def embed(texts, *, base_url, model, batch_size=MAX_BATCH):
    vectors = []
    for chunk in _batches(texts, batch_size):
        vectors.extend(_post(base_url, model, chunk)[0])
    return vectors


class EmbeddingStore:
    def __init__(self, path):
        self.path = path
        self.connection = sqlite3.connect(path)
        self.connection.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        self.connection.execute("CREATE TABLE IF NOT EXISTS vectors (model TEXT NOT NULL, version TEXT NOT NULL, dimension INTEGER NOT NULL, id TEXT NOT NULL, text TEXT NOT NULL, vector TEXT NOT NULL, PRIMARY KEY (model, version, id))")
        self.connection.execute("CREATE TABLE IF NOT EXISTS batches (seq INTEGER PRIMARY KEY AUTOINCREMENT, model TEXT NOT NULL, version TEXT NOT NULL, dimension INTEGER NOT NULL, inputs INTEGER NOT NULL, prompt_tokens INTEGER NOT NULL, total_tokens INTEGER NOT NULL)")
        self.connection.commit()

    def close(self):
        self.connection.close()

    def metadata(self):
        rows = dict(self.connection.execute("SELECT key, value FROM meta").fetchall())
        if "model" not in rows:
            return None
        (count,) = self.connection.execute("SELECT COUNT(*) FROM vectors").fetchone()
        return {"model": rows["model"], "version": rows["version"], "dimension": int(rows["dimension"]), "passages": count}

    def _check(self, model, version, dimension):
        meta = self.metadata()
        if meta is None:
            return
        if model != meta["model"] or (version is not None and version != meta["version"]):
            raise ModelMismatch(f"store holds {meta['model']}@{meta['version']}, not {model}@{version}")
        if dimension != meta["dimension"]:
            raise DimensionMismatch(f"store holds {meta['dimension']}-dimensional vectors, not {dimension}")

    def add(self, passages, vectors, *, model, version):
        passages, vectors = list(passages), [list(map(float, vector)) for vector in vectors]
        if len(passages) != len(vectors):
            raise ValueError(f"{len(passages)} passages but {len(vectors)} vectors")
        if not passages:
            return 0
        dimension = len(vectors[0])
        if any(len(vector) != dimension for vector in vectors):
            raise DimensionMismatch("every vector of one add call must have the same dimension")
        self._check(model, version, dimension)
        with self.connection:
            if self.metadata() is None:
                self.connection.executemany("INSERT INTO meta (key, value) VALUES (?, ?)", [("model", model), ("version", version), ("dimension", str(dimension))])
            self.connection.executemany(
                "INSERT OR REPLACE INTO vectors (model, version, dimension, id, text, vector) VALUES (?, ?, ?, ?, ?, ?)",
                [(model, version, dimension, str(passage["id"]), str(passage["text"]), json.dumps(vector)) for passage, vector in zip(passages, vectors)],
            )
        return len(passages)

    def ingest(self, passages, *, base_url, model, version, batch_size=MAX_BATCH):
        passages = list(passages)
        records = []
        for chunk in _batches(passages, batch_size):
            vectors, prompt_tokens, total_tokens = _post(base_url, model, [passage["text"] for passage in chunk])
            self.add(chunk, vectors, model=model, version=version)
            record = {"model": model, "version": version, "dimension": len(vectors[0]), "inputs": len(chunk), "prompt_tokens": prompt_tokens, "total_tokens": total_tokens}
            with self.connection:
                self.connection.execute("INSERT INTO batches (model, version, dimension, inputs, prompt_tokens, total_tokens) VALUES (?, ?, ?, ?, ?, ?)", tuple(record.values()))
            records.append(record)
        return records

    def batches(self):
        rows = self.connection.execute("SELECT model, version, dimension, inputs, prompt_tokens, total_tokens FROM batches ORDER BY seq").fetchall()
        return [dict(zip(("model", "version", "dimension", "inputs", "prompt_tokens", "total_tokens"), row)) for row in rows]

    def search(self, query_vector, k, *, model, version=None):
        if not isinstance(k, int) or k < 1:
            raise ValueError("k must be an integer of at least 1")
        query = [float(value) for value in query_vector]
        if self.metadata() is None:
            return []
        self._check(model, version, len(query))
        scored = []
        for passage_id, vector in self.connection.execute("SELECT id, vector FROM vectors").fetchall():
            scored.append((passage_id, cosine(query, json.loads(vector))))
        scored.sort(key=lambda item: (-item[1], item[0]))
        return scored[:k]

    def re_embed(self, new_model, embed_fn, *, version, batch_size=MAX_BATCH):
        rows = self.connection.execute("SELECT id, text FROM vectors ORDER BY id").fetchall()
        passages = [{"id": passage_id, "text": text} for passage_id, text in rows]
        vectors = []
        for chunk in _batches([passage["text"] for passage in passages], batch_size):
            produced = list(embed_fn(chunk))
            if len(produced) != len(chunk):
                raise ValueError(f"embed_fn returned {len(produced)} vectors for {len(chunk)} texts")
            vectors.extend(produced)
        with self.connection:
            self.connection.execute("DELETE FROM vectors")
            self.connection.execute("DELETE FROM meta")
        return self.add(passages, vectors, model=new_model, version=version)
