# Field manual — answer with sources

The archive now returns passages for a question, and the operator wants answers that say where they came from. An answer with a source nobody can find is worse than no answer: the operator walks to locker 7 and finds nothing. The starter asks the model for an answer with a Sources: block and believes every line of it, answers even when nothing was retrieved and never asks the judge. Those are the deliberate defects.

## Workshop and entry point

Python 3.10 or later, standard library only. Edit `answer.py` and keep three names importable: `answer`, `faithfulness` and `reconcile`. `passages.json` holds four archive passages for your own runs, `questions.json` three questions (two answerable, one not) and `versions.json` two versions of the relay runbook that disagree. Verify carries its own passages with fresh ids and numbers, so read everything from the arguments, never from these files.

`python3 -B demo.py` answers every question in `questions.json` against the endpoint in `llm.json`; `--conflict` answers from `versions.json`, `--empty` asks with no passages. An API key, if your endpoint needs one, lives in `LLM_API_KEY`, never in a file of this workspace.

## Two different questions

A cited answer can go wrong in two ways, and they are checked by two different mechanisms.

**Is the citation real?** The passage id must be one that was retrieved, and the quote must be words that stand in that passage. This is a string question and code answers it. No judge, no model: `normalized_quote in normalized_passage` is the whole test. An answer that fails it is rejected before anyone reads it.

**Is the claim supported?** A quote can be real and still not back the sentence it hangs on: "wait 90 seconds" is in the runbook, "the relay accepts lithium batteries" is not, and the model can cite the former under the latter. That is a meaning question. RAGAS calls the ratio *faithfulness*: split the answer into claims, ask a judge per claim whether the retrieved passages support it, and report supported over total. TruLens calls the same search for evidence per claim *groundedness*. The judge here is the calibrated binary judge of the previous mission, injected as a function, so Verify can replace it with a scripted one whose verdicts are known.

Keep the two apart. Citation validity is a hard contract: your code enforces it and an invalid citation never reaches the operator. Faithfulness is a measurement reported next to the answer.

## Complete public contract

A passage is `{"id": "p1", "doc": "runbook-relay", "version": 3, "text": "…"}`; ids are unique within the retrieved set, `version` is an integer. The published abstention phrase is `the archive does not answer this`. Whitespace normalization means `" ".join(text.split())`: runs of whitespace, including line breaks, collapse to one space and the ends are trimmed. Comparisons are case-sensitive.

```python
answer(question, passages, *, base_url, model, max_tokens=400, temperature=0.0, max_retries=1) -> dict
faithfulness(result, passages, judge) -> dict
reconcile(passages) -> list[dict]
```

