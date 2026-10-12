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
