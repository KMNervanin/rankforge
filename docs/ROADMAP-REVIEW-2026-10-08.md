# Roadmap review — two opinions, 2026-10-08

Owner questions: does `COURSE-ROADMAP.md` match what backend engineers, DevOps/SRE engineers and system architects actually do; are the three archetypes' skills connected and complementary; how many blocks and missions cover the vast majority of real tasks, counting repetition in changed form as good practice. Two independent reviews: this session, and the Kimi agent through the `rankforge` team channel. Subtask C1 of `PLAN-CONTENT-2026-10-08.md`.

## What the roadmap is today

Eleven blocks, 86 missions: 68 core in nine blocks (I outpost 6, II architect's guild 6, III service workshop 8, IV testing 4 and security 6, V operations 8, VI load 8, VII events 8, VIII data district 10, IX capstone 4) plus two optional branches (foundations 12, model laboratory 6). Ten missions run today: I01–I06, D01–D03 and the optional HTTP trial. Six revisit rows reuse existing missions in a changed situation. Kubernetes, Terraform, managed cloud, Spark/Flink and extra caches are explicitly not required; no observability vendor, Redis, cloud IAM or IaC appears anywhere. No hours are given, deliberately.

## Review A — this session

### The archetype question

The owner is right in substance. Backend, SRE/platform and architecture stand on one foundation: networking and HTTP, data and transactions, processes and containers, observability, failure and recovery. They differ in depth per area and in the scale of responsibility, not in the list of skills. The industry names are backend engineer, SRE or platform engineer, and solutions architect or staff/principal engineer; "system architect" is understood. The one correction: these are not three parallel classes but one ladder. An architect without backend and operations experience draws diagrams nobody can run; a senior backend engineer in a small team already does most of the infrastructure and half of the architecture. For the game this means a common trunk with branches that thicken toward the higher ranks, which is what the roadmap already does by threading design (D) through every later block.

### Coverage against real work

Strong and correctly weighted: data integrity and transactions (I02, I04, I05, B04, B06, B07, B08), messaging and consistency (VII), operations fundamentals (V, especially O04, O05, O07, O08), security practice (S01–S06), the design thread (D01–D06, W10, C01) and the repair-first first chapter, which is how real engineers meet real systems.

Gaps, in order of how often the missing skill appears in real backend and platform work:

1. **Integrations with unreliable third parties.** Calling an external API that times out, rate-limits and returns garbage; outbound and inbound webhooks with signatures and idempotency keys; retries with backoff and jitter; circuit breaker and bulkhead. L05 covers pools, timeouts and cancellation inside our own system and A02/A05 cover our own delivery, but nothing makes the player the client of someone else's broken service. This is weekly work for a backend engineer.
2. **HTTP caching and conditional requests.** ETag, Cache-Control, 304, cache keys with authorization. L04 covers application cache identity only.
3. **Time.** Time zones, DST, scheduling, monotonic versus wall clock, retention windows. A classic bug source; absent except implicitly in W02 watermarks and W08 retention.
4. **Platform work the DevOps archetype is hired for.** Declarative deployment on a local Kubernetes (kind or k3d), infrastructure as code, autoscaling signals. The exclusion is explained by the single-node constraint and should stay out of core, but one optional block makes the archetype honest.
5. **Multi-tenancy and cost.** Tenant isolation in data and limits, cost per customer. Relevant to the product itself; fits as a D or capstone variant.
6. **Blob and file handling.** Uploads, streaming, checksums, storage layout. Minor.
7. **Code review of someone else's change.** T04 finds a missing assertion; reviewing a diff with a hidden regression is a different skill. Minor, cheap to add as a variant.

Over-weighted: the data district (VIII) is ten core missions on what is largely a fourth archetype, data engineering. W01 reconciliation, W02 incremental ingest, W03 backfills and W07 quality with atomic publish are backend-relevant; W04–W06, W09 and W10 are warehouse specialty. The model laboratory is already optional and should stay so.

### Recommendation on blocks and count

Keep the order of magnitude: about **ten core blocks of six to eight missions, around 70 core missions**, plus optional branches. The current 68 is not too many; it is slightly misallocated. Concretely:

- Move W04, W05, W06, W09 and W10 into an optional **data branch** next to the model laboratory. Core W keeps W01, W02, W03, W07, W08 (5).
- Add a core block **Integrations and resilience** between VI and VII with five missions: unreliable external API client; inbound webhooks with signatures and replay protection; outbound webhooks with idempotency keys and retry schedule; HTTP caching and conditional requests; time zones and scheduled work.
- Add an optional **platform branch** with three or four missions: declarative deployment on a local cluster, infrastructure as code for the lab stack, autoscaling signals and limits, cost per tenant.
- Add a multi-tenancy variant to the capstone (C02 or C04).

That gives ten core blocks, 68 core missions again, and three optional branches of 12, 6 and 3–4, roughly 90 authored missions.

### Repetition policy

Repetition in changed form is where most learning happens and the roadmap underinvests in it: six revisit rows against 86 missions. Two mechanisms, both already proposed elsewhere: the **hidden bonus check** on every mission, which is a second pass over the same mission with an edge case, and **authored variants**, the same capability in a new setting, two per core block, about twenty in total. Variants are cheaper than missions because they reuse the starter and verifier shape. A player who completes core missions plus variants plus bonus checks has met every core capability at least three times in different form; that is the coverage claim, not the mission count.

### What this review does not claim

Hours and pacing remain unmeasured, as the roadmap says. Coverage is judged against the reviewer's model of the professions, not against a job-market survey; the gaps list is a prior, and the pilot on real players should be allowed to reorder it.

## Review B — Kimi agent

Written independently before reading Review A; full text in [ROADMAP-REVIEW-B-KIMI-2026-10-08.md](ROADMAP-REVIEW-B-KIMI-2026-10-08.md) (Russian). Summary: the everyday work of the three archetypes is covered by nine blocks and about 55 missions (range 52–58): I, D, B, T, S, O in full, L01–L08, A01/A02/A05/A07, W01/W02/W04/W05 and the capstone. W06–W10 and M are specialization. The archetypes are connected, and the roadmap proves it constructively through the dependency graph rather than by declaration; the capstone certifies a full-lifecycle owner of a bounded system, which should be named as a choice. Main gap: reading and reviewing someone else's code, which appears once at beginner level and then only as a side effect of the repair format. Minor gaps: HTTP API versioning, time zones earlier than W01, cost as a constraint, "the skill of not building". Redundancy: A03 and A04 can merge into one Kafka lab; W09 is the first candidate for optional. The repetition spiral on idempotency and recovery is a strength, not duplication. Methodological caveat: the coverage claim is structural, against competency maps, not a measured share of real tickets.

## Reconciliation

**Agreed by both reviews.** The data district is a fourth archetype; its specialist half leaves the core. The model laboratory stays optional. The archetypes share one foundation and the roadmap already expresses it through dependencies; the game should say plainly that it trains someone who holds a small system end to end, with depth in any one role growing on the job. The idempotency and recovery spiral stays. Time zones and cost need explicit attention. Hours remain unmeasured and the coverage claim is structural, not a market measurement.

**Resolved differences.**

- Data district split: Review B keeps W04 and W05 in the core, since reporting and ETL shape are everyday backend work. Accepted. Core W is W01, W02, W04, W05; W03 and W06–W10 form the optional data branch.
- Code review: Review A listed it as minor, Review B as the main gap. Review B's argument stands, because reading unfamiliar code takes more than half of a working engineer's time. Add one mission "review a change with a hidden regression" and two variants at the B and O levels, for example "find the defect in an unfamiliar service from a symptom and its telemetry" as a revisit of O04 and O08.
- Kafka: merge A03 and A04 into one bounded lab. Accepted; the slot is reused.
- API versioning: a variant on B08 and T02, no new mission.

**Open difference, put to Review B in the channel.** Review A's largest gap, integrations with unreliable third parties (external API client, inbound and outbound webhooks, retries, circuit breaker, HTTP caching), does not appear in Review B. Nothing in the extraction makes the player the client of someone else's broken service, so Review A keeps the recommendation of a five-mission block unless Review B shows where the roadmap already covers it. Likewise the optional platform branch (local Kubernetes, infrastructure as code) for the DevOps archetype.

**Recommendation to the owner.**

- Ten core blocks: trunk I; D; B; T and S; O; L; the new integrations block; A with seven missions after the merge; core W with four; the capstone. About 66 core missions. The coverage claim is attached to the subset of about 55 that both reviews name, with the rest of the core as depth, and the full catalog as specialization on top.
- Optional branches: foundations 12, data 6, model laboratory 6, platform 3–4.
- Repetition: the hidden bonus check on every mission, now implemented, plus about twenty authored variants, two per core block, including the code review, API versioning and time zone variants named above.
- The one-trunk, three-guild device in `PROGRESSION-DESIGN.md` carries this structure into the game.

## Appendix — ambiguity audit of the ten runtime missions (subtask C2)

Read-only audit by a subagent on 2026-10-08 of briefs, lessons, generated LEARN.md, starters and verifiers. Findings not already in `MISSION-AUDIT-2026-10-06.md`, with the fix chosen for each. File references point at the state before the fixes.

**Cross-cutting**

- Lesson text introduces a concept no check requires in all ten missions. Six are disclaimed since 10-06. Undisclaimed: Echo's SQL interpolation warning (no quoted id is ever sent), Ledger's Decimal precision warning (largest total fits the default context), Contract's 8 KiB, no-proxy and no-sleep rules (unobservable), and roadmap codes D02, D03, F04, F05, F10 in Briefing and Capacity lessons that exist nowhere in the game. Fix: turn Echo and Ledger warnings into bonus checks, label Contract's rules as advice, remove roadmap codes.
- Unannounced strictness on return shapes: exact dict keys in Ledger and Recovery, `is True` / `is False` in Echo, type-strict comparison in Briefing. Fix: say it in the objectives.
- "Raise ValueError, not the natural exception" in Capacity for `10**400`, where `float()` raises OverflowError. Fix: name it in the lesson.
- Inter-mission inconsistency: extra JSON fields fail Signal but pass Gateway and the HTTP trial. Fix: Signal accepts extra fields, matching the others; contract version bump.
- Setup hooks invoked inside an open transaction (Vault) and `ingest` expected to create its own table on a fresh connection (Echo). Fix: the Vault verifier commits before calling setup; Echo's objective says ingest creates the table.
- Workspace text is frozen at first open (`server/labs.ts`, prepare returns early when the workspace exists), so every text correction reaches only new workspaces. The owner's Signal workspace still carries the old 503 wording. Follow-up, not fixed here: an explicit, backed-up document-refresh action, deferred in the 10-06 decisions.
- The check contract has no `optional` flag; a mission passes only when every check passes (`server/labs.ts`, `server/rewards.ts`). Precondition for subtask C3a.

**Per mission: hidden strictness or ambiguity → fix; proposed ★★★ bonus check**

1. Signal. Extra health fields rejected, `/health/` with trailing slash must be 404, 3 s timeout. Fix: accept extras, name the trailing slash and timeout in the objectives. Bonus: `Content-Length` equals the bytes written on both `/health` and the 404.
2. Vault. Setup called mid-transaction; `id` must be the sole primary key; `sqlite3.IntegrityError` specifically. Fix: verifier commits first; objectives name the sole key and the exception. Bonus: deleting a referenced item leaves no orphan movements, by restriction or cascade.
3. Gateway. Request line must be forwarded byte-identical; valid but unreloaded nginx config fails without a reload hint; `/api` without slash and bare `/api/` unspecified. Fix: objective states that only paths under `/api/` forward and the prefix is removed; check detail hints at reload when the config test passes but HTTP fails. Bonus: `/api/?probe=` lands on the relay as `/?probe=` and returns 404.
4. Echo. Bool identity, `ingest` creates its table, integral floats untested. Fix: objectives say "return exactly True or False" and "ingest creates the table if missing"; `7.0` added as a rejected quantity. Bonus: an id containing a quote and SQL is stored, replayed as duplicate, table intact.
5. Ledger. Exact two keys, int indices; same id and amount on a different date never tested. Fix: objective says "exactly these two keys"; lesson's precision warning softened. Bonus: the moved-day replay is rejected as a conflict.
6. Recovery. Full `sqlite_master` comparison fails on leftover helper tables; conflict wording reads as "versus existing rows". Fix: objective says "no new tables or indexes remain"; lesson says conflicts are within the archive. Bonus: two maximal quantities sum without SQLite integer overflow.
7. Briefing. Every requirement must cite a fact; a case kind must belong to every referenced requirement; returned manifests must not be mutated later; lesson cites roadmap codes. Fix: objectives name the three rules; codes removed. Bonus: a ticket with two questions, needs a new fixture.
8. Capacity. `10**400` must raise ValueError; roadmap code F10 in lesson. Fix: lesson names non-finite conversion as out of range; code removed. Bonus: junk values in ignored fields leave the seven outputs unchanged.
9. Contract. "Exact delivery fields" contradicts "tolerate extra fields"; byte-exact request targets and media type; UTF-8 body. Fix: wording "required fields with exact values, extra fields tolerated"; targets, media type and UTF-8 named; chunked and 413 paragraph trimmed. Bonus: a create body with `"quantity": 1.0` must fail create only, needs a fixture fault branch.
10. HTTP trial. Threaded server, Arabic-Indic digits, empty and nameless query pairs and parameter case unspecified. Fix: lesson names concurrency and that parameter names are case-sensitive. Bonus: empty pairs, a nameless pair and leading zeros handled on one request.
