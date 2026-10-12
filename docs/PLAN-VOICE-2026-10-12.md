# Plan: chapter IX labs G02–G46 (started 2026-10-12 18:25 MSK)

Authoring runs in batches of five missions by parallel author agents following `VOICE-AUTHORING.md`; the integrator wires `shared/voice.ts`, `shared/roadmap.ts` (runtime id) and `src/style.css`, runs the full Node and Playwright suites and commits one green batch at a time. A second agent then attempts each mission blind from LEARN.md and the starter (gate 6); its findings are applied before the next batch. Status: `planned` → `authored` → `integrated` (committed) → `reviewed`. From 19:25 on 2026-10-12 the pipeline runs in the main context, one mission at a time, no Fable subagents (owner's rule).

| ID | Runtime id | Block | Status |
| --- | --- | --- | --- |
| G01 | price | Calling the model | integrated (554ba6c) |
| G02 | sampling | Calling the model | reviewed |
| G03 | record | Calling the model | reviewed |
| G04 | backoff | Calling the model | reviewed |
| G05 | prompts | Calling the model | reviewed |
| G06 | window | Calling the model | reviewed |
| G07 | traces | Measuring the voice | planned |
| G08 | golden | Measuring the voice | planned |
| G09 | errorbars | Measuring the voice | planned |
| G10 | judge | Measuring the voice | planned |
| G11 | evalgate | Measuring the voice | planned |
| G12 | frontier | Measuring the voice | reviewed |
| G13 | ablation | Measuring the voice | reviewed |
| G14 | embeddings | The archive | reviewed |
| G15 | extraction | The archive | reviewed |
| G16 | chunking | The archive | reviewed |
| G17 | lexical | The archive | authored, reviewed, not integrated (uncommitted) |
| G18 | fusion | The archive | authored, reviewed, not integrated (uncommitted) |
| G19 | annindex | The archive | partial files in tree (agent stopped 19:25), rework in main context |
| G20 | citations | The archive | authored, review fixes interrupted (uncommitted) |
| G21 | reindex | The archive | authored, review stopped, not integrated (uncommitted) |
| G22 | rewrite | The archive | partial files in tree (agent stopped 19:25), rework in main context |
| G23 | tools | Hands of the voice | partial files in tree (agent stopped 19:25), rework in main context |
| G24 | textsql | Hands of the voice | partial files in tree (agent stopped 19:25), rework in main context |
| G25 | consent | Hands of the voice | partial files in tree (agent stopped 19:25), rework in main context |
| G26 | workflow | Hands of the voice | partial files in tree (agent stopped 19:25), rework in main context |
| G27 | agentloop | Hands of the voice | partial files in tree (agent stopped 19:25), rework in main context |
| G28 | compaction | Hands of the voice | partial files in tree (agent stopped 19:25), rework in main context |
| G29 | trajectory | Hands of the voice | partial files in tree (agent stopped 19:25), rework in main context |
| G30 | mcpserver | Hands of the voice | partial files in tree (agent stopped 19:25), rework in main context |
| G31 | injection | Guarding the voice | planned |
| G32 | outputs | Guarding the voice | planned |
| G33 | leakage | Guarding the voice | planned |
| G34 | redteam | Guarding the voice | planned |
| G35 | tracing | Running the voice | planned |
| G36 | latency | Running the voice | planned |
| G37 | cascade | Running the voice | planned |
| G38 | localweights | Running the voice | planned |
| G39 | rollout | Running the voice | planned |
| G40 | feedback | Running the voice | planned |
| G41 | silence | Running the voice | planned |
| G42 | design | Designing the voice | planned |
| G43 | strategy | Designing the voice | planned |
| G44 | onduty | Designing the voice | planned |
| G45 | distill | Optional limbs | planned |
| G46 | manyhands | Optional limbs | planned |
