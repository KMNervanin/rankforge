# Field manual — read the traces first

The operator assistant has been answering for two weeks and everybody has an opinion about what is wrong with it: "it hallucinates", "the tone is off", "it is slow". Nobody has read the traces. The starter ships a taxonomy written before anyone looked, with counts invented to add up, and code that reports those numbers back as if they were measured. That is the deliberate defect.

## Workshop and entry point

Python 3.10 or later, standard library only. The workspace holds `traces.jsonl` (120 recorded exchanges with the assistant), `fresh.jsonl` (20 more for the transfer step), your `annotations.jsonl`, your `taxonomy.json` and `taxonomy.py`, which must keep four names importable: `load_annotations`, `build_taxonomy`, `reconcile` and `recurrence`.

`python3 -B demo.py next` prints the first trace you have not annotated yet; `python3 -B demo.py show tr-0017` prints one trace; `python3 -B demo.py report` builds the taxonomy from your annotations and checks it against `taxonomy.json`; `python3 -B demo.py transfer` reads `fresh-annotations.jsonl` and reports which categories recur. No model is called in this mission and there is no `llm.json`.

## Why reading comes before categories

The evaluation method this mission follows (Husain and Shankar, AI Evals FAQ) starts with roughly a hundred diverse traces and asks you to annotate at least the first thirty by hand with open notes: write what you see in your own words, with no category in mind. Only after that do you group the notes into categories (open coding, then axial coding) and count. Two rules keep the counts honest. Each trace gets **one** label, the **first** failure you observe when reading the trace in order: request, retrieved passages, tool calls, answer. A trace whose tool call returned an error and whose answer is also cut off is labelled with the tool error, because that is where the exchange went wrong first. And every category must cite the traces it was built from, so the counts can be recomputed from the annotations and nobody can quote a number that has no traces behind it.

