# Acceptance record

Checkpoint: 2026-10-03, 05:54 MSK. macOS arm64, Node25.8.1, Python3.14.5, Docker29.1.2 / Compose2.40.3, VS Code1.138.0. User authorization and GUI interaction are intentionally not part of the unattended run.

## Verified on the actual implementation

- `npm test`:33 tests passed,0 failed. Includes real Python lab execution, API integration, persistent state, prerequisites, single-award behavior, interrupted answer recovery, request idempotency, promotion evidence, delayed support expiry, workspace ownership, atomic concurrent preparation and local single-instance ownership. The documented standalone entry point was started, stopped, restarted and challenged with a competing process.
- `npm run build`: TypeScript check, production browser build and editor-extension build passed.
- `npm run test:e2e`:2 headless Chromium tests passed. Real browser → local HTTP service → persisted workspace → broken Python candidate fails → repaired candidate passes →120XP once. Draft, submitted answer, selected mission and paused state survive reload. Returning to the first workspace retains its solution. Desktop widths1024/1280/1600 have no horizontal page overflow; navigation and keyboard focus verified. The actual Pixi canvas rendered under strict CSP using its documented static shader/uniform polyfill; no browser console errors were observed in the full loop.
- `npm run test:gateway`: real Docker/nginx broken fixture gave502 on API health and200 on a missing path. Repaired configuration gave200 relay JSON and404 unknown path. A unique request identifier was confirmed in the upstream relay log, proving forwarding and prefix removal. All5 gateway checks passed. Temporary project cleaned up; pre-existing running container IDs unchanged on the first audit.
- `npm run extension:package`: built a local VSIX. No installation was performed.
- Linux portability: production build and all33 tests passed in Node24 / Debian Bookworm / Python3.11 containers on both `linux/arm64` and `linux/amd64` (amd64 emulated by Docker Desktop). This covers the service, SQLite, Python labs and controlled editor/auth contracts, not a desktop Linux login or actual editor window. Test containers and explicitly created image tags were removed.
- Playwright teardown now explicitly uses SIGTERM so the test service removes its temporary save directory. A fresh browser run passed and a filesystem check found no remaining mission-marker files in owned temporary test homes.

## Verified with controlled adapters, not live provider/editor claims

- Direct provider transport sends the actual subscription endpoint, Bearer OAuth access token, account header and `store:false`; no API-key or paid fallback path exists.
- Refresh is deduplicated for concurrent consumers. HTTP402/429 pause as capacity failures;401/403 require reconnect. Interrupted/malformed streams do not count as complete answers.
- Actual loopback OAuth callback tested on an ephemeral port with mocked token exchange and in-memory credentials. PKCE/state validation, invalid Unicode state, one credential write and callback shutdown verified. This does not prove OpenAI will authorize this new client configuration.
- Editor extension's actual bundled code tested with a controlled VS Code host. It issues `vscode.openFolder` with `forceReuseWindow:true` inside its own host, avoids repeat prompts after a cancelled transition and rereads rotated local bridge credentials. This does not prove actual macOS focus or unsaved-editor behavior.
- Language parser validates exact evidence/correction quotations. Scheduling and progression were tested with synthetic grades. Those tests do not establish grading accuracy.

## Owner-facing acceptance still required

1. Open the local game, connect the subscription through its sign-in flow and send a real free-text debrief. Confirm response compatibility, latency and the account's effective billing/allowance settings.
2. Click a mission with both a work window and a workshop window open. Verify the intended editor window, save/cancel handling, extension reconnect and transition back to a previous mission.
3. Try the real learning loop. Establish Python comfort and current English ability. Evaluate tutor feedback using `content/english-calibration.json`, then actual answers. The corpus is authored material, not human-calibrated CEFR ground truth.
4. Desktop Linux Secret Service/editor integration, Safari/Firefox, speech recognition/synthesis and later curriculum chapters are not yet exercised/shipped. Linux core-runtime portability has separate container evidence above. The first personally usable target is a desktop Chromium browser on this Mac.

## Product boundaries

Six first-chapter labs are executable; later chapters are a curriculum blueprint. Language adaptation currently changes mission briefings and tutor instructions, with varied follow-up questions. It does not claim every external reference or code comment dynamically changes level. Only written interaction is tracked. Rank is a game progression indicator, not a job grade or language certification.
