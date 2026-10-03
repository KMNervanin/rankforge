# Rankforge

- Personal desktop-first browser learning RPG, macOS and Linux. No mobile target.
- Preserve the player's work and progress. Mission selection is not permission to reset a workspace.
- Technical completion requires real checks. A simulated model is test-only and must never be represented as a live evaluation.
- No pay-as-you-go fallback. Quota and authentication failures preserve pending messages.
- Keep auth credentials out of the browser, git, logs and learning history.
- Existing Docker contexts, services, editor windows and repositories belong to the owner. Only manipulate explicitly owned lab resources.
- Browser testing is headless. Do not launch VS Code, install the extension, open a browser or initiate real authorization unattended.
- Use actual Node test runner and Playwright checks. `npm run build`, `npm test`, `npm run test:e2e`.
- Commit intentionally named files only. Keep public-provider adapter changes isolated and documented.
- After verification remove generated build/test/install artifacts before final status; leave a lockfile and reproducible commands.