A trace in `traces.jsonl` is one JSON object per line: `trace_id` (`tr-0001` … `tr-0120`), `request` (the operator's text), `passages` (retrieved runbook and incident-report excerpts with `source`, `title`, `text`), `tool_calls` (each with `tool`, `arguments`, `result`), `answer` and `finish_reason`. Read the tool results and the cited sources, not only the answer: several failures are invisible from the answer alone. Read the unit in the request against the unit in the reserve call: a request in boxes booked in pieces is a failure. Read the relay number in the question against the incident report the answer retells: an answer about another relay's incident is not an answer to the question.

## Complete public contract

Trace ids match `[a-z]{2}-[0-9]{4}`. Verify uses its own ids (`vx-…`) in its fixtures and the shipped `tr-…` ids for your reading.

**`annotations.jsonl`** holds one JSON object per line, in the order you read: `trace_id`, `open_note` (your note, free text) and `first_failure`, which is `"pass"` or the name of a category. Extra keys are allowed; blank lines are ignored.

1. **`load_annotations(path) -> list[dict]`** returns the records in file order, each with at least `trace_id`, `open_note` (`""` when absent) and `first_failure` as written. It raises `ValueError` naming the trace id when `trace_id` is missing or empty, when `first_failure` is missing, empty or not a string (a list of two labels is two labels, not one first failure) or when the same `trace_id` appears twice. A line that is not a JSON object also raises `ValueError`.
2. **`build_taxonomy(annotations, definitions=None) -> dict`** derives the taxonomy from the annotations and nothing else: `{"total": number of annotations, "passes": number labelled pass, "categories": [...]}` with one category per distinct non-pass label, ordered by `count` descending and then by `name`. Each category is `{"name", "definition", "trace_ids", "count"}`: `trace_ids` in annotation order, `count == len(trace_ids)`, `definition` taken from the `definitions` mapping when given, otherwise `""`.
3. **`reconcile(annotations, taxonomy) -> list[str]`** returns `[]` when a taxonomy is consistent with the annotations and otherwise one string per inconsistency. Verify matches the prefix and the quoted name or id; the rest of the wording is yours. Any order.
   - `coverage: ` fewer than 100 annotations, or an annotation among the first 30 whose `open_note` is empty or whitespace (name its trace id).
   - `empty: ` a category with no trace ids (name the category). A taxonomy written before reading fails here.
   - `unknown: ` a category cites a trace id that has no annotation (name the category and the id).
   - `label: ` a category cites a trace whose annotation carries a different `first_failure`, including `pass` (name the id).
   - `count: ` a category's `count` differs from the number of distinct ids it cites (name the category); an id repeated inside one category counts once.
   - `missing: ` an annotation with a failure label that no category of that name cites (name the id). This covers a label whose category does not exist.
   - `total: ` `total` differs from the number of annotations, `passes` differs from the number of pass annotations, or the sum of the counts plus `passes` differs from `total`.
   - Hidden bonus: `example: ` a category whose definition does not mention one of its own trace ids (name the category).
4. **`recurrence(taxonomy, new_annotations) -> dict`** applies an existing taxonomy to a fresh batch and recomputes every number from the new annotations: `{"total": n, "passes": p, "recurring": {name: count} for the taxonomy's categories with at least one new annotation, "absent": [names of the taxonomy's categories with none, in taxonomy order], "new": {label: count} for failure labels the taxonomy does not have}`. The taxonomy's own counts never appear in the result.

**`taxonomy.json`** is your counted taxonomy of `traces.jsonl` in the shape `build_taxonomy` returns, with a non-empty `definition` for every category. Writing it by `python3 -B demo.py report` and pasting is fine; the definitions are yours.

A worked example. Three annotations: `tr-0001` labelled `tool error hidden`, `tr-0002` labelled `invented source`, `tr-0005` labelled `pass`. `build_taxonomy` returns `total 3, passes 1` and two categories of count 1, `invented source` before `tool error hidden` (equal counts, alphabetical). If `taxonomy.json` lists `tool error hidden` with `trace_ids: ["tr-0001", "tr-0002"]` and `count: 2`, `reconcile` reports `label: tr-0002 …` (its annotation says `invented source`), `missing: tr-0002 …` (no category named `invented source` cites it), `total: …` (2 + 1 passes ≠ 3) and `coverage: …` (three annotations are fewer than 100).

## What Verify runs

- **Fresh annotation fixtures** with `vx-` ids and random counts: a consistent set of at least 100 annotations with notes on the first 30, loaded and built into a taxonomy whose counts Verify recomputes by hand; a duplicated id, a two-label list and a missing label that must raise; planted taxonomies with one inconsistency each (an unknown id, a wrong count, a cited pass, an uncited failure, a wrong total, a category with no trace references); sets of 99 annotations and of 100 with an empty note among the first 30; and a fresh batch of 30–60 annotations whose recurrence Verify recounts itself.
- **Your reading.** Verify parses your `annotations.jsonl` and `taxonomy.json` itself: at least 100 of the shipped `tr-` ids annotated, each at most once, and no other ids (your reading of `fresh.jsonl` goes in `fresh-annotations.jsonl`), non-empty notes on the first 30 lines, one label or `pass` per trace, and the taxonomy consistent with the annotations under the rules above, with a non-empty definition per category. Verify also knows which shipped traces were recorded with a failure: up to 12 of your pass-or-failure decisions may disagree with that record; the category names and the grouping are yours and are reviewed in the debrief, not by code.
- The whole run is offline and finishes in under five seconds.

Two different implementations pass: a dictionary-and-`Counter` ledger, and a SQLite in-memory table that reconciles with joins. No specific structure of `taxonomy.py` is required beyond the four importable names.

## Sources

- Hamel Husain and Shreya Shankar, AI Evals FAQ: start with about 100 diverse traces, annotate at least the first 30 by hand with open notes, then open and axial coding into categories; label the first failure per trace.
- Hamel Husain, "Your AI product needs evals": error analysis before any metric.
