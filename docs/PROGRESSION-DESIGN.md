# Progression design — small proofs, visible consequences

Design candidate, 2026-10-06. Companion: [interactive infographic](../public/progression.html), [course roadmap](COURSE-ROADMAP.md). The infographic is Russian for the owner; the actual game and future player-facing labels remain English. This document proposes behavior, not shipped progression, a new course order, live tutor evaluation or mastery certification.

## Why this shape

The owner wants substantial gradual growth, optional paths and a base that visibly changes with practical work. One HTTP mission must not imply HTTP mastery. A useful reward answers two questions: **what becomes possible, and what does the player click to use it?** The infographic contains 30 distinct ideas in six families; details expose triggers and boundaries rather than putting a report on the main canvas.

Four records stay separate:

- **Rank:** a campaign milestone and fictional role. Neither a professional grade nor an assessment of every skill.
- **Skill tier:** an authored, narrow capability checkpoint supported by varied relevant tasks. No generic XP threshold can substitute for its required evidence.
- **Evidence:** actual saved artifact, contract/checker/fixture versions, observable behavior, environment and support used. Technical completion and independent transfer are different claims.
- **Reward:** an inventory item, extra authored route, visible world change, optional practice facility or cosmetic. It cannot change the checker or conceal missing evidence.

A supported correct solution earns its core outcome and normal rewards. It does not silently become independent evidence. A later new attempt without assistance can establish independence; help on an earlier task is not a permanent penalty. Communication/post-brief remains optional and separately observed. Model praise, a schema-valid design and a repeated fixture cannot certify mastery.

## An illustrative eight-quest chapter

The roadmap baseline lists six existing labs, not an eight-mission shipped route. The infographic deliberately labels the two new core examples and one optional example. The order below is a demonstration of a midchapter unlock, **not a request to reorder runtime missions or amend prerequisites**. Gateway can follow Signal alongside the database branch in the roadmap; relevant entry capabilities such as F12 are assumed in this illustration, not waived.

| Step | Example | Evidence and visible consequence |
| --- | --- | --- |
| 1 | Signal, existing I01 | Service health/path/header/body contract; relay lights. HTTP I is first contact, not mastery. |
| 2 | Vault, existing I02 | Direct SQLite writes enforce constraints; vault cells light. |
| 3 | Echo, existing I04 | Durable identity and conflict/replay behavior; event history appears. Integrity II combines distinct constraint and identity contexts. |
| 4 | Ledger, existing I05 | Exact totals and visible rejections; reconciliation view becomes meaningful. |
| 5 | Gateway, existing I03 | Actual nginx forwarding and service-boundary observations. Signal + Gateway give HTTP II and an optional route **before step 6**. |
| Bonus | **Foreign route**, unimplemented proposal | New local service/path/query scenario behind a proxy. Fresh artifact/fixture and trace; core progression does not depend on it. |
| 6 | Recovery, existing I06 | Atomic restore and late-failure preservation; archive lights. |
| 7 | **Field trace**, unimplemented illustration | Supported trace of a different request across owned components. Adds diagnostic practice, not an automatic independent-transfer mark. |
| 8 | **Outpost drill**, unimplemented illustration | Bounded integration of request, durable effect, report and safe restore. An illustrative D rank checkpoint; all public core outcomes and composed checks must hold. |

Steps 7–8 are not catalog IDs D03/O04/C03 and do not inherit claims that those missions exist. Authoring must resolve their entry scope before either is added to a real campaign. The first implementation candidate below can use the existing Signal → Gateway relationship without shipping this eight-step campaign.

The page starts after step 5 to make the branch immediately discoverable. Step buttons and previous/next show a timeline snapshot; moving backwards is not revocation of earned rewards. A separate **Start example again** resets only in-memory demo state. Reload also resets this illustration. There is no game storage access.

The bonus pane lets the owner show a hypothetical supported or independent success. Both count as a technical result in the example; only independent adds one transfer observation. **One of two distinct required contexts is still not HTTP III.** A button in the infographic is not a lab execution or evidence of a real learner outcome. Cosmetic equip/unequip and milestone inventory are likewise demonstrative.

## Deep progression, beyond this chapter

