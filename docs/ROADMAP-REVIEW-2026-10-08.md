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

Pending in the `rankforge` channel.

## Reconciliation

Pending both reviews.

## Appendix — ambiguity audit of the ten runtime missions (subtask C2)

Pending.
