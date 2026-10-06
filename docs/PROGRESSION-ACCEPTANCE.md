# First skills and rewards slice — acceptance and integration

**Integrated release:** all routing, version stamping, registry and UI steps below are implemented. Build+152Node tests+9headlessE2E pass; Linuxarm64Node24.21.0/Python3.11.2 build+152tests pass. The actual browser loop exercised skill rewards, bonus verification, equip and reload. Unequip returns to the default frame while retaining the owned item. The standalone worker's earlier missing-type/Unknown-mission results are historical, not remaining blockers. No charge-spending or live-model gate was added.

Date: 2026-10-06. This slice implements persistence, a skills/rewards infographic panel and one real HTTP bonus lab. Main app navigation, routes, mission registration, lab dispatch and contract stamping belong to the parent integration. The existing preview on 4173 was not restarted or rebuilt by this work.

## Delivered behavior

Four paths contain three modest, cumulative checkpoints each. Every required mission needs a supported, passing check on `currentContractVersion` from `shared/contracts.ts`, with at least one check and no failing check. Here `supported` means a usable technical check, not the absence of hints.

| Path | First checkpoint | Applied checkpoint | Final bounded checkpoint |
| --- | --- | --- | --- |
| HTTP boundaries | Signal | Signal + Gateway | Signal + Gateway + HTTP trial |
| Data integrity | Vault | Vault + Echo | Vault + Echo + Recovery |
| Data processing | Echo | Echo + Ledger | Echo + Ledger + Recovery |
| Design with evidence | Briefing | Briefing + Capacity | Briefing + Capacity + Contract |

None certifies general mastery, production readiness or a language level. Guided practice earns exactly the same completion, XP, unlock and charge as independent practice. Evidence records the mission's hint/coaching count at the passing check. “Independent” means no in-game help recorded; external assistance is not measured. HTTP transfer mode is taken from the trial's own evidence, not from help used on Signal.

### Finite reward schedule

- First qualifying outcome: one starter chip holding **20 game charge**.
- Each path: one chip of **5**, **10**, then **15** game charge at its three checkpoints.
- HTTP Applied: the **Relay frame** and durable access to `http-trial`.
- Data integrity Safe replacement: the **Archive frame**.
- Entire first slice: **13 chips, 140 game charge, two profile frames, one bonus unlock**. Rechecks, changed timestamps, restarts and cosmetic switches do not increase this ceiling.

Charge is a banked game unit for a future bounded tutor harness. It has **no conversion into dollars, tokens or questions**, no spending endpoint and no effect on the current subscription. There are no daily penalties, English requirements or model calls in reward delivery.

## Persistence and existing saves

`Rewards` creates four additive, idempotent tables: `skill_evidence`, `skill_milestones`, `reward_grants`, `reward_equipment`. Evidence is unique by mission/contract/mode; checkpoints by branch/level; rewards by stable grant ID. One equipment slot references an owned cosmetic grant.

`Store.saveCheck` calls `Rewards.recordCheck` **inside its existing BEGIN IMMEDIATE transaction**. Check storage, completion, XP, journal, evidence, checkpoints and grants roll back together on failure. The helper does not open a nested transaction. Node SQLite operations are synchronous; unique constraints protect repeated and concurrent calls. The actual concurrency test uses four processes and independent database connections, not only a Promise queue on one connection.

Old checks with no version or a different version keep their existing completion/XP semantics but create no new skill evidence. Rechecking an already completed mission can add current evidence without changing its completion date or awarding its old XP again. A later failed/unavailable check changes the latest mission report but does not delete earned evidence, levels, unlocks, frames or charge. Historical evidence cannot satisfy a new checkpoint requiring the current contract. Previously earned checkpoints and rewards remain earned across a contract change.

No learner files are read or rewritten by rewards. Pending answers and pause state are not modified by `recordCheck` or equip. Constructor interruption handling and `assertRunning` policy remain the pre-existing Store policy. The parent may change that policy separately.

`Store.views` and `assertAvailable` require both normal prerequisites and durable HTTP level >= 2 for `http-trial`. A directly submitted trial check is also rejected while locked. No Guild completion is required for the bonus, and no core mission depends on it.

## Exact parent integration

