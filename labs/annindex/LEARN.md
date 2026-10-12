# Field manual — an index at scale

The archive has grown past the point where comparing a question with every passage is cheap, and every outpost must only ever see its own runbooks. The starter has an approximate index that probes a few lists, keeps its best candidates and filters them by outpost afterwards, so a query for ten passages quietly returns two; its report times the searches but never measures what the index loses, and the parameters come from the first row of the grid. That is the deliberate defect.

## Workshop and entry point

Python 3.10 or later, standard library only. Edit `annindex.py` and keep four names importable: the classes `ExactIndex` and `ApproxIndex` and the functions `measure` and `tune`. Verify imports your module, builds both indexes from its own seeded vectors, computes every exact top-k itself and recomputes recall from the ids your index returned. `grid.json` holds the parameter grid, the bound and the outpost sizes for your own terminal runs; Verify carries its own values and a fresh seed on every run.

`python3 -B demo.py` generates about three thousand clustered vectors for three outposts, tunes your index over the grid, prints every candidate with its recall and scan count, and runs one filtered query on the smallest outpost. `--scale 10` is the tenfold archive, `--outpost beta --k 25` a different filter. There is no live call in this mission: the vectors are generated deterministically from a seed, so the index algorithm, the filter and the measurement are the whole exercise.

## The problem

pgvector does exact nearest-neighbour search by default: it compares the query with every row and returns the true top-k. An HNSW or IVFFlat index makes that search sublinear by looking at a fraction of the rows, and it pays with recall: with the defaults (`hnsw.ef_search` 40, `ivfflat.probes` 1) some of the true neighbours are simply not visited. Recall@k is the share of the exact top-k that the approximate index returned. You do not know it until you measure it against exact search on your own data, and the right parameters are the cheapest ones that keep it above the bound you declared.

The access filter is the second half. If the index returns its k best candidates first and a `WHERE outpost = 'beta'` runs afterwards, the filtered result holds whatever survived: two rows of ten, or none, with no error. pgvector 0.8.0 added iterative index scans (`hnsw.iterative_scan`) that keep scanning until enough rows pass the filter; the older remedies are a partial index per filter value or a partition per tenant. Either way the filter runs inside or before the scan, never after a fixed candidate list.

In this mission you write the small index yourself, IVF-style (k-means lists with `probes`) or LSH (random hyperplanes with multi-probe buckets); HNSW is allowed but not required. The point is the measurement and the filter semantics, not the index algorithm.

## Complete public contract

```python
ExactIndex(dim).build(items) -> self
ApproxIndex(dim, *, seed, lists=16, probes=1).build(items) -> self
index.search(query, k, *, outpost=None) -> {"results": [(id, score), …], "truncated": bool, "scanned": int}
index.count(outpost=None) -> int
index.build_seconds -> float                       # measured around build()
ApproxIndex.params -> {"lists": int, "probes": int}
measure(exact, approx, queries, k) -> report
tune(exact, items, queries, k, *, grid, bound, seed) -> {"params", "report", "candidates", "bound"}
```

`items` is a list of `{"id": str, "outpost": str, "vector": [float] * dim}`; vectors have different lengths. A query is a list of `dim` floats, and in `queries` each entry is `{"vector": […], "outpost": str | None}`.