The five-node tracks are examples of authored gates, not a validated universal taxonomy. Nodes show evidence requirements rather than a smooth percentage of knowledge.

| Track | I | II | III | IV | V |
| --- | --- | --- | --- | --- | --- |
| HTTP & routing | One service contract | Service + proxy contexts | Two differing unfamiliar cases solved independently | Several failure boundaries: deadlines, TLS, retry | Change a connected system while preserving contracts |
| Data integrity | Schema-level invariant | Constraints + durable identity | New concurrent schedules with committed-state checks | Migration and compatibility across data versions | Connect transactional effects, lineage and reconciliation |
| Recovery | Atomic archive replacement | Narrow restore + composed scenario | Different unfamiliar failure points | Real backup/restore, bounded RPO/RTO | Release, restore and data correctness together |

Higher tiers need multiple tasks that actually exercise the relevant dimensions, including meaningful changed situations and revisits after intervening work. Merely varying an identifier can test hardcoding but does not by itself prove a genuinely different transfer context. A replay is useful practice, not another evidence diversity slot. Scope the tier title and required evidence to observable claims; do not promise “master of HTTP” or professional seniority after tier V.

Readiness gaps should offer targeted practice, not deduct old achievements. A long absence offers a refresher. No streak resets, expiring chips, permanent hint penalties or grind through identical fixtures. If generic skill XP exists for game feel, label it as a game counter; it cannot unlock a capability gate without the specified evidence. Basic instructions, hints, error reports, safe checkpoints and deterministic checks never depend on high skill or chips.

## Reward catalog: 30 ideas, six families

Each ID corresponds to a card in the infographic, with a concrete UI action, acquisition condition and limit. This is an option set, not a commitment to build all thirty.

| Family | IDs and distinct effects |
| --- | --- |
| Charge reserve | **C1 milestone chip:** inspect inventory/source; **C2 optional field-report capsule:** save a voluntary report and inspect its separate award; **C3 exploration reserve:** earmark charge for a new hard optional case; **C4 shared storage:** move a reserve between learning topics; **C5 cache choice:** choose charge or a cosmetic instead of random loot. |
| New routes | **R1 Foreign route:** start a transfer quest at HTTP II; **R2 cross-skill trial:** HTTP + data identity ticket; **R3 alternate method:** preserve the first artifact and compare a second approach; **R4 constrained expedition:** new published operating constraints; **R5 return ticket:** revisit a known node with a different symptom after other work. |
| Outpost | **O1 live connection:** illuminated route opens its evidence; **O2 cartographer desk:** compare versioned diagrams/ADRs; **O3 restore archive:** replay a snapshot into a new copy; **O4 observatory:** request-ID overlay across real hops; **O5 additional plot:** create a bounded project in a separate owned workspace. |
| Identity and collection | **I1 First channel frame:** equip/unequip; **I2 incident trophy:** place an object linked to an actual trace; **I3 callsign:** choose a fictional earned title; **I4 building blueprint:** switch architectural appearance; **I5 outpost chronicle:** collect before/after artifact stories with support labels. |
| Practice facilities | **P1 comparison bench:** run two artifacts against a shared contract; **P2 fault room:** bounded local failure injection; **P3 trace replay:** inspect captured hops with a playhead; **P4 practice mixer:** combine authored cases from opened topics; **P5 operator rehearsal:** reproduce a runbook in a fresh owned environment. |
| Agency | **A1 next-contract choice:** pick between prerequisite-ready tickets; **A2 specialization focus:** reversible recommendations; **A3 personal project:** bounded change to a verified baseline; **A4 non-reset prestige:** new campaign conditions while retaining history; **A5 asynchronous handover:** optionally export a scrubbed reproducible incident package for a friend. |

**Promising after the first slice:** R2/R5 make skills intersect and recur; O4/P3 give a concrete view of cause and effect; A1/A2 add agency without a class lock. C2 is participation encouragement, never a grammar/length gate or model approval gate. It needs a tested, anti-repeat eligibility rule before release. If that cannot be reliable and understandable, use a non-scarce chronicle entry rather than farmable charge.

