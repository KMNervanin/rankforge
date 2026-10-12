# Field manual — fit the window

The operator assistant now has instructions, pinned facts, a runbook, an incident report and a morning of chat to carry into every call, and the relay's model has one window for all of it plus the answer. The starter stuffs everything in and, when it runs out of room, cuts whatever sorted last: the instructions. That is the deliberate defect.

## Workshop and entry point

Python 3.10 or later, standard library only. Edit `context.py` and keep three names importable: the class `BudgetError`, the function `estimate` and the function `build`. Verify imports your module, calls `build` with explicit keyword arguments and its own counting function, and reads the messages and the report it returns. `context.json` is a sample call for your own terminal runs; Verify carries its own sections, codes and budgets, so never rely on a fixed text or a fixed number.

`python3 -B demo.py 700 128` builds the sample call for a window of 700 tokens with 128 reserved for the answer and prints the messages and the report. Try 1200, 700 and 350 and watch what the policy cuts first. There is no live call in this mission: fitting is decided before any request leaves.

## The problem

A model reads the prompt and writes the answer inside one context window. OpenAI's guidance is blunt: truncate, omit or shrink the input until it fits, and if a long conversation does not fit, the reply is incomplete or missing. Servers differ in what they do with an over-long prompt: llama.cpp and vLLM refuse it, Ollama silently drops old messages, keeping the system messages and the last message. Neither is a policy you chose, so you build one: a context builder that knows what is mandatory, what is cheap to lose and how much room the answer needs.

Counting is the second half. Tokenizers differ between models, so `build` takes the counter as an argument and Verify injects its own, including deliberately odd ones. The default is the bound from the first mission: a token never covers less than one byte of UTF-8, so `len(text.encode("utf-8"))` can only over-count, and over-counting is safe.

## Complete public contract

```python
class BudgetError(Exception): ...
estimate(text) -> int                       # len(text.encode("utf-8"))
build(sections, *, window, reserve_output, overhead, count=estimate) -> (messages, report)
```

`sections` is a list of dicts in the order the caller assembled them. Every section has a string `id`, a `kind` and a `text`:

| kind | extra keys | role in the output |
| --- | --- | --- |
| `instructions` | — | `system` |
| `pinned` | — | `system` |
| `document` | `priority` (integer, 1 is the most important) | `system` |
| `history` | `role` (`user` or `assistant`), oldest first in the list | the turn's own role |

The **budget** is `window - reserve_output`. The **cost** of one message is `count(content) + overhead`: every message pays the per-message framing of the chat template once, on top of its text. The **total** is the sum of the costs of the messages you return, and it is never above the budget. Costs are recomputed by Verify with the counter it injected, so compute yours with `count` and nothing else.

1. **Mandatory sections.** Every `instructions` section, every `pinned` section and the newest `history` turn (the operator's current question) are always kept, verbatim. If they alone exceed the budget, raise `BudgetError` and return nothing. The same rule serves a model with half the window: the mandatory sections still fit or the call is refused.
2. **Published order.** The messages are: instructions in input order, pinned facts in input order, the included documents in ascending `priority` (ties in input order), then the kept history turns oldest to newest. The newest turn is the last message.
3. **Documents.** After the mandatory sections, documents are filled in ascending priority. A document that fits whole is kept whole. One that does not fit is **shortened**: its text splits into passages at blank lines, you keep a subset of whole passages in their original order (a prefix for truncation, the most relevant ones for retrieval) so that the message fits, and the message ends with the line `[shortened: kept K of N passages]` after a blank line, with K kept of N passages. A shortened document keeps at least one passage; if not even one passage fits with the marker, the document is dropped. A dropped document does not end the fill; the next priority is still tried. Never cut inside a passage and never shorten silently. Normalisation: a blank line is `\n\s*\n`; passages are stripped and re-joined with one blank line, and Verify compares that normalised form. Rewriting passages with a model is out of scope here; the output holds the original passages.
4. **History.** After the documents, history turns are kept newest-first for as long as the next older turn fits; once a turn does not fit, it and every older turn are dropped. The kept history is a contiguous run ending at the newest turn and each kept turn is verbatim. Dropping the newest and keeping the oldest is the defect the starter has.
5. **Deterministic.** The same sections with the same window, reserve, overhead and counter build the same messages and the same report, byte for byte.
6. **The report.** A dict with `window`, `reserve_output`, `budget` (= window − reserve_output), `overhead`, `method` (the counter's `__name__`, `estimate` for the default), `total` (the recomputed sum above, ≤ budget) and `sections`: one entry per input section, in input order, with `id`, `kind`, `status` (`kept`, `shortened` or `dropped`), `tokens` (the cost of the full text) and `kept` (the cost of the message you emitted, `0` when dropped). The kept values add up to `total`. Extra keys are allowed.

Worked example with `count = words` (whitespace-separated words) and `overhead = 2`: instructions of 18 words cost 20, a pinned fact of 9 words costs 11, the newest turn of 6 words costs 8, a three-passage runbook of 43 words costs 45. With `window = 110` and `reserve_output = 24` the budget is 86: the mandatory 39 and the runbook 45 fit with two tokens to spare, and a 13-word turn from earlier in the chat does not, even though it would fit the window. That turn is dropped, the reserve stays free for the answer, and the report says `total: 84`.

## What Verify runs

Every check builds small fixtures with fresh codes, ids and reserves, and derives each budget from its own counters: room for exactly these sections, one token short of the next. The checks: everything kept in the published order when it fits; instructions, pinned facts and the newest turn surviving an over-budget call with the reserve respected and the lowest priorities dropped; history dropped oldest-first as a contiguous run; a document shortened at passage boundaries with the marker and the report saying so; the limit holding under a word counter, a bytes-divided-by-three counter and your default byte bound; half the window still fitting the mandatory sections and an impossible budget raising `BudgetError`; and two builds agreeing byte for byte with equal priorities in input order. Probe facts (a relay code in a pinned fact, a bay name in the priority-1 runbook) must appear in the messages. One hidden bonus check exists; it can only add to the result and never fails the run. There is no live call and no model output in any verdict.

Two different implementations pass: prefix truncation with plain lists, and retrieval of the passages that overlap the operator's question with dataclasses and a deque. No structure of `context.py` is required beyond the three importable names.

## Sources

- OpenAI, "Managing tokens" and the token-counting guide: the context window covers prompt plus generated tokens; an input that does not fit must be truncated, omitted or shrunk.
- Ollama `server/prompt.go` and the OpenAI-compatibility notes: an over-long prompt loses old messages from the front while system messages and the last message stay. llama.cpp `llama-server` and vLLM refuse it instead.
- Python `re.split` and `str.encode`: passages at blank lines, bytes as the token bound.
