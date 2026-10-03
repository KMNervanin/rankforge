# Rankforge

A personal, local-first engineering learning RPG. Build a living outpost by solving real backend, operations and data problems. Practice English through meaningful conversations, with difficulty adapted to evidence of learning.

The browser is the game, VS Code is the workshop, and the terminal is a real tool. Subscription access uses a direct ChatGPT OAuth adapter; no Codex CLI or paid API fallback is required.

## Development status

Initial implementation in progress. Acceptance and remaining owner-only checks are recorded in `docs/ACCEPTANCE.md` when verified.

## Run

Requires Node.js 24+, npm, Python 3.10+ and VS Code. Docker Desktop/Engine is needed for the gateway lab only.

```sh
npm ci
npm run build
npm start
```

Open `http://127.0.0.1:4173` yourself. The service does not open browser windows or start a login flow automatically. User state lives in `~/.local/share/rankforge`, outside the checkout. Set `RANKFORGE_HOME` to use a different location and `RANKFORGE_PORT` to change the port.

For development, run `npm run dev` and `npm run web:dev` in separate terminals.

## Principles

- Technical outcomes come from actual lab checks, not a model's praise.
- English feedback accepts free phrasing and preserves quoted evidence.
- Practice completion and independent mastery are separate.
- Quota exhaustion saves the submitted answer and pauses evaluation; resume never duplicates rewards.
- Each mission has its own workspace. Switching never overwrites previous work.
- The local service manages only Rankforge workspaces; existing projects and Docker contexts are preserved.
- Reading/writing evidence does not claim speaking or listening proficiency.

## Project notes

- [Implementation plan](docs/PLAN.md)
- [Decision log](docs/decisions-2026-10-03.md)
- [Curriculum](docs/CURRICULUM.md)
- [Third-party notices](THIRD_PARTY_NOTICES.md)

Private personal project. No public service or shared subscription gateway is exposed.