**Consciously deferred:** C5 needs an actual charge policy and a pilot before offering scarcity-driven choices. A4 needs genuinely new content, not a restart grind. A5/social guilds need a useful solo product first; an automated rehearsal is not a human teammate. Also defer trading, reward sales and a base-resource economy. Do not implement loot boxes, leaderboard pressure, hint penalties, daily losses or a purchasable PASS. Giving extra charge for repeated failures would reward intentional failure; tie exploration grants to a unique authored episode instead.

## First implementation candidate — four reward effects

Implement only **C1 + R1 + O1 + I1** around a single milestone: verified Signal and Gateway satisfy HTTP II. This includes a charge inventory entry, an optional authored transfer route, a lit map connection with evidence access, and a collectible profile frame. The reward does not need an arbitrary XP economy or the full eight-step chapter. The initial inventory quantity of one chip is an illustrative item count, not a priced resource allowance.

### Observable player path

1. Verify Signal; show its bounded technical outcome, support label and HTTP I.
2. Verify Gateway on real owned nginx/HTTP resources. With both valid evidence records, show HTTP II, light the link, expose **Foreign route** and grant exactly one chip and frame.
3. Open the route or continue the core path. Starting the bonus creates an isolated owned workspace with an explicit artifact-copy/checkpoint step; never reset Signal or Gateway.
4. In the bonus, run real public-contract checks over fresh requests and state. Failure preserves work. Success with help records completion; an independent new context adds a distinct transfer record. Neither skips future tier gates.
5. Open inventory and inspect the chip's source. Open collection, equip the frame, reload and observe it still equipped. Unequip without destroying the item or changing skill evidence.

### State and award contract for the parent implementation

Use version-bound evidence and explicit authored milestone predicates, rather than inferring competence from mission completion IDs or a generic XP total. Preserve source artifact hashes/versions and support metadata at the attempt boundary. Do not relabel historic supported or unknown-support attempts as independent. Existing completions require evidence compatibility review; do not silently reset them or fabricate new tests.

Awards need an atomic, idempotent ledger operation keyed by player + stable milestone identity + reward identity. Re-Verify, retry after a lost response, concurrent tabs, reload and later attempts must converge on the same earned item, not add another. A content/checker version bump is not automatically a new reward identity; define explicit compatibility/migration behavior. Store cosmetic ownership separately from equipped selection. Nonmatching future evidence leaves a new gate pending without revoking historic progress. The static infographic derives its one-item display from a snapshot and **does not implement this persistence contract**.

### Charge clarification

A tutor chip is **reserve charge**. The future harness will bound model context, output and cost; do not assume long answers, assign token prices, promise a fixed number of questions or implement spending now. In the first candidate, earn and inspect the item only. Before any later activation, design spend/refund/retry and quota behavior against the actual harness contract. Basic learning support remains available without the item. Quota/auth failures retain pending messages and do not trigger pay-as-you-go fallback. No new provider adapter belongs in this slice.

## Owner proposal, 2026-10-07 — three stars per mission

The owner wants every mission to have several levels of completion instead of one pass/fail outcome. Today a first passing Verify grants the whole XP value at once, records skill evidence and advances a skill checkpoint; the debrief adds nothing beyond the language band, and nothing rewards looking for an edge case. The result is that a learner who barely passes and a learner who tried hard look identical to the game. The proposal below is written against the current code and the fairness rules above; it is a design candidate, not shipped behavior.

### The three stars

| Star | Name | Earned when | What the player sees before earning it |
| --- | --- | --- | --- |
| ★ | Restored | The current-contract Verify passes, with or without hints. Same as today's completion. | The objectives list, as now. |
| ★★ | Reported | A debrief for this mission is graded by the tutor with the communicative goal **met or partial**. `not_met` is not a loss: the tutor's reply says what is missing and the player can send another debrief at any time. | "Write a debrief to the guild" with the mission's debrief question. |
| ★★★ | Thorough | A passing Verify run also passes the mission's **optional hidden checks**: one or two deterministic edge cases that the public objectives do not spell out. | A short authored nudge on the card, such as "Rumour says the ledger misbehaves right at a boundary" or "What if the same event arrives twice?" The exact check is revealed after the star is earned, or on request after ★ is earned. |

