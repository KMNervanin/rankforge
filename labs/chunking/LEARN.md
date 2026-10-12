# Field manual — where to cut

The archive extractor now hands the assistant runbooks and incident reports as ordered passages: headings, numbered steps, paragraphs, and safety warnings attached to steps. Before anything is indexed you must decide where a document is cut into chunks, and prove with numbers that the cut keeps answers findable. The starter cuts every document into fixed slices of characters, drops the warning that belongs to a step, aggregates recall from counters instead of rankings and then picks whichever strategy scores highest no matter what it costs. Those are the deliberate defects.

## Workshop and entry point

Python 3.10 or later, standard library only. Edit `chunker.py` and keep five names importable: `chunk`, `audit`, `evaluate`, `metrics` and `choose`. Verify imports your module and calls them with keyword arguments; it carries its own passages, questions, sizes and embedding function, so never rely on a fixed text or a fixed number. `passages.json` and `questions.json` are the sample archive for your own runs: two runbooks and one incident report, six questions.

`python3 -B demo.py compare` chunks the sample both ways, evaluates them and prints the decision. `python3 -B demo.py fixed 32 8`, `structural 32` and `semantic 64 0.08` print the chunks of one strategy; `python3 -B demo.py audit 32` lists the steps that fixed chunking of that size separated from their warnings. The demo embeds with a hashed bag of words so that it runs offline; there is no model and no network in this mission.

## The problem

Retrieval returns chunks, not documents. A chunk that is too small loses the context an answer needs; a chunk that is too large dilutes it and costs more to embed, store and feed to the model. Chroma's 2024 study compared fixed-size, recursive and semantic chunkers by recall and precision on question→passage sets and found that the strategy, not the embedding model, often decides whether a passage is retrievable at all. For a runbook there is one cut that is never acceptable: between a procedure step and the safety warning that belongs to it. A chunk that says "open the clamp" without "wait 90 seconds first" is an answer the assistant must never give.

## Passages, words and units

A passage is a dict with `id`, `doc_id`, `kind` (`heading`, `step`, `paragraph`) and `text`. A step may carry a `warning` string. Passages arrive grouped by document, in document order.

The **text of a passage** is its `text`, followed by a newline and `Warning: <warning>` when it has a `warning` field. The **word stream** of a document is the concatenation of its passages' texts split on whitespace (`str.split()`), in order. Every chunk is a half-open slice `[start, end)` of that stream, and `size` and `overlap` count words of it.

A **unit** is one passage, except that a step with its warning forms one unit together with it: the `warning` field is part of the step's own text, and a `paragraph` whose own text starts with `Warning:` (case-insensitive) and which immediately follows a step belongs to that step. A step that already carries a `warning` field does not absorb a following paragraph: that paragraph is a unit of its own. A unit with a warning is **separated** when no single chunk holds all of its words.

## Complete public contract

```python
chunk(passages, strategy, *, size, overlap=0, embed=None, threshold=0.3) -> list[chunk]
audit(chunks, passages) -> list[violation]
evaluate(chunks, questions, embed, k_values) -> report
metrics(report) -> {"recall": {...}, "mrr": {...}}
choose(reports, target_recall, *, k) -> decision
```

A chunk is a dict with `id` (unique within one call), `doc_id`, `strategy`, `start`, `end` (integer word offsets, `start < end`), `text` (exactly `" ".join(words[start:end])`) and `passage_ids` (every passage with at least one word in `[start, end)`, in document order).

