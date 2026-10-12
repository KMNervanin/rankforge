# Authoring guide for chapter IX labs (G02–G46)

This is the working contract for every mission of "The voice of the outpost". The reference implementation is G01 (`labs/price`, `server/verify_price.py`, `shared/voice.ts`, `tests/price.test.ts`, `tests/solutions/price/`). Read those four places before writing anything. The roadmap row for the mission (`docs/COURSE-ROADMAP.md`, chapter IX) is the specification: its Objective, Artifact, Verification and Alt/Fail/Transfer columns must all be covered by the lab. `docs/ROADMAP-IX-SOURCES-2026-10-12.md` lists what the sources confirmed and what is still open; respect it.

## World and runtime

- The outpost's operator assistant triages free-text supply requests, answers from runbooks and incident reports with sources, queries stock and reserves stock only with the operator's own permissions. Every lab changes one behavior of that assistant or tests one claim about it. Reuse the outpost vocabulary: relay, supplies, runbooks, incident reports, operator, reservations, outposts (tenants).
- Python 3.10+ standard library only, SQLite when a database is needed, JSON files for fixtures. No pip, no Docker, no network beyond loopback and the endpoint the learner configured in `llm.json`. No GPU, no paid service, no API key in any file: a key lives in `LLM_API_KEY` in the environment.
- The model is reached through an OpenAI-compatible `POST {base_url}/chat/completions` (and `/embeddings` where a lab needs vectors). Deterministic checks go through a **scripted adapter**: a loopback server inside the verifier that speaks the same contract and returns chosen outputs, faults and counts. It is a labeled test tool and is never presented as a model. The learner's `llm.json` (`base_url`, `model`, optional `embedding_model`, `context_window`, prices) feeds the **live** part, if the mission has one.
- Verify runs `python3 -I -B server/verify_<id>.py <id> <workspace>` with a 45 s total budget, a 256 KiB stdout limit and a whitelisted environment (no `LLM_API_KEY`: live calls to key-protected endpoints are environment-blocked, local servers need none). Print one final line `{"checks": [...]}` and exit 0 only when every non-optional check passed. A check named exactly `Environment blocked` marks the run unsupported: no failure, no pass. Use it for a missing `llm.json` model, an endpoint that does not answer within 15 s, or any resource the learner has not configured; never for learner mistakes.
- Live calls are optional per mission. When the roadmap row says quality numbers come from actual runs, the live check must exist, must name the model id and base URL in its detail, and must report numbers as measurements, never as pass/fail on model talent. Keep live work under 20 s total; warm-up advice belongs in LEARN.md.

## Files a mission consists of (and nothing else)

| Path | Content |
| --- | --- |
| `labs/<id>/LEARN.md` | Field manual: story in two sentences, workshop and entry point, the **complete public contract** (function signatures, file formats, bounds, tolerances, error behavior), what Verify runs, sources. Written for an experienced iOS developer who is new to this topic: explain the concept once, precisely, with one worked example. No Russian. |
| `labs/<id>/<main>.py` | The starter with the deliberate defect(s): it runs, it is plausible, and it fails the contract in the ways the roadmap's Fail column names. Keep the importable names Verify needs. |
| `labs/<id>/*.json`, `*.jsonl`, `*.md`, `*.sql` | Fixtures for the learner's own runs: small, synthetic, licensed-free. Verify never trusts workspace fixtures; it carries its own values. |
| `labs/<id>/demo.py` | A terminal entry point: `python3 -B demo.py …` exercises the starter against `llm.json` or a local fixture. |
| `labs/<id>/llm.json` | Only when the lab has a live part: `{"base_url": "http://127.0.0.1:11434/v1", "model": "", …}` with an empty model id, exactly like `labs/price/llm.json`. |
| `labs/<id>/llm.py` | Optional helper when the lab needs a working metered client: copy `tests/solutions/price/urllib.py` and trim. Labs are self-contained; never import another lab. |
| `server/verify_<id>.py` | The verifier. Pattern: `check(name, operation, optional=False)`; a scripted adapter class; fresh values; one `optional=True` hidden bonus whose name starts with `bonus:`; `Environment blocked` only for resources. Exit code ignores optional checks. Load the learner module with `importlib` from the workspace; never execute workspace code at import time beyond the module itself. |
| `shared/voice/<id>.ts` | `export const mission: Mission = {…}` and `export const followUps: string[]` (two debrief follow-up questions). `chapter: 'voice'`, `order` = the G number, `block` = the roadmap sub-block heading, `files` = the files the coach should read first, `prerequisites` = runtime ids of shipped quests only (chapter IX ids or `signal`/`vault`/…; roadmap ids that are not shipped are omitted), `skills` three short nouns, `xp` 200–280, `kind` `build`/`repair`/`assessment`, `nudge` one rumour line for the bonus, `briefs` for guided/connected/independent, `objectives` = the contract (what Verify enforces, numbered sentences), `languageGoal`, `prompt`, three `hints` from investigation to concept to concrete, `sources` (URLs from the source-check document), `commands`, `lesson` (what the starter gets wrong, what Verify does, what is out of scope), `artifact`. Titles and objectives are the roadmap's English. |
| `tests/solutions/<id>/<a>.py`, `<b>.py` | Two materially different passing implementations (different library, data structure or algorithm), both earning the bonus. |
| `tests/<id>.test.ts` | Copy the shape of `tests/price.test.ts`: starter RED on each named requirement; both solutions GREEN with the exact check count; at least six mutations of one solution, each RED on the named check; a minimal variant that passes the contract but misses the bonus; `Environment blocked` paths if the lab has a live part (use `tests/llm-stub.ts`; extend the stub only by adding handlers, never by changing existing behavior); import failure reported as a failed check. Run only `node --import tsx --test tests/<id>.test.ts`. |

Do not edit `shared/voice.ts`, `shared/roadmap.ts`, `shared/content.ts`, `server/labs.ts`, `src/*`, `package.json` or another mission's files: the integrator wires the index, the Atlas runtime id and the sector colour.

## Quality gates (the roadmap's release gates, applied)

1. One primary outcome, bounded inputs, explicit exclusions. The experienced path is a specific challenge, not a lecture.
2. Every blocking check maps to a sentence in LEARN.md and in `objectives`. Publish grammar, units, error behavior, tolerances, ordering and persistence where relevant.
3. The oracle is independent: hand-computed tiny cases, `Fraction`/`Decimal` recomputation, state inspection. Never derive expected values by running the reference solution.
4. The intended starter fails; two different valid approaches pass; degenerate approaches fail: always-pass, canned fixture, silent data loss, swallowed exceptions, output copied from the prompt, state kept only in memory when persistence is required.
5. Fresh values on every run (ids, counts, prices, seeds) so hardcoding is caught. Distinguish infrastructure unavailable from wrong learner behavior.
6. Hints go from investigation to concept to concrete help without imposing one algorithm.
7. Real execution: loopback HTTP, real SQLite files, real subprocesses where the contract says so. Record what you ran in the final report.
8. No model output ever completes a technical check. A judge or model answer may be an input the learner's code processes; the verdict comes from code.

## Report back (max 400 words)

The runtime id, the files created, the check names, the live part (yes/no and what it measures), the solutions' difference in one line, the mutation list, and the exact output of `node --import tsx --test tests/<id>.test.ts` (pass/fail counts). Name anything in the roadmap row you could not cover and why.