Stars are independent and can be earned in any order, except that ★★★ requires a run that also passes. A mission's stars never decrease: a later failing Verify, a contract version bump or a weaker debrief leaves earned stars in place. ★★ is about communication, not technical mastery, and stays separately observed as the fairness rules require; it never gates ★ or ★★★.

### Why hidden checks are allowed here but not in the core contract

The mission audit chose published behavioral bounds and rejected surprise failures. Hidden checks respect that: they can **only add** a star and can never fail a mission or block a reward that ★ already grants. Each hidden check must be a reasonable consequence of the brief, written next to the public checks in the same verifier and marked `optional`, so the player can audit it afterwards. The card nudge exists so that the star is discoverable without reading the verifier.

### Effect on XP, skills and rewards

- **XP.** ★ keeps the current mission XP. ★★ and ★★★ each add half of that XP once. XP stays a game counter and still unlocks nothing by itself.
- **Skill checkpoints.** A checkpoint that is not yet earned additionally requires ★★★ on at least one of its missions. Clearing every mission with the bare minimum reaches ★ everywhere, but the skill ladder waits until the learner has handled at least one edge case in that branch. Already earned checkpoints and chips are preserved by the idempotent ledger and are not re-evaluated.
- **Chips.** Chip charge from a checkpoint scales with the total stars across its missions instead of a flat `level × 5`; exact numbers wait for the charge-spending design, which is still deferred.
- **Cosmetics.** Three stars on every mission of a checkpoint unlocks a gilded variant of that checkpoint's frame. Purely visual.
- **Nothing new is subtracted.** Hints, coach use, failed runs and `not_met` debriefs still cost nothing, in line with "no hint penalties".

### Data and migration

- New table `mission_stars(mission_id, star, earned_at, source_ref)` with a primary key on `(mission_id, star)`, written inside the same transaction as `saveCheck` or the debrief `finish`, so retries, reloads and concurrent tabs converge on one row. `source_ref` points at the check result or exchange id.
- `Check` gains `optional?: boolean`; `passed` continues to mean "all required checks passed". The verifiers return hidden checks alongside the public ones.
- `Mission` gains `nudge?: string` for the card hint. Missions without hidden checks have no ★★★ and show two star slots.
- One-time backfill on startup: ★ for every mission with `progress.completed`; ★★ for every mission that already has a completed debrief exchange with a `met`/`partial` grade; no retroactive ★★★, because old runs did not execute hidden checks and the current rule says historical results are not fresh evidence.

### Open question for the owner

The one judgement call is the bar for ★★. The table uses "goal met or partial" so that a one-word debrief does not count; the alternative is "any graded debrief", which removes the model from the decision entirely but makes the star trivial. The recommendation is met/partial, because the star is granted once per mission and cannot be farmed, so the catalog's concern about farmable model-approved charge does not apply.

### Checks before calling it done

Node tests: a hidden check failing never fails the mission; ★★★ requires a passing run; stars are idempotent across replayed results and duplicate debriefs; backfill matches existing completions and graded debriefs; a checkpoint without ★★★ stays pending while an already earned one is untouched. Headless browser: the card shows star slots and the nudge, the detail panel explains how each star is earned, and reload keeps the stars. Run `npm run build`, `npm test`, `npm run test:e2e` after integration.

## Roadmap and release checks

1. **This deliverable:** standalone Russian explanation, step/skill/family interactions, diagram, bonus-support distinction, demo inventory/cosmetic. Confirm local/file operation, keyboard paths, reduced motion, readable 1024–1600 layouts and zero network requests. This is a design preview, not implementation acceptance.
2. **Parent UI/state slice:** evidence presentation, milestone predicate/ledger, chip inventory and equip persistence. Make source versions and support visible; preserve saves. Use meaningful Node tests for concurrent/replayed grants, old evidence compatibility and equip/reload. Verify the actual browser flow headlessly. Run repository build/test/E2E in the parent's integration workstream.
3. **Optional mission authoring:** freeze Foreign route's brief, starter, checker, failure model and resource ownership together. Demonstrate starter RED, distinct valid approaches GREEN, negative cases RED, fresh inputs, state preservation and help-independent technical scoring before exposing a runnable route.
4. **Three-star completion (owner proposal, 2026-10-07):** optional checks in the verifiers, star ledger, backfill, card nudges and the star-aware checkpoint rule from the section above. Decide the ★★ bar first; preserve every earned checkpoint and chip.
5. **Small real-use pilot:** does a player notice the midchapter branch, understand HTTP II's limits, and use the reward? Observe confusion and effort rather than inventing timings or learning-effectiveness metrics. Then consider R2/R5 and one facility. Harness economics and social features stay separate.

