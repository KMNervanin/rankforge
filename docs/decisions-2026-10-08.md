# Decisions — 2026-10-08

## Provider for the commercial build
**Chosen:** Google Cloud with Vertex AI, postpaid; Rankforge's own gateway meters cost per customer; Stripe bills customers. No second adapter, no free tiers in the product, no customer-supplied keys.
**Reason:** The only postpaid provider whose key creation, quotas, budgets and cost export are all APIs; OpenRouter is prepaid with a fee and an intermediary.
**Reversal cost:** Swap the adapter behind the gateway; the ledger and Stripe stay.
**Location:** `docs/PROVIDER-FREE-TIERS-2026-10-07.md`.

## Three stars per mission, skills from XP
**Chosen:** ★ Verify passes; ★★ debrief graded met or partial against the recorded checks; ★★★ hidden optional checks pass in a passing run. Stars scale XP (★ base, ★★ and ★★★ each add half); XP is credited to each skill the mission lists; skill levels are XP thresholds. Existing chips, frames and checkpoints are preserved.
**Reason:** The owner wants full skill growth only for effort, and skills to grow from XP rather than from authored evidence gates.
**Reversal cost:** Keep the star ledger, change the XP shares or the skill thresholds; no data loss.
**Location:** `docs/PROGRESSION-DESIGN.md`, `shared/progression.ts`, `server/store.ts`.

## Atlas as a site tab
**Chosen:** The oak-tree atlas (`public/atlas-oak.html`) becomes a top-level tab in the game, rendered from a shared roadmap catalog with live statuses; the outpost map stays unchanged.
**Reason:** The owner chose the vertical tree with a thick colour-segmented trunk and side limbs after rejecting four conceptual sketches.
**Reversal cost:** Remove the tab; the catalog file stays useful for the roadmap.
**Location:** `shared/roadmap.ts`, `src/Atlas.tsx`, `src/App.tsx`.

## Language of the Atlas tab
**Chosen:** Russian mission titles as the primary label in the Atlas, English title as the subtitle in the card; the rest of the game stays English.
**Reason:** The owner asked for the tree in his language so he can read it; he is the only player today.
**Reversal cost:** A language toggle or swapping the two fields in one component; the catalog carries both.
**Location:** `shared/roadmap.ts`, `src/Atlas.tsx`.

## Workspace reset
**Chosen:** Reset copies the current workspace to a timestamped backup beside it before restoring the starter and regenerating the mission documents; rewards are never revoked and a repeat grants only stars not yet earned.
**Reason:** The owner wants to redo a mission differently without losing work or progress, and the project rule says preserve the player's work.
**Reversal cost:** Delete backups by hand; no schema change.
**Location:** `server/labs.ts`, `server/app.ts`.

## C3b: skills without XP are listed, not drawn as bars
**Chosen:** The snapshot carries every skill the catalog names (about thirty); the Skills section draws a bar only for skills with XP and lists the rest in one "Not practiced yet" line.
**Reason:** Thirty empty bars would bury the few that moved; the data stays complete for a later redesign.
**Reversal cost:** Drop the filter in `ProgressionPanel`; no data change.
**Location:** `src/ProgressionPanel.tsx`, `shared/progression.ts` (`skillSnapshots`).

## C3b: ★2 pays its XP before ★1
**Chosen:** A met or partial debrief grants ★2 and half the base XP even when the mission's Verify has not passed yet; stars stay independent as the design says.
**Reason:** The design states stars can be earned in any order; gating ★2 on ★1 would need a second grant path when ★1 arrives later.
**Reversal cost:** One condition in `debriefStar` plus a catch-up grant in `saveCheck`.
**Location:** `server/store.ts`.

## C3b: the legacy awards table is frozen, not removed
**Chosen:** `saveCheck` no longer writes `awards`; startup copies its rows into `star_awards` as ★1 and leaves the table in place. Total XP reads `star_awards` only.
**Reason:** Two live sources of XP would drift; keeping the old table costs nothing and keeps a downgrade readable.
**Reversal cost:** Re-add the one `INSERT OR IGNORE INTO awards` line.
**Location:** `server/store.ts`.