1. **Nothing retrieved, nothing asked.** With an empty passage list, return an abstention without sending any request.
2. **One request per attempt.** `POST {base_url}/chat/completions` with the question verbatim, every passage's text verbatim and its id written as `[id]`, the abstention phrase and the word `Sources:` somewhere in the messages; `max_tokens` and `temperature` as given; no `stream`. The model's reply grammar is published so that you can parse it: an answer body (sentences, each may end with `[id]` markers), then a line reading `Sources:` (surrounding whitespace and Markdown emphasis such as `**` or `#` are ignored), then one line per citation: `[id]` followed by the quote, optionally in double quotes. Lines in the Sources block that do not start with `[` are ignored. A reply that contains the abstention phrase anywhere (any case) is a refusal.
3. **Validate every citation in code.** `passage_id` must be the id of a retrieved passage and the normalized quote must be a non-empty substring of the normalized passage text. One bad citation rejects the whole answer. An answer with no citation at all is rejected the same way: an answer without evidence is not an answer.
4. **Retry within the bound, then abstain.** After a rejected answer, if fewer than `max_retries` retries were sent, send one more request whose messages contain the rejected citation (its id and its quote), the question and the reason. `max_retries=k` means at most `k + 1` requests; `max_retries=0` means one. When the last answer is still rejected, return an abstention whose `reason` names the offending passage id. A refusal is final: abstain at once, no retry.
5. **The result.** A dict with `status` (`answered` or `abstained`), `text`, `reason` (`None` when answered, otherwise why), `citations`, `claims`, `conflicts` and `attempts` (the number of requests actually sent, `0` for an empty passage set). When answered: `citations` is the list of validated `{"passage_id", "quote"}` in reply order, `quote` in normalized form; `claims` is the answer body split into sentences by the published rule below; `text` is the answer in any citation style you choose, inline `[p3]` markers or numbered footnotes with a list underneath, as long as every claim appears in it once bracketed tokens are removed. When abstained: `text` starts with the abstention phrase, `citations` and `claims` are empty lists.
6. **Claims.** Remove every bracketed token together with the whitespace before it (`\s*\[[^\]]*\]`), normalize whitespace, split after `.`, `!` or `?` followed by whitespace, trim, drop empties. Worked example: `Wait 90 seconds [p1]. Fuses are in locker 7 [p2].` gives `["Wait 90 seconds.", "Fuses are in locker 7."]`.
7. **Faithfulness.** `judge(claim, passages) -> bool` is called once per claim, in order, with the claim string and the retrieved passages. Return `supported` (count of true verdicts), `total` (count of claims), `score` = `supported / total` within 1e-9 (`None` when there is no claim) and `verdicts`, one `{"claim", "supported"}` per claim in order. An abstention has no claims and never reaches the judge. Worked example: three claims, the judge rejects the third: `supported 2, total 3, score 0.6667`.
8. **Versions that disagree.** `reconcile(passages)` groups the retrieved passages by `doc` and returns one `{"doc", "ids", "versions"}` per document present in more than one version, ids ordered by ascending version, documents ordered by name; `[]` when there is no such document. The result of `answer` carries it as `conflicts`. The rule: an answer that cites one version of such a document must cite every retrieved version of it, otherwise it is rejected like a bad citation, retried with both ids named, and finally abstained with both ids in the reason. The archive never decides which version is current; that is the operator's call and the next mission's problem.

Transport errors (connection refused, HTTP 4xx/5xx) may raise any exception.

## What Verify runs

- A **scripted adapter**: a loopback server that speaks the contract above and plays the model with chosen replies: a correct cited answer whose quote crosses a line break in the passage, an answer citing an id that was never retrieved, an answer whose quote is a paraphrase, an answer with a fabricated third claim, a refusal, an answer with no Sources block, and for the transfer an answer citing one version then both. It records every request body. It is a labeled test tool, not a model.
- A **scripted judge** that decides each claim from a hidden rule, so the expected faithfulness is known before your code runs. Citation validity is checked by Verify's own string comparison, never by the judge.
- A **live measurement**: two questions on the four passages of `passages.json` through your `answer` on the endpoint in `llm.json`, one answerable and one the archive cannot answer. Verify re-validates every citation of an answered result with its own code (that is your contract) and reports whether each question was answered or abstained, with citation and claim counts, as a measurement of one run, never a verdict on the model. No model id in `llm.json`, or no answer within 15 seconds, is **Environment blocked**: nothing fails, nothing passes. The whole live section has a 20-second budget; warm the model up with the demo first.

On a local 4B model the answerable question usually comes back with one or two citations, sometimes with a quote that drops a word; your validator rejects it, the retry fixes it or the answer abstains. The unanswerable question is where small models invent a diesel price: a prompt that offers the abstention phrase as an explicit way out makes the difference between a hallucinated answer and a clean refusal.

Two different implementations pass: `urllib.request` with inline markers kept as the model wrote them and a retry that continues the conversation, and `http.client` with dataclasses, footnote rendering and a retry that sends one fresh message. No specific structure of `answer.py` is required beyond the three importable names.

## Sources

- RAGAS, faithfulness: the answer is broken into claims, each claim is checked against the retrieved context and the score is supported claims over total claims.
- TruLens, the RAG triad: groundedness searches the retrieved context for evidence per claim; context relevance and answer relevance are the other two legs.
- Python `re`: `re.split` with a lookbehind for sentence ends; Python `str.find` for the span test.
