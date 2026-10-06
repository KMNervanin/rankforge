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

## Revised navigation after the owner's visual review
**Chosen:** Supersede the first placement decision: navigation stays in the top bar, compact profile/XP on the right, selected mission directly below the map. Detailed progress moves inside the profile.
**Reason:** The owner observed that mid-page navigation confused navigation between pages and interrupted the map-to-mission connection.
**Reversal cost:** UI-only layout change; saves remain unchanged.
**Location:** `src/App.tsx`, `src/style.css`; owner feedback 06.10.

## Skills and rewards rather than completion cards
**Chosen:** Design gradual, evidence-linked branches with rewards and an actual bonus quest; keep chip collection separate from future model-charge spending. Show proposal breadth in a dedicated infographic before representing ideas as shipped mechanics.
**Reason:** The owner explicitly rejected interpreting one completed HTTP exercise as mastery, requested practical progression consequences and asked for implementation plus an infographic.
**Reversal cost:** Version reward rules and preserve already-earned inventory; proposals may be revised without changing learner artifacts.
**Location:** Upcoming progression design and acceptance record; current individual check evidence remains the source of truth.

## Tutor quota versus local practice
**Chosen:** Pause only model submissions/evaluation after a quota or auth failure; deterministic labs and static hints continue, with the pending answer retained.
**Reason:** Optional communication and future chip mechanics must not prevent technical learning when the tutor is unavailable. No alternate billing/provider path is added.
**Reversal cost:** Restore UI/API pause gates; no stored data migration is needed.
**Location:** `server/store.ts`, `server/app.ts`, `src/App.tsx`, `tests/app.test.ts`.

## Historical checks after a contract update
**Chosen:** Stamp fresh results with a contract version. Preserve old completion/XP, display old reports as historical, and require current verification for new skill evidence.
**Reason:** An old PASS may not exercise newly clarified persistence/edge cases; presenting it as proof of the new contract is misleading.
**Reversal cost:** Define an explicit compatibility mapping later; never silently manufacture fresh evidence.
**Location:** `shared/contracts.ts`, `server/labs.ts`, `src/App.tsx`, `server/rewards.ts`.

## First rewards implementation scope
**Chosen:** Four narrow three-checkpoint paths, banked one-time chips, two reversible profile frames and an optional HTTP pagination trial. No charge spending, daily penalties, random rewards or model grading gate.
**Reason:** These have testable practical/visual effects now. The deeper five-tier infographic and its30ideas remain a proposal rather than an implied shipped economy.
**Reversal cost:** Adjust future grants/rules without deleting earned inventory or evidence; frame selection is reversible.
**Location:** `shared/progression.ts`, `server/rewards.ts`, `src/ProgressionPanel.tsx`, `docs/PROGRESSION-DESIGN.md`.
