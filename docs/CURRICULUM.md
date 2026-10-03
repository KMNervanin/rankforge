# Learning design

## Starting point

The learner is an experienced iOS developer with some backend practice and familiarity with APIs, services, SQL, Git and Docker. nginx and Kafka are new. Python fluency is unknown. The initial English reference is approximately A2–B1, not a current diagnostic result.

The first two missions act as low-stakes practical diagnostics. Explain unfamiliar Python syntax using the included field manuals. Existing knowledge can be demonstrated directly; there is no requirement to sit through introductory lectures. A successful lab is evidence of that particular outcome, not a professional grade or comprehensive subject mastery.

## Two connected curricula

Engineering is represented by observable capabilities shared across domains. Language is represented by communication goals and independent writing observations. Neither curriculum is a list of product names. A tool appears when it makes an already-understood problem concrete.

Each mission contains: prerequisites, a repair/build objective, an executable acceptance contract, a short conceptual model, a terminal investigation, a free-text debrief, progressive hints, an artifact and follow-up opportunities. The learning loop is **observe → predict → act → verify → explain → return later**.

## Chapter I — The silent outpost (implemented labs)

| Mission | Capability | Evidence | Language goal |
| --- | --- | --- | --- |
| A signal in the dark | Inspect and satisfy an HTTP contract | Actual HTTP status, headers and JSON on valid/unknown paths | Describe a symptom, action and check |
| Give memory a structure | Put relational integrity in the database | SQLite rejects invalid records, accepts valid ones, preserves data on repeat setup | Explain a design choice and its consequence |
| Open the right gate | Route through a reverse proxy | Real nginx syntax check and requests across Compose networking | Describe a request path and clarify terminology |
| An echo is not an event | Persist event identity and make retries safe | Replay, conflict, invalid input and reconnect tests | Explain cause, effect and contrast |
| Numbers that tell the truth | Transform data without hiding losses | Exact decimal sums, normalization, rejected rows and repeatability | Compare expected and observed results |
| After the blackout | Rebuild trusted state atomically | Recovery, replay, replacement and failure-preserves-old-state tests | Give a connected handover and justify a decision |

Dependencies: signal → vault → echo → ledger; signal → gateway; gateway + ledger → recovery. Gateway can be studied before or after the data branch. Recovery is a transfer challenge; its solution is not supplied to the tutor. References and QA solutions are separate from generated learner workspaces.

## Subsequent campaign blueprint

These chapters are designed, not yet executable. Each row is a planned mission family, not a shipped feature.

### II — Under pressure

1. **Measure before scaling:** latency distribution, throughput, saturation; establish a repeatable workload and a baseline.
2. **The slow archive:** read a query plan, choose an index, compare both query performance and write cost.
3. **A crowded gate:** upstream timeout versus application failure; reproduce and localize a bottleneck.
4. **Borrowed memory:** cache identity, invalidation and stale reads; prove correctness after a write.
5. **Pressure valves:** bounded queues, backpressure, retry budgets and graceful degradation.
6. **Rank trial:** unfamiliar workload regression; diagnose with evidence rather than adding replicas by habit.

Prerequisites: HTTP, relational storage, basic diagnostics. Cross-links: warehouse performance, streaming ingestion, model-serving latency.

### III — Reliable operations

1. **The reproducible machine:** Linux processes, permissions, environment, ports and signals.
2. **The release bridge:** build/test pipeline and reproducible deployment artifact.
3. **Change without amnesia:** forward-compatible migrations, rollback limitations and data preservation.
4. **A light in the fog:** structured logs, metrics, traces and actionable alerts.
5. **The locked gate:** authentication versus authorization, secrets, least privilege and request validation.
6. **Disaster drill:** verified backup/restore and a short runbook another operator can use.

Prerequisites: the first chapter and measurement basics. Cross-links: delivery pipelines and ML operations. No Kubernetes prerequisite; introduce orchestration only when its problem is demonstrated.

### IV — The event frontier

