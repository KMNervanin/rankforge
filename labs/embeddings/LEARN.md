# Field manual — meaning as numbers

The archive of runbooks and incident reports is growing faster than anyone can read it, and the assistant will soon have to find the passage that answers a question instead of the passage that shares a word with it. The starter already turns passages into vectors and ranks them; it just forgets which model made the vectors, scores them with a bare dot product and loses everything when the process ends. Those are the deliberate defects.

## Workshop and entry point

Python 3.10 or later, standard library only; SQLite through the `sqlite3` module. Edit `store.py` and keep these names importable: the constant `MAX_BATCH`, the exceptions `ModelMismatch` and `DimensionMismatch` (both subclasses of `ValueError`), the functions `cosine` and `embed`, and the class `EmbeddingStore`. Verify imports your module, drives it through a scripted adapter and inspects the SQLite file it writes.

`python3 -B demo.py "which runbook covers a power dip"` ingests `passages.json` into `archive.sqlite` and prints the top-3 with scores, using the endpoint and `embedding_model` in `llm.json`. For Ollama: `ollama pull nomic-embed-text`, then put `nomic-embed-text` into `embedding_model`. An API key, if your endpoint needs one, lives in `LLM_API_KEY`, never in a file of this workspace. `--re-embed other-model` switches the archive to a second model and asks again.

## The concept, once

An embedding model maps a text to a vector of fixed length (its *dimension*: 768 for `nomic-embed-text`, 1536 for `text-embedding-3-small`). Texts with related meaning land close together, and "close" is measured by **cosine similarity**: the cosine of the angle between the two vectors,

```
cosine(a, b) = (a · b) / (|a| · |b|)        a · b = Σ aᵢbᵢ,   |a| = √(Σ aᵢ²)
```

