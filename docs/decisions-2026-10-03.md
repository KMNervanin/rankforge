# Decisions — 2026-10-03

## Where and what to call it
**Chosen:** `~/rankforge`, private `KMNervanin/rankforge`.
**Why:** Separate personal project; no coupling to existing product or work repositories.
**Reversal:** Rename folder/repository/display title.
**Location:** repository root and package metadata.

## Runtime and visual stack
**Chosen:** Node 24+ / TypeScript / Fastify 5, SQLite, React 19 and PixiJS 8.
**Why:** Shared language with the inspected subscription adapter; builtin SQLite avoids native package setup; actual browser-rendered world with accessible DOM controls.
**Reversal:** Renderer is a view of persisted domain state; changing it does not alter curriculum or saves.
**Location:** `server/`, `shared/`, `src/`.

## First chapter lab language
**Chosen:** Python standard library, SQLite and one nginx Compose lab.
**Why:** One practical language crosses backend, data and introductory ML without installing a large framework before the first task. Prior API/SQL experience is recognized.
**Reversal:** Add language variants to mission manifests; competency identities stay stable.
**Location:** `labs/`, `shared/content.ts`.

## Provider and auth boundary
**Chosen:** Adapt OpenCode's MIT-licensed direct ChatGPT OAuth flow into a local-only provider; no CLI, automatic existing-token import, API key, or paid fallback.
**Why:** Explicit owner requirement, supported by inspected `opencode` 1.18.34 source. New-client compatibility still requires a real login acceptance check.
**Reversal:** Provider interface isolates transport from game and assessment state.
**Location:** `server/provider.ts`, `THIRD_PARTY_NOTICES.md`.

## Reuse research
**Chosen:** Fastify/React/PixiJS rather than building HTTP, UI reconciliation or rendering engines. A small purpose-built domain layer joins real lab evidence and adaptive language practice.
**Why:** Reviewed official docs: roadmap.sh for competency coverage, DataTalksClub Zoomcamp for data sequencing, Google MLCC for ML foundations, Europass CEFR for separate modalities, OpenAI eval guidance for judge calibration. None is being copied into a new course wholesale.
**Reversal:** Content is plain manifests/Markdown and labs are independent projects.
**Location:** `docs/CURRICULUM.md`, `content/`, `shared/content.ts`.
