# Autonomous implementation — 2026-10-03

Start: 04:07 MSK. Owner expects to return around 12–13. Initial repository: empty, no baseline tests. Working title: **Rankforge**. Private repository: KMNervanin/rankforge.

## Product contract

Desktop browser game + owned local service + a dedicated VS Code window. Six real first-chapter labs, English immersion, evidence-based advancement, a living base and RPG ranks. Use existing ChatGPT subscription through a direct provider adapter. Preserve work when switching, pausing, restarting or hitting a limit. Git/Docker familiarity is not assumed to cover all operations; nginx starts guided, Kafka is a later chapter. No automatic UI launch or owner authorization during the autonomous run.

## Milestones and acceptance

1. Foundation: private repo, reproducible build, persisted state, loopback-only routes, concrete curriculum and decision log.
2. Vertical slice: prepare mission → edit actual workspace → run independent checker → persist evidence → update base. Fresh broken work must fail and a real solution must pass.
3. Subscription adapter: isolated OAuth/refresh/SSE implementation, typed failures, no API-key path. Contract tests with local mock transport; actual owner login is deferred.
4. Six labs: HTTP service, relational storage, nginx gateway, duplicate events, ETL ledger, recovery capstone. Reference solutions pass and broken fixtures fail; public requirements are distinct from checker implementation.
5. English: durable free-text exchanges, rubric-backed feedback, source quotations, support tracking, repeated evidence and due practice. Never report unsupported CEFR certification or speaking ability.
6. Editor bridge: scoped polling from a small extension. Switch inside its own game window; reconnect after extension-host restart. Extension is packaged but not installed unattended.
7. Visual world: responsive desktop shell, animated 2D outpost, mission panel, journal, competencies, connection and pause state. Test headlessly in light/dark system settings, keyboard use, and restart/resume.
8. Hardening: input boundaries, pending-request recovery, single-award transaction, concurrent actions, lesson/helper separation, user-facing failures. Commit and push verified stages.

## First acceptance boundary

Ship a usable local first chapter, not the entire future curriculum. Real OAuth with the owner's subscription, actual editor focus, pedagogical quality over multiple sessions and genuine language calibration remain explicit owner-facing checks. No mock verdict will be described as live model accuracy.