1. `shared/types.ts`: import `ProgressionSnapshot` from `./progression.js`, add `Snapshot.progression?: ProgressionSnapshot`, `Mission.bonus?: boolean`, and `CheckResult.contractVersion?: string`.
2. `shared/content.ts`: import `{ httpTrialMission }` from `./http-trial.js` and include it in `missions` exactly once. It has id `http-trial`, chapter `outpost`, order `10`, bonus `true`, prerequisites `signal` + `gateway`, XP `180`. Also register the parent's `architectMissions` for Briefing/Capacity/Contract. Do not renumber or reset saved progress.
3. `server/labs.ts`: route the bonus to `python3 -I -B server/verify_http_trial.py http-trial <workspace>` via the existing `run` helper and 45-second outer timeout. The source entry is `service.py`; retain the regular-file/symlink guard. The verifier emits standard final-line JSON `{checks: [{name,passed,detail}]}`, exits 0 only if all checks pass, and writes no player state. Parent stamps actual runner results with `currentContractVersion`; do not stamp historical persisted reports retroactively.
4. `server/app.ts`: wire `POST /api/profile/equip` with body `{id: string}` to `store.equipCosmetic(id)`, then return/refresh the usual snapshot. Unknown, unowned and non-cosmetic IDs throw `DomainError` with status 409. Equip has no model/auth dependency and does not call `assertRunning`.
5. `src/App.tsx`: named import `{ ProgressionPanel }` from `./ProgressionPanel`; props are exactly `{ progression: ProgressionSnapshot | undefined, missions: MissionView[], busy: boolean, onEquip: (id: string) => void, onMission: (id: string) => void }`. The component imports `progression.css` itself. Use `snapshot.progression`, `snapshot.missions`, existing busy state, the new equip request and existing mission-opening action.
6. Profile rendering: read `snapshot.progression?.inventory.equippedCosmeticId` (`relay-frame`, `archive-frame` or null). The helper does not auto-equip. Owned items live in `inventory.cosmetics`, reserve in `inventory.bankedCharge`, immutable chip receipts in `inventory.chips`, and bonus access in `unlockedMissionIds`. `ProgressionSnapshot` and related branch/evidence/reward types are exported from `shared/progression.ts`.

All source changes in this slice are confined to the 15 files listed below. Parent-owned integration files were not patched.

## HTTP trial acceptance contract

`labs/http-trial/LEARN.md` and `httpTrialMission.objectives` specify the entry point, immutable supplied snapshot, exact `/supplies` route, URL decoding, absent-versus-blank inputs, unique known parameters, numeric bounds, stable id-based continuation and error precedence. The lab is intentionally different from the fixed Signal health response. It permits equivalent implementations and extra response fields without requiring an author's algorithm.

The verifier uses actual `HTTPServer`/`Handler` and HTTP clients with fresh loopback ports, disabled dependence on external proxies, bounded response reads and 1.5-second client timeouts. Request threads are daemon threads; only owned servers are shut down. Reverse DNS is avoided in the verifier to prevent VPN-related local bind delays. The parent runner's 45-second deadline bounds pathological learner code. This is trusted local code execution, not a sandbox or a production HTTP server.

Seven check groups cover three independent snapshots (unsorted, exact-page boundary, empty), page sizes 1/2/4, unseen cursor ids, numeric boundaries, encoded values, ignored unknown parameters, invalid queries, unknown-path precedence, repeatability, interleaved clients and unchanged source state. The starter fails six groups and passes only the empty-snapshot group. Both `sorted.py` and `selection.py` pass all seven: the second uses key/value query pairs and heap selection instead of dictionary query parsing and full sorting. HTTP/1.1 framing, Unicode values, extra fields and JSON/media-type variation are accepted.

Fourteen wrong mutants are rejected: blank-query defaulting, repeated known parameters, non-ASCII digits, ignored upper bound, offset cursor, inclusive cursor, false final continuation, missing-cursor error, prefix routing, false JSON media type, wrong query error, mutated input order, Boolean cursor and cross-client shared cursor.

## Checks performed and failure history

Environment: macOS, Node **25.8.1**, Python **3.14.5**, plus installed Python **3.11**. Python 3.10 syntax was parsed for all four Python sources; an actual 3.10 interpreter was not available. Source/API choices were checked against Python 3.10 docs. The project's Node 24 minimum was checked against its SQLite documentation; this run itself used Node 25.

