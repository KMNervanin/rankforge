# First chapter handoff — 2026-10-03

## Ready to try

The repository is https://github.com/KMNervanin/rankforge and the working checkout is `~/rankforge`, branch `main`. The first chapter is a playable local application with six actual lab projects, independent technical checks, an animated outpost, persistent achievements, a field journal, free-text tutor/assessor integration and an editor bridge. [Русская инструкция](START_RU.md) covers installation and ordinary use.

From the checkout:

```sh
npm ci --include=dev
npm run build
npm start
```

Open `http://127.0.0.1:4173` in a desktop Chromium browser. The service starts quietly and does not open windows automatically. Build/install artifacts have been removed from the source checkout after verification, so the first two commands are intentional.

For a new machine, follow [Install and run](../README.md#install-and-run), including prerequisites, cloning the public repository and enabling the `code` command. Each person connects their own account; credentials and progress are local and are not shipped through GitHub.

## Personal use and remaining acceptance

On October3, the owner reported that the game started, GPT connected and VS Code opened. The revised, brighter visual style was then approved. This confirms the basic first-run path, not the quality of language assessment or every editor save/cancel scenario.

1. Open **Connection**, click **Connect ChatGPT**, then follow **Continue with ChatGPT**. This is a new local client login using the existing subscription. macOS Keychain/desktop Linux Secret Service may request permission. No previously stored Codex/OpenCode token has been copied.
2. Enter **A signal in the dark**. The service prepares a separate workspace and opens a dedicated VS Code extension-development window. Accept workspace trust if asked. Keep a normal work window open too and confirm it is not replaced.
3. Read `MISSION.md` and `LEARN.md`. Explore the broken service, repair it, save, then **Verify lab**. Use **Prepare workspace only** if you prefer to inspect files before opening the editor.
4. Submit a debrief in your own English. Judge whether the response is accurate, appropriate for your level and useful. Automated transport/parser tests do not establish tutor quality.
5. Switch to another available mission, cancel a switch with unsaved work once, and return. Confirm the workshop window and previous files are preserved. The extension retains a cancelled command until a deliberate retry or successful new-host acknowledgment.

## Verified evidence

- Latest macOS chat/context iteration:36 tests, production build,5 headless browser scenarios.
- Initial Linux arm64 and amd64 baseline: production build and33 tests under Node24 / Python3.11; amd64 used Docker Desktop emulation. Later checks are recorded separately in ACCEPTANCE.md.
- Actual nginx lab: broken502/missing200 → corrected200/404;5 checks, including an upstream-log proof of forwarding.
- Quota, auth failure, truncated streams, restart, duplicate submissions/rewards and workspace races have deterministic tests.
- Secrets scan and dependency audit found no issues at the recorded checkpoints.

Detailed distinctions and versions: [ACCEPTANCE.md](ACCEPTANCE.md). Decisions and reversibility: [decision log](decisions-2026-10-03.md).

## Boundaries and next work

- The owner reported successful account connection and opening VS Code. Real tutor-response quality, editor focus alongside work windows, and save/cancel behavior still need the corresponding checks above.
- The implemented language modality is writing. Listening/speaking and voice integration need a separate iteration.
- Only Chapter I is executable. Six further chapters have a concrete curriculum blueprint in [CURRICULUM.md](CURRICULUM.md), including the system-design track added after owner feedback. Design foundations start after Chapter I and return in later practical chapters; ML is not a prerequisite.
- Game ranks and language thresholds are provisional learning mechanics, not professional or CEFR certification. “Unassisted” reflects recorded in-game assistance, not a proctored exam or knowledge of external help.
- No lab/service process or newly tagged QA image is intentionally left running. Existing user projects, Docker contexts, VPN and work windows were preserved. Public image/build caches may remain in Docker's normal cache.

There is no automatic API-credit fallback. On subscription capacity failure, the submitted answer is stored and training pauses. Resume reuses the saved request rather than replaying completed rewards.
