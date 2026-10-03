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

The owner reported successful game startup, GPT connection and opening VS Code on October3. The initial subdued design was rejected, and the brighter revised version was explicitly approved. This is owner-reported acceptance of those steps; it does not extend to every integration scenario below.

1. Send a real free-text debrief. Confirm response compatibility, latency, feedback quality and the account's effective billing/allowance settings.
2. With both a work window and a workshop window open, verify the intended editor window, save/cancel handling, extension reconnect and transition back to a previous mission.
3. Try the real learning loop. Establish Python comfort and current English ability. Evaluate tutor feedback using `content/english-calibration.json`, then actual answers. The corpus is authored material, not human-calibrated CEFR ground truth.
4. Desktop Linux Secret Service/editor integration, Safari/Firefox, speech recognition/synthesis and later curriculum chapters are not yet exercised/shipped. Linux core-runtime portability has separate container evidence above. The first personally usable target is a desktop Chromium browser on this Mac.

## October3 visual/editor iteration

- The redesigned outpost, larger text, separated objectives and collapsed workspace details passed a fresh build,33 tests and2 headless E2E scenarios. The real rendered quest panel measured16px descriptions/objectives,50px main controls and contrast ratios12.59:1/11.73:1 for description/objective text; the two main buttons measured9.80:1/6.06:1. These are specific element measurements, not a complete accessibility audit.
- The editor bridge applies completion settings at Workspace scope: generated inline blocks/next-edit suggestions off, ordinary name/method/parameter IntelliSense on. The controlled-host test verifies the target and preservation of unrelated font/format settings. The current learning workspace was also configured directly; actual disappearance of an already visible ghost-text proposal was not observed by automation.
- System design was added to the future curriculum and chapter list. It is a planned track, not an additional executable lab in this version.

## Product boundaries

Six first-chapter labs are executable; later chapters are a curriculum blueprint. Language adaptation currently changes mission briefings and tutor instructions, with varied follow-up questions. It does not claim every external reference or code comment dynamically changes level. Only written interaction is tracked. Rank is a game progression indicator, not a job grade or language certification.

## Chat workspace and code-context iteration

- Fresh production build,36 Node tests and5 headless Chromium scenarios passed. The additional browser controls use synthetic long histories and do not send messages to a live model.
- The current code also built and passed all36 tests under Node24 / Python3.11 in a Linux amd64 container. This remains a core-runtime check, not a Linux desktop login/editor acceptance.
- A120-exchange history remained complete in a viewport-bounded chat. The composer stayed visible at desktop widths, old-message reading position survived new replies and view/quest switches, and mode/drafts restored after reload.
- GFM headings, emphasis, lists, tables, inline code and fenced code were rendered. Code copying preserved indentation and newlines using a test clipboard rather than the system clipboard. Raw HTML/script and unsafe links did not execute, and rendered images did not trigger remote requests. A very long code line scrolled within its block rather than widening the page.
- Read-only inspection of an existing local conversation confirmed the practical layout change: page height became viewport-bounded and chat width increased from340px to1158px at1440px viewport width. Previously recorded exchange content hashes remained unchanged; no inspection message was submitted.
- An owner-reported debug-print issue was resolved by saving the editor buffer. Coaching now receives saved-file timestamps, workspace provenance and explicit limits on editor/runtime visibility. Newly created helper modules are included; hidden files, common credential filenames, symlinks and dependency directories are excluded. File-count/size budgets and truncation are exercised by tests. This validates the supplied evidence, not a guarantee of every subsequent model diagnosis.
- A coaching payload regression check first failed because its `question` field contained the mission debrief instead of the learner's current debugging question. Coaching now binds this field to the latest learner message; the same check passes. Debrief grading keeps its original question contract. No extra live tutor messages were generated during these checks.