1. **`fixed`** slides a window of `size` words with a stride of `size - overlap`: windows start at 0, then every stride, until a window reaches the end of the stream; the last window may be shorter. `overlap` must satisfy `0 <= overlap < size`, otherwise `ValueError`; an unknown strategy is a `ValueError` too.
2. **`structural`** cuts only between units. Chunks of one document are contiguous and disjoint and reach the end of the stream. A chunk holds at most `size` words unless it is a single unit longer than `size`. A chunk may be closed before the next unit only when that unit would not fit or is a heading.
3. **`semantic`** (optional, the hidden bonus) embeds every unit's text with `embed` and closes a chunk before a unit when the cosine similarity between it and the previous unit is below `threshold` or when it would not fit; otherwise the unit joins the chunk. Headings do not force a cut in `semantic`; only the similarity drop or the size bound closes a chunk. Without `embed` it is a `ValueError`.
4. **`audit`** returns one violation per separated unit: `{"doc_id", "step_id", "warning_id"}`, where `warning_id` is the id of the Warning paragraph, or the step's own id when the warning is a field. A step without a warning may be cut anywhere. Structural chunks never produce a violation.
5. **`evaluate`** embeds every chunk text and every question text with the injected `embed(texts) -> list[list[float]]` and ranks all chunks per question by cosine similarity, descending, ties broken by chunk id ascending. A chunk is a **hit** when its `passage_ids` share an id with the question's `expected`. The report carries `strategy`, `k_values`, `chunk_count`, `avg_words` (mean of `len(text.split())`), `coverage` (chunk id → `passage_ids`), `questions` (per question: `id`, `expected`, `ranking` = every chunk id once, in rank order), `recall` and `mrr`, the last two keyed by the k as a string with float values (compute with `Fraction`, convert with `float()` before storing).
6. **Metrics recompute from the rankings.** Per question, recall@k is the fraction of expected passage ids covered by the union of the top-k chunks; MRR@k is `1 / rank` of the first hit within the top k, else 0. The aggregates are plain means over the questions. `metrics(report)` recomputes both from `questions` and `coverage` alone; a report whose stored aggregates were tampered with still yields the true numbers. Tolerance 1e-9.
7. **`choose`** recomputes recall@k for every report with `metrics` and picks, among those with `recall >= target_recall`, the cheapest: fewest chunks, then smallest `avg_words`, then strategy name. The decision carries `strategy` (`None` when nothing meets the target), `k`, `target_recall`, `candidates` (one per report, in order: `strategy`, `recall`, `mrr`, `chunk_count`, `avg_words`, `meets`) and a `reason` string that contains the chosen strategy name and its recall as a decimal (e.g. `0.75` or `0.750`), never as a percentage or a fraction.

Worked example: three chunks `a → [p1]`, `b → [p2]`, `d → [p1, p2]`; a question expecting `[p1, p2]` ranked `a, d, b`. Recall@1 is 1/2 (only `p1` covered), recall@2 is 1 (`a ∪ d` covers both), MRR@1 and MRR@2 are both 1 because the first hit is at rank 1.

## What Verify runs

Fresh passages (ids and numbers change every run), a scripted `embed` that is a hashed bag of words, and these checks: fixed windows against the stride rule with overlap 0 and a random overlap; structural invariants and `audit() == []`; `audit` on hand-cut chunks that split a warning field, a Warning paragraph, neither and only part of one; every ranking against cosine order and both aggregates recomputed with `Fraction`, including a tampered report; `choose` on synthetic reports where the highest recall is not the cheapest and where the aggregates are forged; one question whose answer is a step with its Warning paragraph that only an unsplit chunk retrieves at rank 1, with a declared target that fixed chunking misses; and a generated runbook more than fifty times longer with the same guarantees under the same size. The bonus runs `semantic` with a threshold chosen inside the spread of adjacent similarities.

Two different implementations pass: an explicit per-document word stream with `Fraction` metrics, and a cursor over passage boundaries with `bisect`, generators and float means.

## Sources

- Chroma Research, "Evaluating Chunking Strategies for Retrieval" (2024): fixed-size, recursive and semantic chunkers compared by recall and precision on question→passage sets.
- Sentence Transformers, `InformationRetrievalEvaluator`: MRR@k and Recall@k as used here, averaged over queries.
- Python `fractions.Fraction`: exact arithmetic for the recomputation.