## Standalone behavior and verification

`public/progression.html` uses only inline CSS, authored inline SVG and a classic inline script; no fonts, images, libraries, requests, auth, game APIs or storage. Its CSP disallows connections. It opens directly through `file://` and is a Vite public asset at `/progression.html` on the next normal dev/build serving cycle. An already-built preview will not automatically acquire a new public file; do not restart the owner's preview to make this page appear.

Native buttons expose pressed/expanded state, the bonus and filter provide live announcements, selectors have labels, SVGs have text alternatives, focus is visible, and reduced-motion disables scrolling/transitions. Changing snapshots preserves the simulated bonus/equip choices when returning forward; resetting the example clears only those in-memory choices. Four candidate cards are explicitly marked among the 30 proposals.

Verification is scoped to this standalone deliverable; running the changing parent app's build/full suites would not prove these interactions and could touch shared artifacts. Use installed Playwright 1.63 headless Chromium with a fresh context and blocked HTTP(S), navigate to the file, exercise all eight steps plus reset, unlock/close/support modes, all three skills, six filters/all 30, details and cosmetic equip. Check overflow at 1024/1280/1600, keyboard focus and reduced-motion styles; save and inspect screenshots outside the repo. No permanent test script is required. The parent owns full `npm run build`, `npm test`, `npm run test:e2e` after integration. Playwright 1.63 library/screenshot behavior was checked against Context7 before using it.

### Executed acceptance, 2026-10-06

Actual Node test runner + headless Chromium: **10 tests passed, 0 failed, 0 skipped** (one parent test and nine scenario subtests), after the final HTML change. Covered every step/filter, all 30 unique cards/four first-slice effects, supported and independent bonus paths, tier boundaries, repeat visits, reset/reload, keyboard-only controls, cosmetic equip, valid accessibility references, reduced-motion and 1024/1280/1600 overflow checks. Observed **0 HTTP(S) attempts and 0 JavaScript/console errors**. This proves the static illustration's behavior, not persistent game awards or real mission assessment.

Screenshots were saved under `/var/folders/tj/_9g91tx120qfjzwmw5zxc76w0000gp/T/opencode/`: `rankforge-progression-overview.png`, `rankforge-progression-first-screen.png`, and `rankforge-progression-{chapter,skills,rewards}-{1024,1280,1600}.png`. The overall layout, 1024 chapter/skill details and 1600 reward cards were visually inspected. A screenshot-exposed offscreen skip-link rendering issue was fixed with clipped-until-focused styling; the final first-screen and 1024 chapter captures were inspected again. Owned browsers were closed. No dependencies, test scripts or build artifacts were created in the repository; the existing preview server was untouched. Full application build/test/E2E were not run by this standalone workstream.

### Plain-language revision, 2026-10-06 evening

The owner reported that the first version could not be read by a person: design-review vocabulary (evidence, transfer, checkpoint, harness, fixture), English terms inside Russian sentences and a caveat in almost every line. The fictional example is intentional and stays. The page now explains the same model in plain Russian: a quest → check → result loop, the eight-step chapter with the timeline above the map, a character strip (rank, three skills, rewards) for the selected step, five-level skill ladders, all 30 ideas with "в игре / как получить / важно знать", the four first-slice rewards and the fairness rules. The map has six buildings, so every step visibly changes the outpost; step 7 lights every route and step 8 raises the D flag.

Verified headless in Chromium through `file://` and the actual service CSP: every step, previous/next, reset, both bonus modes, three skills, six families and all 30 cards, equip; zero network requests and console errors; no horizontal overflow from 900 to 1600 px; smallest visible text 13 px. `npm run build`, `npm test` (152/152) and `npm run test:e2e` (9/9) passed. The service hashes this page's inline script once at startup, so a changed page needs a deliberate preview restart; learner state (120 XP, 25 exchanges) was identical before and after the restart.
