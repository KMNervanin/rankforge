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
