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

## Real lab execution and host boundaries
**Chosen:** Python exercises run locally as the learner; nginx uses a uniquely named Compose project. The service preserves the active Docker context and only inspects the selected lab.
**Why:** The owner wants actual terminal/IDE work. This is a personal trusted-code workshop, not a hardened service for arbitrary uploaded code.
**Reversal:** Replace the lab executor with a container/VM backend without changing the mission contracts.
**Location:** `server/labs.ts`, `server/verify.py`, `labs/gateway`.

## Editor control
**Chosen:** Start one extension-development workshop window on explicit mission click; a small extension switches folders in its own host and reconnects after reload.
**Why:** `code --reuse-window` targets the last active window and could replace an unrelated work project. Owner focus is not touched during autonomous checks.
**Reversal:** Package/install the same extension or later wrap the web frontend in a desktop shell.
**Location:** `server/app.ts`, `extension/src/extension.ts`.

## English evidence and support
**Chosen:** Separate technical hints from language support; coaching support expires after a day, follow-up questions vary, and identical repeated answers do not add evidence.
**Why:** A SQL hint does not establish weak English, and early coaching must not permanently block future independent learning. Repetition must involve retrieval and transfer.
**Reversal:** Thresholds and scheduling are isolated in Store; raw answers, original questions and grades remain available for recalibration.
**Location:** `server/store.ts`, `shared/content.ts`, `content/english-calibration.json`.

## Local HTTP verification on this Mac
**Chosen:** Disable reverse DNS for the verifier's loopback HTTP server and use an explicit proxy-free loopback client.
**Why:** Observed HTTPServer startup took about35 seconds under the current DNS environment; direct requests then finished immediately. The same checker now finishes in about0.5seconds without touching VPN or DNS configuration.
**Reversal:** Use standard HTTPServer if the deployment no longer needs this local workaround.
**Location:** `server/verify.py`, `labs/signal/service.py`.

## Canvas rendering under Content Security Policy
**Chosen:** Use PixiJS8.22's `pixi.js/unsafe-eval` static polyfill with a CSP that does not permit unsafe-eval.
**Why:** Enabling CSP exposed the renderer's normal dynamic shader-sync generation. The installed package documentation and source confirm this counterintuitively named import removes the eval requirement. Fresh browser tests rendered the canvas with zero console errors.
**Reversal:** Replace the renderer while preserving the surrounding DOM interface.
**Location:** `src/Outpost.tsx`, `server/app.ts`.
