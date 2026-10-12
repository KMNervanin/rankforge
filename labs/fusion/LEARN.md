# Field manual — two lists, one ranking

The archive now answers every operator question twice: the lexical index returns the passages that share the words, the dense store returns the ones that share the meaning, and the assistant has to hand the model one list. A cross-encoder reranker is on offer that reads the question with each candidate and scores the pair, and it is slow. The starter adds the two lists' raw scores together, reranks everything it has and keeps the reranker because the MRR went up. Those are the deliberate defects.

## Workshop and entry point

Python 3.10 or later, standard library only. Edit `fusion.py` and keep five names importable: `rrf`, `weighted`, `rerank`, `measure` and `decide`. Verify imports your module and calls each with explicit arguments: it injects the two retrievers, the reranker's scoring function and the clock, so nothing in this mission touches the network or a model. `rankings.json` holds canned lists, scripted reranker scores and declared costs for your own terminal runs; Verify carries its own lists, scores and costs with fresh ids and numbers on every run.

`python3 -B demo.py` runs the six questions through your pipeline on a simulated clock and prints the fused and reranked rankings, the aggregates and the decision. `python3 -B demo.py --budget 25` tightens the latency budget; `--top-n 2` narrows the rerank. The demo's scorer is a script with a declared cost per pair, not a model: it exists so the whole pipeline can be read before real numbers arrive.

## The problem

A lexical score (BM25, larger is better) and a cosine similarity live on different scales, so adding them means nothing: a BM25 of 9.4 swamps a cosine of 0.77 whatever the passages are. Reciprocal rank fusion (Cormack, Clarke and Büttcher, SIGIR 2009) ignores scores and uses only positions: a document that is near the top of several lists wins. The constant `k` damps the advantage of the very first positions; 60 is the published default and the value Elasticsearch (`rank_constant`) and OpenSearch use.

A cross-encoder reranker scores one `(query, document)` pair per forward pass, so its cost grows with the number of candidates it sees. It is applied to the top `N` of a fused list, never to the corpus, and it is kept only when its ranking gain pays for its latency at the percentile the operator feels: p95, not the mean.

## Complete public contract

A **ranking** is a list of `(id, score)` pairs, best first; position 1 is the first pair. Every function below returns a ranking as a list of `(id, score)` tuples that holds each id once and is sorted by score descending, then id ascending (the **tie rule**).

```python
rrf(rankings, k=60) -> ranking
weighted(rankings, weights) -> ranking
rerank(candidates, query, score_fn, top_n) -> ranking
measure(queries, retrievers, *, clock, score_fn, top_n, k=60) -> report
decide(report, budget) -> decision
```

