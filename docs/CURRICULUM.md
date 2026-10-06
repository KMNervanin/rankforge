# Learning design

## Starting point

The learner is an experienced iOS developer with some backend practice and familiarity with APIs, services, SQL, Git and Docker. nginx and Kafka are new. Python fluency is unknown. The initial English reference is approximately A2–B1, not a current diagnostic result.

The first two missions act as low-stakes practical diagnostics. Explain unfamiliar Python syntax using the included field manuals. Existing knowledge can be demonstrated directly; there is no requirement to sit through introductory lectures. A successful lab is evidence of that particular outcome, not a professional grade or comprehensive subject mastery.

The complete proposed sequence is in [Course roadmap](COURSE-ROADMAP.md): **86 bounded missions**, comprising 68 core missions, 12 optional entry foundations and 6 optional ML missions. Nine catalog labs are implemented: I01–I06 and D01–D03. Another77catalog missions remain planned. One additional optional HTTP trial, outside that86count, makes10runtime quests. [Current acceptance](ACCEPTANCE.md) and the [guild release record](ARCHITECT-ACCEPTANCE.md) distinguish executable contracts from broader design judgement.

For a new programmer, foundations provide a route into Python, SQL, terminal work and quantitative reasoning. They are optional by demonstrated capability, not because the later course silently assumes those skills. An experienced learner can challenge the relevant outcome directly or use existing evidence; unfamiliar Python syntax does not imply unfamiliar programming. The proposed diagnostic routing and skip records are not shipped functionality.

## Two connected curricula

Engineering is represented by observable capabilities shared across domains. Language is represented by communication goals and independent writing observations. Neither curriculum is a list of product names. A tool appears when it makes an already-understood problem concrete.

Each mission contains: prerequisites, a repair/build objective, an executable acceptance contract, a short conceptual model, a terminal investigation, an optional free-text debrief, progressive hints, an artifact and follow-up opportunities. The learning loop is **observe → predict → act → verify → explain → return later**. Code and operational work happen in the learner's own IDE and terminal; the browser presents the world, contracts and evidence.

The whole game, mission material and language practice are in English. Technical depth and English difficulty advance independently. A skipped post-brief, grammar mistake, unavailable tutor or exhausted model quota must not block a verified technical outcome. This is the target course policy; a documentation change alone does not establish its implementation in every progression path.

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

These are implemented labs, not six independently certified learning outcomes. Their brief, starter, hints and verifier must agree. In Signal, the initial unconditional 503 is a starter defect; it does not imply an unmentioned dependency-failure branch. Required behavior, the deliberately broken starting behavior and optional theory must be visibly distinct. Hidden examples may exercise published rules; hidden requirements and source-code-pattern matching are not acceptable substitutes for behavioral checks.

## Subsequent campaign blueprint

