"""Embedding store: http.client, vectors L2-normalized on add and stored as float64 BLOBs, dot product on search."""
import http.client
import json
import math
import os
import sqlite3
from array import array
from urllib.parse import urlsplit

MAX_BATCH = 16


class ModelMismatch(ValueError):
    """The vectors or the query come from a different embedding model or version than the store."""


class DimensionMismatch(ValueError):
    """The vectors or the query have a different dimension than the store."""


def _unit(vector):
    values = [float(value) for value in vector]
    norm = math.sqrt(math.fsum(value * value for value in values))
    if norm == 0.0:
        return values
    return [value / norm for value in values]


def cosine(a, b):
    if len(a) != len(b):
        raise DimensionMismatch(f"cosine needs equal dimensions, got {len(a)} and {len(b)}")
    return math.fsum(x * y for x, y in zip(_unit(a), _unit(b)))


def _request(base_url, model, texts):
    parts = urlsplit(base_url)
    connection = (http.client.HTTPSConnection if parts.scheme == "https" else http.client.HTTPConnection)(parts.hostname, parts.port, timeout=60)
    headers = {"Content-Type": "application/json"}
    key = os.environ.get("LLM_API_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    try:
        connection.request("POST", parts.path.rstrip("/") + "/embeddings", body=json.dumps({"model": model, "input": texts}), headers=headers)
        response = connection.getresponse()
        raw = response.read()
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status}: {raw[:300].decode('utf-8', 'replace')}")
    finally:
        connection.close()
    payload = json.loads(raw)
    by_index = {int(item["index"]): [float(value) for value in item["embedding"]] for item in payload["data"]}
    if sorted(by_index) != list(range(len(texts))):
        raise ValueError(f"expected indexes 0..{len(texts) - 1}, received {sorted(by_index)}")
    usage = payload.get("usage") or {}
    return [by_index[index] for index in range(len(texts))], {"prompt_tokens": int(usage.get("prompt_tokens") or 0), "total_tokens": int(usage.get("total_tokens") or 0)}


def _chunks(items, size):
    if size < 1:
        raise ValueError("batch_size must be at least 1")
    items = list(items)
    return [items[start:start + size] for start in range(0, len(items), size)]


def embed(texts, *, base_url, model, batch_size=MAX_BATCH):
    out = []
    for chunk in _chunks(texts, batch_size):
        out.extend(_request(base_url, model, chunk)[0])
    return out


def _pack(vector):
    return array("d", vector).tobytes()


def _unpack(blob):
    values = array("d")
    values.frombytes(blob)
    return values.tolist()


class EmbeddingStore:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.execute("CREATE TABLE IF NOT EXISTS space (one INTEGER PRIMARY KEY CHECK (one = 1), model TEXT NOT NULL, version TEXT NOT NULL, dimension INTEGER NOT NULL)")
        self.db.execute("CREATE TABLE IF NOT EXISTS passages (id TEXT PRIMARY KEY, text TEXT NOT NULL, unit BLOB NOT NULL)")
        self.db.execute("CREATE TABLE IF NOT EXISTS usage_log (n INTEGER PRIMARY KEY AUTOINCREMENT, record TEXT NOT NULL)")
        self.db.commit()

    def close(self):
        self.db.close()

    def _space(self):
        return self.db.execute("SELECT model, version, dimension FROM space WHERE one = 1").fetchone()

    def metadata(self):
        space = self._space()
        if space is None:
            return None
        (count,) = self.db.execute("SELECT COUNT(*) FROM passages").fetchone()
        return {"model": space[0], "version": space[1], "dimension": space[2], "passages": count}

    def _guard(self, model, version, dimension):
        space = self._space()
        if space is None:
            raise ModelMismatch("the store is empty")
        if model != space[0] or (version is not None and version != space[1]):
            raise ModelMismatch(f"store is {space[0]}@{space[1]}, got {model}@{version}")
        if dimension != space[2]:
            raise DimensionMismatch(f"store dimension is {space[2]}, got {dimension}")

    def add(self, passages, vectors, *, model, version):
        passages, vectors = list(passages), list(vectors)
        if len(passages) != len(vectors):
            raise ValueError("passages and vectors differ in length")
        if not passages:
            return 0
        dimension = len(vectors[0])
        if any(len(vector) != dimension for vector in vectors[1:]):
            raise DimensionMismatch("vectors of one add call differ in dimension")
        if self._space() is None:
            with self.db:
                self.db.execute("INSERT INTO space (one, model, version, dimension) VALUES (1, ?, ?, ?)", (model, version, dimension))
        self._guard(model, version, dimension)
        with self.db:
            self.db.executemany("INSERT OR REPLACE INTO passages (id, text, unit) VALUES (?, ?, ?)", [(str(p["id"]), str(p["text"]), _pack(_unit(v))) for p, v in zip(passages, vectors)])
        return len(passages)

    def ingest(self, passages, *, base_url, model, version, batch_size=MAX_BATCH):
        records = []
        for chunk in _chunks(passages, batch_size):
            vectors, usage = _request(base_url, model, [p["text"] for p in chunk])
            self.add(chunk, vectors, model=model, version=version)
            record = {"model": model, "version": version, "dimension": len(vectors[0]), "inputs": len(chunk), **usage}
            with self.db:
                self.db.execute("INSERT INTO usage_log (record) VALUES (?)", (json.dumps(record),))
            records.append(record)
        return records

    def batches(self):
        return [json.loads(record) for (record,) in self.db.execute("SELECT record FROM usage_log ORDER BY n").fetchall()]

    def search(self, query_vector, k, *, model, version=None):
        if not isinstance(k, int) or isinstance(k, bool) or k < 1:
            raise ValueError("k must be a positive integer")
        query = _unit(query_vector)
        if self._space() is None:
            return []
        self._guard(model, version, len(query))
        ranked = []
        for passage_id, blob in self.db.execute("SELECT id, unit FROM passages"):
            ranked.append((-math.fsum(q * v for q, v in zip(query, _unpack(blob))), passage_id))
        ranked.sort()
        return [(passage_id, -negative) for negative, passage_id in ranked[:k]]

    def re_embed(self, new_model, embed_fn, *, version, batch_size=MAX_BATCH):
        rows = self.db.execute("SELECT id, text FROM passages ORDER BY id").fetchall()
        vectors = []
        for chunk in _chunks([text for _, text in rows], batch_size):
            produced = list(embed_fn(chunk))
            if len(produced) != len(chunk):
                raise ValueError("embed_fn must return one vector per text")
            vectors.extend(produced)
        with self.db:
            self.db.execute("DELETE FROM passages")
            self.db.execute("DELETE FROM space")
        return self.add([{"id": passage_id, "text": text} for passage_id, text in rows], vectors, model=new_model, version=version)