1. **Results.** `score` is cosine similarity, the dot product divided by both lengths, within 1e-9 of Verify's own value. Results are sorted by score descending, then id ascending. `search` returns `min(k, count(outpost))` results and `truncated` is `True` exactly when the outpost (or the whole archive when `outpost` is `None`) holds fewer than `k`. `scanned` is the number of stored vectors whose score you computed. `ExactIndex` compares the query with every vector that passes the filter; its results are the reference the approximate index is measured against.
2. **The filter.** A search with `outpost=X` returns only ids stored with outpost `X`. Two published strategies are acceptable: a partition per outpost (a partial index per filter value, searched on its own) or an iterative scan that applies the filter inside the scan and keeps opening the next-best list or bucket until `k` matches are in hand or every candidate has been read. Never filter a fixed candidate list after the fact: an outpost with at least `k` passages gets exactly `k`, every time, for every `probes` value.
3. **Deterministic.** The same `seed`, the same items and the same params build an index that returns the same results for the same query. Verify rebuilds your index with its seed and expects the ids your report lists.
4. **The report.** `measure` runs every query through both indexes and returns a dict with `k`, `queries` (the count), `params` (the approximate index's), `build_seconds` (its `build_seconds`), `per_query`, `recall_mean`, `recall_min`, `scanned_mean`, `exact_scanned_mean`, `approx_p50_ms`, `approx_p95_ms`, `exact_p50_ms` and `exact_p95_ms`. Each `per_query` entry, in query order, carries `outpost`, `ids` (the approximate results in order), `returned`, `truncated`, `recall`, `scanned`, `exact_scanned`, `approx_ms` and `exact_ms`. Recall@k of one query is `|approximate ids ∩ exact ids| / |exact ids|` (`1.0` when exact search found nothing); the means are plain arithmetic means over the queries, `recall_min` the smallest per-query recall. Latencies are measured around each `search` call in milliseconds; the percentiles are nearest-rank: sort the values and take the element at index `ceil(fraction × n) − 1`.
5. **Tuning.** `tune` builds one `ApproxIndex` per grid entry with the given `seed`, measures it on `queries` and lists every entry in grid order under `candidates` as `{"params", "recall_mean", "scanned_mean", "approx_p50_ms", "build_seconds", "meets"}` with `meets = recall_mean >= bound`. `params` is the cheapest candidate that meets the bound, cheapest meaning the smallest `scanned_mean` (ties go to the earlier grid entry), and `report` is its full report. When no entry meets the bound, `params` and `report` are `None` and the candidates say so: honest failure is a valid outcome of a tenfold archive.
6. **Timing.** `build_seconds` is measured around `build()` and is positive; per-query latencies cannot add up to more than the time `measure` took. An approximate index that compares as many vectors as exact search is not approximate: `scanned_mean` must be below `exact_scanned_mean`.

Worked example. Exact top-3 for a query is `[a, b, c]`; your index returns `[a, c, x]`: recall@3 is 2/3 ≈ 0.667. Outpost gamma holds 7 passages and the operator asks for 10: the result has 7 ids and `truncated: True`, from both indexes. The defect: the global top-10 holds 8 passages from alpha and 2 from beta; filtering that list for beta returns 2 with `truncated: False`, while beta holds 1400 passages. With a grid of `probes` 1, 2, 4, 8 and 16 over 32 lists, an IVF index on clustered data measures recall 0.78, 0.97, 1.0, 1.0, 1.0 and scans 61, 111, 202, 368 and 719 of about 1900 vectors: the choice for a bound of 0.9 is `probes: 2`.

## What Verify runs

A fresh seed generates 32-dimensional vectors around 24 topics for three outposts (1500, 1400 and 7 passages), plus 48 near-duplicates of six query vectors planted in the wrong outpost, and 30 queries (unfiltered, alpha, beta and two for gamma); k is 10 and the bound 0.9. The checks: your `ExactIndex` matches Verify's own top-10 with and without the filter, scores within 1e-9; a filtered approximate query never returns a planted duplicate from another outpost; a query for gamma returns all 7 with `truncated: True`, `k=3` returns 3, alpha and beta return exactly 10 and 25 on request, and `k` above the archive size returns everything; `tune` over `lists: 32, probes: 1, 2, 4, 8, 16` reports every candidate's recall and scan count as Verify recomputes them by rebuilding each entry with your class, chooses the cheapest meeting the bound, and the chosen report's per-query recall, means and ids recompute from your own results while a second build with the same seed returns the same ids; build time and latencies are present, consistent with the wall clock and with nearest-rank percentiles, and the index scans fewer vectors than exact search; the tenfold archive (about 29,000 vectors, grid `lists: 64, probes: 4, 16, 32, 48`) either meets the bound with the chosen params on recomputation or reports honestly that no entry does, within a 28 second budget. One hidden bonus check exists; it can only add to the result and never fails the run. No model output takes part in any verdict.

Two different implementations pass: IVF with spherical k-means and one partial index per outpost (filter, then search, widening to the next list until k), and multi-probe LSH over one global table whose iterative scan applies the filter inside the scan. No structure of `annindex.py` is required beyond the four importable names.

## Sources

- pgvector README: exact search by default; HNSW and IVFFlat trade recall for speed (`hnsw.ef_search` 40, `ivfflat.probes` 1); filtering after an approximate scan can return fewer than k rows; iterative index scans since 0.8.0 (`hnsw.iterative_scan`, `hnsw.max_scan_tuples`); partial indexes and partitioning per filter value.
- Faiss wiki, "Faster search": IVF partitions, `nprobe` and the recall/speed trade-off measured against brute force.
- Lv, Josephson, Wang, Charikar, Li, "Multi-probe LSH" (VLDB 2007): probe the neighbouring buckets in order of perturbation cost instead of building more hash tables.
- sqlite-vec README: a pre-1.0 brute-force vector extension for SQLite, the exact baseline when the archive lives there.
