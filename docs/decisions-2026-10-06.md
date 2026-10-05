# Decisions — 2026-10-06

## Where should the mission workspace live?
**Chosen:** Below the full-width overview, with profile/navigation beneath the map and a wide mission workspace beneath those controls; the existing full-page conversation remains available.
**Reason:** This follows the owner's latest explicit placement request while fixing the narrow verification column discussed previously.
**Reversal cost:** Change the UI layout; learner files and saved state are unaffected.
**Location:** `src/App.tsx`, `src/style.css`.

## Map/card control semantics
**Chosen:** A two-position sliding segmented control with named Map/Cards buttons and persisted view preference; render only the active representation.
**Reason:** Two discrete views need keyboard-readable choices, not a numeric range slider. Shared mission state stays above the switched views, as React's state-preservation guidance requires.
**Reversal cost:** Replace the control without migrating saves.
**Location:** `src/App.tsx`; React official preserving/resetting state and Effect cleanup documentation checked through Context7 (installed React 19.3).

## How are clarified requirements delivered to existing workspaces?
**Chosen:** The website displays current objectives/lesson; learner code and annotated MISSION.md/LEARN.md remain untouched. Existing awards are preserved.
**Reason:** Fixing an ambiguous exercise must not erase the learner's work or notes.
**Reversal cost:** Add an explicit, backed-up document-refresh action later; no data migration needed now.
**Location:** `shared/content.ts`, `src/App.tsx`, `tests/labs.test.ts`.

## Which solutions should the first chapter accept?
**Chosen:** Behavioral contracts, independent alternative fixtures and plausible-wrong counterexamples; no source-string grading. Publish money/input/storage bounds and retain freedom in algorithms, column order and rejected-index order.
**Reason:** The earlier tests both rejected valid solutions and accepted incorrect ones, as recorded in the mission audit.
**Reversal cost:** Revise a versioned contract and checks without revoking old progress.
**Location:** `docs/MISSION-AUDIT-2026-10-06.md`, `server/verify.py`, `tests/labs.test.ts`.

## Course breadth and next implementation slice
**Chosen:** Plan the complete 86-mission catalog, then implement only D01–D03 (requirements, capacity, executable contract) in the next slice.
**Reason:** A broad dependency map prevents gaps; a small verifiable block avoids treating bulk generated exercises as a finished course. Architecture prose remains formative review, not an automatic correctness claim.
**Reversal cost:** Edit the proposed catalog; preserve existing IDs and learner artifacts.
**Location:** `docs/COURSE-ROADMAP.md`, `docs/CURRICULUM.md`.
