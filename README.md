# Rankforge

A personal, local-first engineering learning RPG. Build a living outpost by solving real backend, operations and data problems. Practice English through meaningful conversations, with difficulty adapted to evidence of learning.

The browser is the game, VS Code is the workshop, and the terminal is a real tool. Subscription access uses a direct ChatGPT OAuth adapter; no Codex CLI or paid API fallback is required.

## Development status

The first chapter has six executable labs, a rendered outpost, durable progress, a subscription adapter and a scoped editor bridge. [Acceptance](docs/ACCEPTANCE.md) distinguishes real checks from deferred account/editor acceptance and language-model calibration.

## Run

Requires Node.js 24+, npm, Python 3.10+ and VS Code. Docker Desktop/Engine is needed for the gateway lab only.

```sh
npm ci
npm run build
npm start
```

Open `http://127.0.0.1:4173` yourself. The service does not open browser windows or start a login flow automatically. User state lives in `~/.local/share/rankforge`, outside the checkout. Set `RANKFORGE_HOME` to use a different location and `RANKFORGE_PORT` to change the port.

For development, run `npm run dev` and `npm run web:dev` in separate terminals.

The game opens VS Code only after you click a mission. It uses a dedicated extension-development window, so global extension installation is not required. VS Code may ask you to trust the generated workspace on first use. Keep that workshop window open; later missions replace its workspace after the editor's normal unsaved-file handling. A cancelled transition can be retried with **Open workshop**.

Connect ChatGPT from the game's **Connection** page. Credentials are stored in macOS Keychain; Linux requires a working Secret Service and `secret-tool`. No existing OpenCode or Codex credential is imported automatically. No API key is accepted. This is subscription usage with its normal limits, not a general-purpose OpenAI API account.

## Verify

```sh
npm test
npm run build
npx playwright install chromium --only-shell
npm run test:e2e
npm run test:gateway
```

`test:gateway` needs a running Docker engine. It starts a uniquely named temporary Compose project, demonstrates a failing and repaired route, then removes only that project's containers/network/volumes. Existing Docker context and other projects are left alone. Python checks execute trusted learner code locally with a restricted environment and a timeout; they are not a security sandbox for arbitrary uploaded code.

The gateway exercise uses `GATEWAY_PORT=45113 docker compose up -d` if its default port45103 is occupied. The verifier discovers the actual published port. The service uses port4173 by default; one process owns each save directory, so starting a second instance does not rotate its editor credentials or interrupt pending evaluations.

`npm run extension:package` creates an optional VSIX. Do not install it into all workspaces by default; the game-scoped development window is sufficient.

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