1. **`rrf`.** `score(d) = Σ over the lists that contain d of 1 / (k + rank(d))`, ranks starting at 1, input scores ignored. Verify compares with exact fractions within 1e-12 at `k=60` and at a fresh `k`. A `k` of zero or less is a `ValueError`. Input lists hold each id once. A per-list weight, if you offer one, multiplies that list's vote: `Σ w_r / (k + rank)`; pass it as `weights=` to `rrf`.
2. **`weighted`** is the alternative fusion: min-max normalize each list on its own, `(s − min) / (max − min)`, every score `1.0` when a list's scores are all equal, then `score(d) = Σ weight_r × normalized_r(d)` with 0 for a list that lacks `d`. One weight per list; tolerance 1e-9.
3. **`rerank`.** Call `score_fn(query, id)` once for each of the first `top_n` candidates and for no other id; the result is those candidates sorted by the scorer's score under the tie rule, followed by the remaining candidates in their fused order with their fused scores. A `top_n` above the candidate count reranks every candidate once; `top_n = 0` reranks nothing and returns the candidates unchanged; a negative `top_n` raises `ValueError`. The scorer counts its calls: reranking the whole list fails the cost check.
4. **`measure`.** `queries` is a non-empty list of `{"id", "text", "expected"}` (`measure` is never called with an empty query list); `retrievers` is a list of callables `retriever(text) -> ranking`, each called exactly once per query, in query order; `clock()` returns seconds as a float and is the **only** clock you read; `score_fn` is the reranker. For each query: fuse the retriever results with `rrf(…, k)`, then `rerank(fused, text, score_fn, top_n)`. The **fused latency** is `clock()` just after fusion minus `clock()` just before the first retriever, in milliseconds (`× 1000`); the **reranked latency** is measured from the same start to just after the rerank, so it is the fused latency plus the rerank stage. Verify's retrievers and scorer advance the injected clock by declared amounts (the scorer per pair), so both numbers are exact to 1e-6 ms; a wall clock gives noise and fails.
5. **The report** is a dict with `k`, `top_n`, `queries`, `samples`, `mrr`, `p50_ms` and `p95_ms`. `queries` holds one entry per query in order: `id`, `fused` (list of ids), `reranked` (list of ids), `hit` = `{"fused": r, "reranked": r}` with the 1-based position of `expected` or `None`, and `latency_ms` = `{"fused": ms, "reranked": ms}`. `samples` = `{"fused": [ms per query], "reranked": [...]}` in query order. The three aggregates are dicts keyed `fused` and `reranked`: **MRR** is the mean over queries of `1 / hit rank` with 0 for a miss; **p50** and **p95** use the nearest-rank method: sort the samples ascending and take the `ceil(P / 100 × n)`-th one (at least the first). With 20 samples, p95 is the 19th smallest, not the maximum. Tolerance 1e-9 for MRR, 1e-6 ms for the percentiles; the sample lists are never empty.
6. **`decide`.** `budget` is `{"min_mrr_gain": g, "p95_ms": ms}`. Recompute from the raw rows, never from the report's summaries: `mrr_gain` = reranked MRR − fused MRR from `queries[*].hit`, `p95_ms` = nearest-rank p95 of `samples["reranked"]`, `p95_added_ms` = that minus the fused p95. Keep the reranker (`rerank: True`) only when `mrr_gain >= min_mrr_gain` **and** `p95_ms <= budget p95_ms`; otherwise drop it. The decision carries `rerank`, `mrr_gain`, `p95_ms`, `p95_added_ms`, `min_mrr_gain`, `p95_budget_ms` and `rule`, a sentence that contains the words MRR and p95 and their numbers (a digit within a few characters of each word). If `samples` is missing or either sample list is empty, raise `ValueError`: an MRR gain with no latency measurement never adopts a reranker. A tighter budget on the same report flips the verdict to drop.

Worked example at `k = 60` with three lists, `L = [a, b, c, d]`, `D = [c, a, e]`, `T = [b, e, a, f]`: `a` is in all three, at positions 1, 2 and 3, so `score(a) = 1/61 + 1/62 + 1/63 = 0.048395…`; `b` scores `1/62 + 1/61 = 0.032522…`, `c` `1/63 + 1/61 = 0.032266…`, `e` `1/63 + 1/62 = 0.032002…`, and `d` and `f` both score `1/64 = 0.015625` and are ordered by id. The fused ranking is `a, b, c, e, d, f`. With `top_n = 3` the reranker sees `(query, a)`, `(query, b)` and `(query, c)` and nothing else; `e, d, f` keep their places behind the reranked three.

## What Verify runs

Fresh ids, a fresh `k`, fresh weights and fresh costs on every run. The checks: RRF on three overlapping lists at `k=60` and a fresh `k`; the tie rule in `rrf` and `weighted`; weighted fusion on a published fixture, including a flat list; a counting scorer that must see exactly the top `N` pairs; twenty queries over twelve passages through `measure` with canned retrievers that charge the injected clock, every fused and reranked list, hit rank and latency recomputed; MRR, p50 and p95 recomputed from the raw samples; a hand-built report with deliberately stale summaries where the reranker pays under one budget and not under a higher minimum gain; a report with an MRR gain and no latency samples that must raise `ValueError`; and the same report under a tighter latency budget that must drop. One hidden bonus check exists; it can only add to the result and never fails the run. No model output takes part in any verdict.

Two different implementations pass: dicts, tuples and floats with `sorted`, and dataclasses with exact `Fraction` scores and a heap. No structure of `fusion.py` is required beyond the five importable names.

## Sources

- Cormack, Clarke and Büttcher, "Reciprocal Rank Fusion outperforms Condorcet and individual Rank Learning Methods", SIGIR 2009: `1 / (k + r)` with `k = 60`.
- Elasticsearch reciprocal rank fusion reference (`rank_constant` 60) and OpenSearch hybrid search with RRF: the same formula in production search engines.
- pgvector-python `examples/hybrid_search/rrf.py`: RRF over a full-text and a vector query in a few lines.
- Sentence-Transformers, "Retrieve & Re-Rank": the cross-encoder scores the top candidates of a fast retriever, not the corpus, because it is slower by orders of magnitude.
- Nearest-rank percentile: sort, take the `ceil(P/100 × n)`-th sample.