1. **A message outlives its sender:** synchronous request versus durable messaging.
2. **Kafka's map:** topics, partitions, keys and ordering within a partition.
3. **Shared work:** consumer groups, assignment and rebalancing.
4. **The bookmark:** offsets and restart behavior.
5. **The repeated delivery:** acknowledgement timing, idempotent effects and failed-message handling.
6. **Lag under pressure:** measure lag, inspect a slow consumer and apply a justified fix.

Prerequisites: durable identity, retries, container networking and basic observability. Start with a single-node disposable learning environment; distinguish it from a production design.

### V — The data district

1. **Sources do not agree:** schema, units, identity, time zones and missing values.
2. **Only what changed:** incremental ingestion, watermarks, late arrivals and replay.
3. **Reliable schedules:** dependencies, retries, backfills and idempotent orchestration.
4. **One fact, many questions:** operational schema versus analytical model; facts, dimensions and grain.
5. **Trust the report:** quality checks, reconciliation, lineage and schema evolution.
6. **Batch meets stream:** select processing mode from freshness and correctness needs.

Prerequisites: relational integrity, repeatable ETL, event semantics. First use local data; distributed processing is introduced only after measuring a reason for it.

### VI — The model laboratory

1. **A useful question:** choose a modest classification/regression task and a non-ML baseline.
2. **A fair experiment:** training/validation/test splits, leakage and reproducibility.
3. **What does 'good' mean?:** basic metrics, class imbalance, error examples and uncertainty.
4. **A small model:** train one understandable model and compare with the baseline.
5. **A model is a service:** input validation, artifact versioning and inference endpoint.
6. **When the world changes:** data drift observation, monitoring and a retraining decision.

This is an optional foundation, not a promise of data-science specialization. Introduce only the mathematics needed to interpret the experiment. Serving a pretrained model does not count as learning to train or evaluate one.

## English learning loop

Initial objectives: ask a concrete question, describe present state, narrate an action, express cause, compare results, explain a choice and hand over work. Recurring patterns include `I checked…`, `It failed because…`, `If …, then …`, `I expected …, but …`, and `I chose … so that …`. These are optional supports, never exact-match answers.

- Input difficulty: guided short statements → connected explanations → independent natural exchanges.
- Evaluation: communicative goal, comprehensibility, quoted evidence, at most two useful corrections, one next-use prompt.
- Assistance: technical hints affect technical independence. Explicit tutor coaching is conservatively marked as supported language practice for that exchange. It must not permanently prevent future independent evidence.
- Repetition: revisit patterns after a delay, change the communication situation, and avoid awarding progress for the same answer repeatedly.
- Evidence: one qualifying mission/day observation; more than one mission and day required for promotion. Thresholds are provisional, versioned product heuristics, not validated CEFR cutoffs.
- Coverage: written interaction is implemented first. Listening and speaking require their own exercises and verification; they are not inferred from text.

## Evaluation responsibility

Executable checks own technical pass/fail. The model can discuss trade-offs and language but cannot override a failed check. The local state machine owns progression, idempotent awards and paused jobs. Tutor responses are not trusted to change game state directly.

Model assessment is useful formative feedback, not an exam certificate. Before accepting reliable rank calibration, evaluate paraphrases, understandable errors, fluent off-topic answers, incorrect technical claims, requests to change the grading rules and ambiguous answers. A second model agreeing is not independent human validation. The calibration corpus is authored test material, not live accuracy evidence.

## Evidence sources reviewed 2026-10-03

- https://roadmap.sh/backend — coverage of backend concepts and practice.
- https://roadmap.sh/devops — delivery, operation, automation and observability.
- https://github.com/DataTalksClub/data-engineering-zoomcamp — pipelines, orchestration, warehousing, analytics engineering, batch and streaming.
- https://developers.google.com/machine-learning/crash-course — data, generalization, metrics and production context.
- https://europass.europa.eu/en/common-european-framework-reference-language-skills — distinct language modalities and communicative descriptors.
- https://developers.openai.com/api/docs/guides/evaluation-best-practices — judge rubrics, bias and calibration against human labels.

These references inform coverage. Course text and exercises here are newly authored; no claim is made that the referenced organizations endorse the game.
