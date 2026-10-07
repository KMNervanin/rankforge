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
