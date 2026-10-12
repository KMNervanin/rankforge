# Decisions — 2026-10-12

## AI engineering block in the roadmap
**Chosen:** Keep the 86 existing missions and add chapter IX "The voice of the outpost": 44 core missions G01–G44 in seven sub-blocks plus 2 optional limbs; the capstone becomes chapter X and C01 requires G44.
**Reason:** The owner wants a broad applied AI/LLM engineering block rather than splitting the catalog into separate courses; it lives in the same outpost world as an operator assistant so the capstone can use it.
**Reversal cost:** Remove the chapter and the C01 edge; no runtime mission or saved progress refers to G ids.
**Location:** `docs/COURSE-ROADMAP.md`.

## Runtime for the AI block
**Chosen:** Personal route first, configurable OpenAI-compatible endpoint; the public runtime (local CPU model, bring-your-own provider, or both) stays open.
**Reason:** The owner will take the block himself before deciding what other learners get.
**Follow-up:** Mirror G01–G46 and the chapter X rename into `shared/roadmap.ts` and the Atlas tests; verify tooling and coverage against current documentation and primary sources before authoring the first G mission.

## Chapter IX on the Atlas trunk
**Chosen:** `shared/roadmap.ts` mirrors G01–G46 with the roadmap's titles and objectives verbatim; 14 of them form the trunk between W05 and C01 (G01, G03, G07, G08, G09, G10, G20, G23, G25, G27, G31, G35, G41, G44), the other 32 are limbs named after their roadmap sub-block ("Calling the model", "The archive", …) and hang on the right side of the oak next to the model laboratory; the capstone block is renamed to "X · The independent outpost" and C01 gains the G44 edge.
**Reason:** 44 trunk nodes would add 2.9 k px to the trunk; the 08.10 trunk already takes one main line per chapter (A03–A04, W03, W06–W10 are limbs), so chapter IX follows the same editorial rule: one mission per sub-block plus the measurement chain G07–G10 and the gates G31/G41/G44 that C01 depends on. The left side already carries the data and messaging limbs.
**Reversal cost:** Move ids between `roadmapSpine` and `branch`; nothing else refers to the trunk membership.
**Location:** `shared/roadmap.ts`, `src/atlas-layout.ts` (limb side rule), `tests/atlas.test.ts`, `tests/e2e/atlas.spec.ts`.

## Chapter IX checked against primary sources
**Chosen:** Thirty wording changes applied to G01–G46 from a four-pass source check (OpenAI, llama.cpp, vLLM, Ollama, MCP 2026-07-28, OpenTelemetry GenAI, OWASP LLM 2025, pgvector, SQLite FTS5, PostgreSQL 18, evals and agent methodology papers); claims without a primary source stay as the course's own contracts and are listed in `docs/ROADMAP-IX-SOURCES-2026-10-12.md` under "Still open before authoring".
**Reason:** No claim was wrong outright, but several were loose where the sources are specific: MCP transports and authorization scope, deprecated `seed`/`system_fingerprint`, PostgreSQL ranking is not BM25, vLLM on Apple silicon, Ollama's silent truncation, judge order-swap applies to pairwise judgments only.
**Reversal cost:** Prose only; nothing in the runtime or tests refers to the changed cells.
**Location:** `docs/COURSE-ROADMAP.md` chapter IX and the reference section; `docs/ROADMAP-IX-SOURCES-2026-10-12.md`.

## G01 "Every word has a price" is the first shipped chapter IX lab (runtime id `price`)
**Chosen:** A metered client in Python stdlib: `ask()` posts to any OpenAI-compatible `/chat/completions`, refuses by a byte-bound window guard before sending, takes tokens and finish reason from the response, prices from the manifest of the model called, measures latency around the request and appends one JSON line per call. Verify runs a recording adapter (labeled test tool, deterministic counts unlike any character estimate) and one live call to the endpoint in the workspace's `llm.json`, reconciled with Verify's own direct request; no model id or no answer within 15 s is "Environment blocked", not a failure. In-game prerequisite is `signal` (the roadmap's B01/F10 are not shipped); the game chapter is "IX · The voice of the outpost" with its own map label; the hidden bonus is cached prompt tokens priced at the cached rate.
**Reason:** The owner put the AI block first for his own route; G01 is its root and needs only the service basics. Ollama already runs on his machine with a standard `usage` object, so the live check costs nothing and keeps the "real checks, no simulated live evaluation" rule: the adapter never counts as the live run. Keys stay in `LLM_API_KEY`, never in a workspace file.
**Reversal cost:** Remove `labs/price`, `shared/voice.ts`, `server/verify_price.py`, the `price` branches in `server/labs.ts`, the runtime id in `shared/roadmap.ts`, the chapter row and one CSS rule; no saved progress refers to the id yet.
**Follow-ups:** The Atlas limb-nudge guard was raised from 40 to 400 so 32 G limbs fit on the left side; 26 limbs now climb up to 1.9 k px above the capstone (the model-lab chain already did). A layout pass that spreads deep limbs into more columns is separate work. The coach prompt and a `requires` route for chapter IX unlocks were not changed.

## Every quest is open from the start
**Chosen:** `Store.views()` never returns `locked`; `assertAvailable` only checks the id exists; the HTTP trial is enterable without HTTP Applied (the milestone and its unlock reward are still recorded). The briefing shows "Recommended first: … Not required: every quest is open." when prerequisites are incomplete. Chapters with more than six core quests have no pixi map; their cards are grouped by the mission's `block` (the roadmap sub-block).
**Reason:** The owner wants to study any block and any task in any order, without the previous one; the roadmap already calls its order "a convenient reading order, not a chain of unnecessary locks".
**Reversal cost:** Restore the two removed conditions in `server/store.ts` and the `locked` branches in the tests (`tests/store.test.ts`, `tests/progression.test.ts`, `tests/app.test.ts`, `tests/campaign.test.ts`, `tests/e2e/game.spec.ts`, `tests/e2e/atlas.spec.ts`).
**Location:** `server/store.ts`, `src/App.tsx`, `src/ProgressionPanel.tsx`, `shared/types.ts` (`block`, `files`), `server/labs.ts` (verifier by `server/verify_<id>.py`, coach files from `Mission.files`).

## Session stopped at 19:25 by the owner: subagent spend
**What happened:** Batches 1–3 (G02–G16) were authored by ~28 Fable author agents and ~15 blind-reviewer agents in parallel; the owner reported about half of the weekly plan limit consumed in two hours and stopped the run. All running agents were killed at 19:25.
**Chosen:** Keep the committed work (`a2cdf09`, `9afb390`, `17b337d`); leave the uncommitted files in the tree untouched for the next session: `lexical` (G17), `fusion` (G18), `reindex` (G21) are complete and reviewed, `citations` (G20) was stopped mid-fix, `annindex` (G19), `rewrite`, `tools`, `textsql`, `consent`, `workflow`, `agentloop`, `compaction`, `trajectory`, `mcpserver` (G22–G30) are partial. Pipeline rule from now on: missions are authored in the main context, one at a time, no subagents on Fable; any subagent runs on Opus or cheaper with a lower effort, and a batch's cost is named before it starts.
**Reversal cost:** None for the rule; partial lab directories can be deleted or finished.
**Location:** `~/.claude/CLAUDE.md` (rule), this file, `docs/PLAN-VOICE-2026-10-12.md` (statuses).