- First direct verifier run: starter **1 pass / 6 fail**, sorted solution **7/7**, selection solution **7/7**. Repeated on Python 3.11 with the same results.
- Ordinary targeted Node run: **38 tests, 34 pass / 4 fail**. The four failures are `Unknown mission` because the parent registry had not yet added HTTP trial / architect missions. No expected result was weakened and no production registry was edited to hide that gap.
- Isolated integration fixture: the exact exported architect/trial definitions were appended only to the test processes' in-memory registry, with duplicate-id guards. **38/38 pass**, comprising **31 new tests** (11 progression + 20 HTTP trial) and seven existing Store tests. This proves state logic with the intended definitions, not completed production registration.
- Ordinary `npm run typecheck` initially reported exactly three parent-owned field gaps: `CheckResult.contractVersion`, `Snapshot.progression`, `Mission.bonus`. After adding the tests, the final ordinary run has **12 diagnostics** from those same gaps and their downstream inferred types. An in-memory TypeScript compiler host supplied exactly those agreed fields, without casts or changed assertions: **0 diagnostics** across the configured project. The real project typecheck remains a parent integration gate until those fields land.
- Headless Chromium, with actual `ProgressionPanel`/CSS and temporary Store-backed controlled fixtures: empty/partial/full states at **1024, 1280, 1600** px, **nine combinations**, all without horizontal overflow even with evidence details open. Verified equip/mission callback IDs, disabled busy controls and old-server fallback. **0 page errors**. The screenshot was visually inspected; no truncation or overlap was found.
- Atomicity test deliberately aborts a reward insert and verifies the entire snapshot is unchanged, including pending answer, completion, XP and journal. The same Store then succeeds after removing only the test trigger. Four concurrent writers finish with two evidence rows, HTTP level 2, three chips/35 charge, one frame and 320 old-style XP.

Temporary UI evidence: `/var/folders/tj/_9g91tx120qfjzwmw5zxc76w0000gp/T/opencode/rankforge-skills-vertical-slice-1024.png` (controlled fixtures, not the owner's progress). UI bundle generation was in memory. Temporary test databases/workspaces were removed. Pre-existing `dist`, extension build, dependencies and test artifacts belong to the parent and were not cleaned or replaced.

### Reproducible commands after parent wiring

```sh
node --import tsx --test --test-concurrency=1 tests/progression.test.ts tests/http-trial.test.ts tests/store.test.ts
npm run typecheck
```

Parent integration acceptance still needs the real prepare → verify → Store reward → bootstrap UI path, equip route/profile rendering, then the normal build, `npm test` and headless `npm run test:e2e` on the integrated tree. Do not rebuild or restart the owner's existing 4173 preview without coordinating ownership. Current HTTP trial checks are real local HTTP; Store/UI fixtures are explicitly controlled. No live provider, English grading, Docker, authorization, IDE or GUI was used.

## File manifest

One modified file: `server/store.ts`.

Fourteen new files:

```text
server/rewards.ts
server/verify_http_trial.py
shared/progression.ts
shared/http-trial.ts
src/ProgressionPanel.tsx
src/progression.css
labs/http-trial/service.py
labs/http-trial/supplies.json
labs/http-trial/LEARN.md
tests/progression.test.ts
tests/http-trial.test.ts
tests/solutions/http-trial/sorted.py
tests/solutions/http-trial/selection.py
docs/PROGRESSION-ACCEPTANCE.md
```

No commit or push. No new dependencies. No charge spending gateway is implemented; inventory explicitly says so. Profile appearance is a parent rendering responsibility, while equip ownership and persistence are implemented and tested here.
# Parent integration checkpoint — 05:13 MSK

The registry, API routes, chapter UI and versioned checks are now wired in the working tree. The first whole-project run passed 149/149 Node tests; its enclosing 120-second shell deadline expired before E2E could start. A separate `npm run test:e2e` then passed 8/8, including actual guild/trial starter FAIL → saved repair → PASS, reward persistence/equip and the infographic under the real HTTP CSP. This is controlled prerequisite setup plus real new-lab execution, not a live tutor evaluation.

Cold review found three HTTP-trial boundaries after that run: incomplete Content-Length falsely accepted, newline-after-digit mutant accepted, and an unpublished 16 KiB body bound. The verifier now checks framing completeness and encoded trailing whitespace. Both public contract and manual declare bounded inputs and response bytes. Fresh `node --import tsx --test tests/http-trial.test.ts tests/progression.test.ts`: **34/34 PASS**, including inclusive size boundary, chunked/connection-close alternatives, the two wrong candidates, equip/unequip persistence and retained inventory. Final full-suite/E2E refresh remains pending after these changes.

Unequipping restores the default profile frame without deleting ownership. The UI reports newly earned charge/cosmetics after Verify. Skill checkpoints are narrow current-lab milestones; they are not the five deeper hypothetical tiers in the owner's design infographic. Charge remains banked and unspent.