The [mission catalog and prerequisite DAG](COURSE-ROADMAP.md#prerequisites-and-ordering) replace the earlier mission-family sketch as the planning sequence. IDs below are documentation identifiers, not new runtime unlocks. Chapters are released in small verified blocks; listing an outcome does not mean its starter, checker or teaching material exists.

| Stage | Missions | Learning emphasis | Connection and language goal |
| --- | --- | --- | --- |
| Optional entry workshop | F01–F12, 12 | Python from first functions, debugging/tests, Git, HTTP, SQL, units, processes and containers | Enter only where a capability is missing; ask a specific question and describe a check |
| I — The silent outpost | I01–I06, 6 implemented | HTTP, relational integrity, gateway routing, idempotency, exact ETL and recovery | The existing diagnostic/repair loop; narrate evidence |
| II — The architect's guild | D01–D03 implemented; D04–D06 planned | Requirements, capacity arithmetic, executable contracts, then boundaries, ADR and changed requirements | Design before adding components; clarify, compare and justify |
| III — The service workshop | B01–B08, 8 planned | A maintainable API, persistence, pagination, transactions, concurrent writers and migrations | Evolve the same delivery service; explain invariants |
| IV — Evidence and trust | T01–T04 + S01–S06, 10 planned | Unit/integration/contract/fault tests; authentication, authorization, secrets and abuse limits | Protect other users' data and challenge a passing test; report a counterexample |
| V — Reliable operations | O01–O08, 8 planned | Reproducible configuration/builds, CI, telemetry, SLOs, rollout, restore and incident response | Operate the service before scaling it; give an actionable handover |
| VI — Under pressure | L01–L08, 8 planned | Workload measurement, plans/indexes, algorithmic cost, caching, deadlines, scaling and backpressure | Revisit capacity and failure domains with measurements; distinguish estimates from observations |
| VII — The event frontier | A01–A08, 8 planned | Durable jobs, outbox, Kafka partitions/groups/offsets, replay, schema evolution and compensation | Trace consistency per operation, not slogans; explain an uncertain outcome |
| VIII — The data district | W01–W10, 10 planned | Incremental ingestion, schedules/backfills, warehouse grain/history, SQL analysis, lineage, quality, privacy and batch/stream | Reconcile service facts with reports; state freshness and limitations |
| Optional model laboratory | M01–M06, 6 planned | Just-in-time math, a non-ML baseline, splits/leakage, simple training, serving and drift | Interpret an experiment honestly; quantify error and uncertainty |
| IX — The independent outpost | C01–C04, 4 planned | A bounded capstone: contract, vertical slice, failure drill and a changed requirement | Transfer across the system; defend a decision with reproducible evidence |

System design remains an explicit thread from Chapter II through operations, load, events, data and the capstone. Begin with users, constraints, request/data paths and ownership; then revisit load balancing, replication, partitioning and recovery as actual problems justify them. Compare a modular monolith with a split service and specify what evidence would change the decision. An elaborate diagram or more tools do not earn a higher score.

The proposed connected campaign evolves the outpost's delivery service, inventory and reports. Old data, delayed/duplicated deliveries and new requirements create consequences across these boundaries. Connections must be implemented through versioned artifacts and opt-in imports; mission selection never permits overwriting a learner workspace. The existing six labs are separate workspaces, not an already integrated production system.

Use local data and the smallest useful runtime: Python/SQLite first, PostgreSQL for concurrent-client experiments, the existing nginx/Compose boundary when needed, and one disposable Kafka node for broker-specific learning. No Kubernetes, cloud account, distributed-processing cluster or GPU prerequisite. A single-node experiment does not demonstrate production availability. Runtime versions, resource limits and platform evidence must be established when each block is authored.

ML is optional and never unlocks the core capstone. Introduce only the mathematics needed to interpret the experiment; teach SQL and Python gaps before relying on them. Serving a pretrained model is not evidence of learning to train or evaluate one. Completion means an evidence-backed small system and broader independence, not a production-senior title, job guarantee or exhaustive mastery of every discipline.

## Fair mission authoring

Each future mission needs a visible contract covering allowed inputs, outputs, errors, preserved state and the tested failure model. Separate required behavior from examples, starter defects and optional stretch work. Bind every blocking check to a published requirement. Specify an algorithm or tool only if it is itself the learning objective; otherwise accept all implementations satisfying the same observable contract.

Before release, demonstrate that the starter fails for the intended reason, independently derived valid alternatives pass, and plausible incorrect implementations fail. Include fresh values, boundary cases, persisted-state checks and a transfer variant. Recheck the actual brief → saved IDE artifact → terminal/Verify failure → repair → pass path in a disposable workspace, with headless browser checks. Generated solutions and tests can share an error; a shared author or a second model's agreement is not sufficient independent validation.

The roadmap defines a [release gate](COURSE-ROADMAP.md#authoring-and-release-gates), a smaller [next-block contract](COURSE-ROADMAP.md#next-candidate-block), and explicit limits on architecture evaluation. These are requirements for future implementation, not a claim that an audit or live evaluation was run for this document.

## English learning loop

Initial objectives: ask a concrete question, describe present state, narrate an action, express cause, compare results, explain a choice and hand over work. Recurring patterns include `I checked…`, `It failed because…`, `If …, then …`, `I expected …, but …`, and `I chose … so that …`. These are optional supports, never exact-match answers.

- Input difficulty: guided short statements → connected explanations → independent natural exchanges.
- Evaluation: communicative goal, comprehensibility, quoted evidence, at most two useful corrections, one next-use prompt.
- Assistance: technical hints affect technical independence. Explicit tutor coaching is conservatively marked as supported language practice for that exchange. It must not permanently prevent future independent evidence.
- Repetition: revisit patterns after a delay, change the communication situation, and avoid awarding progress for the same answer repeatedly.
- Evidence: one qualifying mission/day observation; more than one mission and day required for promotion. Thresholds are provisional, versioned product heuristics, not validated CEFR cutoffs.
- Coverage: written interaction is implemented first. Listening and speaking require their own exercises and verification; they are not inferred from text.
- Participation: offer briefings, incident notes, review questions and optional post-briefs repeatedly, with simpler English scaffolds when helpful. Technical completion does not require a particular phrase, a language rank or a model response. Preserve pending messages on quota/authentication failure; do not introduce a paid fallback.

## Evaluation responsibility

Executable checks own technical pass/fail. The model can discuss trade-offs and language but cannot override a failed check. The local state machine owns progression, idempotent awards and paused jobs. Tutor responses are not trusted to change game state directly.

For planned system-design missions, review against explicit requirements, capacity calculations, coherent data/request paths, failure handling and justified trade-offs. Missing a critical requirement requires revision even if the diagram looks convincing. Check arithmetic and any implemented probe with executable tools; treat model critique of the remaining design as formative feedback rather than an objective correctness oracle. Preserve the learner's diagram, assumptions and decision record as evidence, with no mandatory single reference architecture.

Record these separately: executable contract result, submitted design evidence, review observations and demonstrated transfer/independence. A complete template only proves submission; a passing probe proves its measured claim, not the whole architecture. If review identifies a concrete contradiction, reproduce it against a published rule; do not turn free-text praise or criticism into a deterministic progression gate. When no qualified review is available, mark review as pending rather than fabricating an architecture pass.

Model assessment is useful formative feedback, not an exam certificate. Before accepting reliable rank calibration, evaluate paraphrases, understandable errors, fluent off-topic answers, incorrect technical claims, requests to change the grading rules and ambiguous answers. A second model agreeing is not independent human validation. The calibration corpus is authored test material, not live accuracy evidence.

## Evidence basis

The [ten references reviewed on 2026-10-06](COURSE-ROADMAP.md#reference-coverage-and-limitations) cover entry programming, Python, HTTP, databases, security, reliability/design, messaging, data engineering, basic ML and language modalities. They inform coverage and specific boundaries, not the validity of unbuilt labs. Course text and exercises here are newly authored; no endorsement, live tutor evaluation, learner outcome study or professional certification is implied.