It ranges from −1 to 1 and ignores length: `(3, 4)` and `(6, 8)` have cosine 1. When vectors are **L2-normalized** (length 1, as OpenAI's embeddings are), the division disappears and cosine equals the plain dot product. That is the only shortcut this mission allows, and only after you normalized.

Worked example: `cosine([3, 4], [4, 3]) = (12 + 12) / (5 × 5) = 0.96`. For `[1, 2, 2]` and `[2, 0, 1]`: `(2 + 0 + 2) / (3 × √5) = 0.5963…`.

Vectors are only comparable when the **same model, the same version and the same dimension** produced both sides. A query embedded with model B against passages embedded with model A gives numbers that look like scores and mean nothing. Vector databases key their indexes per model id and dimension for exactly this reason; your store does the same.

## The API you talk to

`POST {base_url}/embeddings` with the JSON body `{"model": "<id>", "input": ["text one", "text two"]}`. The response:

```json
{"object": "list",
 "data": [{"object": "embedding", "index": 0, "embedding": [0.0123, -0.0456, …]}, …],
 "model": "<id>",
 "usage": {"prompt_tokens": 17, "total_tokens": 17}}
```

`data[i].embedding` is the vector for `input[j]` where `j = data[i].index`: order by `index`, not by position. Every string of `input` must be non-empty. Servers cap the number of inputs per request (OpenAI: 2048); this mission publishes its own cap as `MAX_BATCH = 16`. Ollama serves the same route; it ignores `encoding_format` and `dimensions`.

## Complete public contract

```python
MAX_BATCH = 16
class ModelMismatch(ValueError): ...
class DimensionMismatch(ValueError): ...

cosine(a, b) -> float
embed(texts, *, base_url, model, batch_size=MAX_BATCH) -> list[list[float]]

class EmbeddingStore:
    __init__(path)                                              # a SQLite file; created when missing
    close()
    metadata() -> dict | None                                   # {"model", "version", "dimension", "passages"} or None when empty
    add(passages, vectors, *, model, version) -> int
    ingest(passages, *, base_url, model, version, batch_size=MAX_BATCH) -> list[dict]
    batches() -> list[dict]
    search(query_vector, k, *, model, version=None) -> list[tuple[str, float]]
    re_embed(new_model, embed_fn, *, version, batch_size=MAX_BATCH) -> int
```

A passage is `{"id": str, "text": str}`. A vector is a list of numbers; Verify compares scores with a tolerance of 1e-9.

1. **`cosine(a, b)`** is the formula above. If either vector has length 0, return `0.0`. Different dimensions raise `DimensionMismatch`.
2. **`embed`** sends `input` as a list of texts in the given order, at most `batch_size` per request, and returns one vector per text, in the same order, taken from `data[i].embedding` ordered by `index`. Transport errors may raise any exception.
3. **A store has one model.** The first `add` fixes `model`, `version` and `dimension` (the length of the vectors) and `metadata()` reports them with `passages`, the number of stored vectors. A later `add` whose `model` or `version` differs raises `ModelMismatch`; a vector whose length differs from the store's dimension raises `DimensionMismatch`. Model and version are compared first; dimension only after the identity matched. A refused `add` stores nothing. An `id` already present is replaced. `add` returns the number of passages stored.
4. **`ingest`** embeds `passages` through `embed` in batches of at most `batch_size`, stores them with `add`, and records one **batch record** per request: `{"model", "version", "dimension", "inputs", "prompt_tokens", "total_tokens"}` where `inputs` is the number of texts in that request and the token counts come from the response's `usage`; a missing `usage` counts as 0 tokens. It returns the records of this call; `batches()` returns every record ever stored, in order. The records survive a reopen.
5. **`search`** compares the query with every stored vector (brute force, no index) and returns the `k` best `(id, score)` pairs with `score = cosine(query, vector)`, sorted by score descending, then by `id` ascending (string order) on equal scores. Fewer than `k` results when the store is smaller, `[]` on an empty store; `k < 1` raises `ValueError`. A `model` different from the store's, or a `version` given and different, raises `ModelMismatch`; a query of another dimension raises `DimensionMismatch`. Model and version are compared first; dimension only after the identity matched. Storing L2-normalized vectors and using a dot product is acceptable only if the result equals cosine for vectors of any length.
6. **Persistence.** Everything lives in the SQLite file at `path`: a new `EmbeddingStore(path)` in a fresh process answers the same `metadata()`, `batches()` and `search` results. Nothing may depend on the Python objects of the process that wrote it.
7. **`re_embed(new_model, embed_fn, *, version)`** rebuilds the store under a new model: it calls `embed_fn(texts)` with the stored texts in `id` order, at most `batch_size` texts per call, expects one vector per text, replaces every vector, sets `metadata()` to the new model, version and dimension, and leaves no row holding an old-model vector in any table. It returns the number of passages re-embedded. On an empty store `re_embed` returns 0 and never calls `embed_fn`. Afterwards a query from the old model is refused.

## What Verify runs

- A **scripted adapter**: a loopback server speaking the `/embeddings` contract above. It answers with deterministic unit vectors computed from a salted hash of the words of each text, 8 dimensions for `relay-embed-a` and 12 for `relay-embed-b`, records every request body and counts tokens its own way. It is a labeled test tool, not a model. The salt and the passage ids are fresh on every run.
- Cosine on hand-computed vectors; `embed` and `ingest` through the adapter with the request bodies, metadata and batch usage inspected; top-k for several queries and `k` values against a reference computed with exact arithmetic from the same vectors, including a tie between two identical passages; hand-added vectors of different lengths; refusals on `add` and `search`; a reopen of the SQLite file in a fresh Python process; `re_embed` to the 12-dimensional model with a scan of the file for leftovers. The hidden bonus uses an adapter that caps inputs per request and returns `data` out of order.
- A **live measurement**, only when `llm.json` carries an `embedding_model`: four passages and one query through your `ingest` and `embed` against that endpoint, reporting the dimension and the top-2 as numbers. No `embedding_model`, or no answer within 15 seconds, is **Environment blocked**: nothing fails, nothing passes, and the adapter checks stand on their own.

Two different implementations pass: JSON vectors with cosine on every search, and float64 BLOBs normalized on add with a dot product on search.

## Sources

- OpenAI embeddings guide and API reference: request and response shape, `index`, `usage`, 2048 inputs per request, vectors normalized to length 1 so dot product equals cosine.
- Sentence-Transformers, semantic textual similarity: cosine as the default similarity; embed the query with the model that embedded the corpus.
- Pinecone quickstart: a query must be embedded with the same model as the records it is compared with.
- pgvector README: indexes keyed per model id and dimension; exact (brute-force) search is the default and the reference for approximate indexes.
- Ollama OpenAI compatibility: `/v1/embeddings` with `input` as a string or a list.
