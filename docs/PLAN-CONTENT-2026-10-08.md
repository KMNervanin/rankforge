# Content plan — 2026-10-08

Owner request of 2026-10-08: assess the course roadmap with two independent opinions, audit missions for ambiguity, add a hidden bonus objective to every mission, and say how many blocks and missions cover the vast majority of real backend, DevOps and architecture work, with repetition in changed form counted as good practice.

## Lineage

- 2026-10-06, autonomous run: `docs/COURSE-ROADMAP.md` with 86 missions (68 core, 12 foundations, 6 ML), `docs/CURRICULUM.md`, and `docs/MISSION-AUDIT-2026-10-06.md` which reviewed the first six missions and replaced source-string grading with behavioral contracts (commits `8c528df`, `82c07d1`, `7af7df3`, `e1d9a9e`, `1188a50`). Nine catalog missions plus the optional HTTP trial are runnable today.
- 2026-10-07/08, this session: three-star proposal, provider and cost decisions, three environments. The hidden bonus objective is the third star of that proposal.

## Subtasks

| ID | Subtask | Done when | Output |
| --- | --- | --- | --- |
| C1 | Roadmap coverage review, two opinions: this session and the Kimi agent in the `rankforge` team channel. Compare blocks against real backend, SRE/platform and architect work; answer the archetype question; name gaps and redundant entries. | Both reviews written, disagreements listed, a single recommendation on the number of blocks and missions with the repetition policy. | `docs/ROADMAP-REVIEW-2026-10-08.md` |
| C2 | Ambiguity audit of the 10 runtime missions: dangling facts in briefs, lessons, LEARN.md and READMEs that no check requires; hidden requirements; two-reading objectives; unspecified bounds. The owner's example: the first mission's LEARN.md described a 503 with no way to handle it and no requirement to. | Every finding fixed in text or check, one commit per mission; a changed check bumps the contract version; `npm test` and `npm run test:e2e` green. | Text and verifier changes, audit appendix in the review doc |
| C3a | Hidden bonus check per mission in the verifiers: `Check.optional`, never failing the mission; `Mission.nudge` for the card hint; the check report shows the bonus line separately. | For each mission: starter RED on the bonus, a correct edge-case solution GREEN, mission still PASSES when the bonus fails; Node tests cover the three states. | `server/verify*.py`, `server/labs.ts`, `shared/types.ts`, `shared/content.ts`, `src/App.tsx`, tests |
| C3b | Third star record: `mission_stars` table and backfill from the three-star proposal, limited to ★ and ★★★; XP rows per star. | Idempotent across replayed results; existing XP rows map to ★; UI shows star slots. | `server/store.ts`, `server/rewards.ts`, `src/App.tsx`, tests |
| C5 | Reset a mission workspace to its starter, owner request 2026-10-08 03:40. The current files are first copied to a timestamped backup beside the workspace, then the starter is restored and MISSION.md / LEARN.md are regenerated from the current mission texts (this also replaces frozen old wording). Earned stars, XP, chips and frames stay; a repeat pass grants nothing new; a repeat that also passes the hidden bonus earns ★★★ and its XP as usual. | Button in the mission panel with an in-page confirmation; API endpoint; Node tests for backup-then-restore, idempotent rewards on repeat, ★★★ on an improved repeat; E2E for the button. | `server/labs.ts`, `server/app.ts`, `src/App.tsx`, tests |
| C6 | Atlas tab in the site from `shared/roadmap.ts`: the oak layout of `public/atlas-oak.html` as a React view with live statuses from the same mission views as the map, Russian titles, hidden-bonus leaves and the HTTP trial branch. | Tab renders 86 entries; locked/available/completed match the map for every runtime mission (E2E asserts); zoom and pan; card with prerequisites. | `shared/roadmap.ts`, `src/Atlas.tsx`, `src/App.tsx`, tests |
| C4 | Apply the C1 recommendation to `COURSE-ROADMAP.md` and `CURRICULUM.md`: block count, mission count, repetition entries, archetype wording. | Roadmap edited; dependency graph still acyclic; implemented IDs preserved. | `docs/COURSE-ROADMAP.md`, `docs/CURRICULUM.md` |

Order: C1 and C2 ran in parallel; C3a after C2; then C3b, C6 and C5 in sequence overnight on 2026-10-08 so that workers do not edit `src/App.tsx` at the same time; C4 after the owner reads the reconciliation.

## Status, 2026-10-08 02:30

- C2 done: eight commits `64f40cb`..`926d302`, contract version `2026-10-08.1`; Node 154/154, E2E 9/9, real nginx acceptance green. Follow-ups: workspace text is frozen at first open, so corrected texts reach only new workspaces; Recovery does not state that `recover` creates the table on a new file; the Capacity retention wording could say "non-integral".
- C3a done: three commits `22bac9f`, `ff66344`, `5e74b14`, contract version `2026-10-08.2`. Every mission has one optional hidden check, RED on the starter and on a minimal passing solution, GREEN on a thorough one; the card and panel show a one-line rumour; the check report lists the bonus separately and reveals it only when the mission currently passes. Re-run by the coordinator: Node 165/165, E2E 9/9. The Gateway and HTTP-trial bonuses are earned by a careful first solution, which the owner confirmed is the intent: a minimal passing solution still misses them, and a solution that covers both at once shows the player thought it through rather than patching twice.
- C1: Review A written; Kimi's Review B in progress in the `rankforge` channel.
- C3b and C4 not started.

