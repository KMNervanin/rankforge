# D01–D03 authoring acceptance — 2026-10-06

**Integrated release:** registered in the real app on October6. Production build,152/152 full Node tests and9/9 headless browser scenarios passed on macOS; Linuxarm64Node24.21.0/Python3.11.2 built and passed the same152tests. Actual API/browser starterFAIL→savedrepair→PASS exercised all three guild labs, with preserved work and idempotent awards. The source/type/registration gaps described in the historical worker handoff below are closed. Deeper architecture review and live tutor effectiveness remain outside these claims.

Scope: new files only, based on `main` at `82c07d1` after the UI/audit/roadmap commits. This is the standalone guild block handoff. Registration, chapter UI, API/browser/store acceptance and quota behavior belong to the parent integration. No commit or push was made by this worker.

## Entry points and integration

| Mission | Metadata | Learner entry point | Runtime prerequisite |
| --- | --- | --- | --- |
| D01 `briefing` | `chapter: 'guild'`, order 7 | `manifest.py: build_manifest(ticket)` | `recovery` |
| D02 `capacity` | `chapter: 'guild'`, order 8 | `capacity.py: estimate(workload)` | `briefing` |
| D03 `contract` | `chapter: 'guild'`, order 9 | `probe.py: probe(base_url, scenario)` | `briefing` |

`shared/architect.ts` exports `architectMissions: Mission[]` and `architectFollowUps: Record<string, string[]>`. All mission text, manuals and code are English. Each `labs/<id>/` is independently copyable and includes a starter, field manual and working terminal demo. Reference solutions exist only in `tests/solutions/architect/`; the verifier never imports them and the labs/tutor material contain no probe or calculator solution.

Parent integration steps:

1. Add the required `Mission.chapter: 'outpost' | 'guild'`; label the original six missions `outpost`. Concatenate `architectMissions` and merge `architectFollowUps` in the existing content registry. Keep orders 7/8/9 and the independent D02/D03 prerequisite branches.
2. Route only these three IDs to `server/verify_architect.py`. Preserve owned-workspace validation and add `manifest.py`, `capacity.py`, `probe.py` to entry-file/symlink/context handling as appropriate. Preparation must use the existing copy-on-first-use behavior, not replace an existing workspace or its documents.
3. Execute `python3 -I -B <repo>/server/verify_architect.py <mission> <workspace>` with the existing `run()` helper and its 45-second outer timeout. The verifier has a 30-second internal deadline. Its **last stdout line** is always `{ "checks": [{ "name", "passed", "detail" }] }` for normal completion, import failure and its internal deadline. Exit status is 0 only when all checks pass. Candidate prints go to stderr. OS termination/output-limit handling remains the parent's runner responsibility.
4. A fixture-bind failure produces failed checks named exactly `Environment blocked`; map that to `supported: false`/setup guidance rather than a learner assertion failure. The normal `HTTP probe distinguishes unavailable` check is different: it passes when the probe correctly classifies the deliberately disconnected fixture.
5. Use this block's technical outcomes without making optional prose/debrief an additional gate. Complete the actual prepare → starter FAIL → saved repair → PASS → return/reload flow, one-time rewards and pending-message/quota checks in parent API/headless browser integration. Update implemented chapter/roadmap counts there.

At the original handoff, `npm run typecheck` failed on exactly **four expected integration errors** because the parent had not yet declared `Mission.chapter`. The parent has since added it; those errors are absent in the 04:36 MSK follow-up. That fresh typecheck still reports **12 errors outside this worker's ownership** in concurrent progression/http-trial work (`server/rewards.ts`, `server/store.ts`, `shared/http-trial.ts`, `tests/progression.test.ts`: missing `contractVersion`/`progression`/`bonus` and dependent implicit-any parameters). No guild-file error was reported, and no parent file was edited to address that snapshot. Build and E2E release acceptance remain with parent integration.

## Published contracts and observable checks

### D01 — structured requirements, not automatic architecture certification

The source of truth is `ticket.json` plus visible changed `ticket-v2.json` and `ticket-v3.json`. Schema v1 is fixed; ticket revision is separate. Revision 2 lowers quantity/latency limits; revision 3 changes the actor, payload and excluded scope. A fourth scenario changes identity/limit/order, followed by the original again. The validator reads canonical repository tickets, not a learner-edited copy.

`build_manifest` is a thin evaluation interface for the primary artifact: requirement facts and observable-case links, assumptions, open questions and exclusions. The algorithm is not being certified as a requirements engineer. The checker verifies exact typed fact values/units, complete coverage, valid references, allowed case categories and preservation of old returned artifacts. Grouped or separate requirements, manual or automatic dispatch, and explicitly unresolved dispatch all pass. Exclusions stay out of the promised scope; they do not create extra implementation obligations. Description/rationale wording is review-only and may be omitted.

Requirement-to-case mapping: actor → authorized/unauthorized; operation → success; payload → success/missing_field; quantity → boundary/over_limit; persistence → restart; latency target → measurement; chosen dispatch → the option's published observation. These are **plans for observations**, not evidence that authorization, persistence or latency were implemented or measured.

### D02 — independent dimensional arithmetic

`LEARN.md` publishes seven input bounds, seven outputs and all equations. Rates use 86,400 seconds/day; mean residence time includes queueing, is converted from milliseconds and is never replaced by p95. Fractional in-flight averages are retained. Storage uses average daily writes and a combined multiplier, not peak rate for the entire day. Decimal MB/s and binary GiB are explicit; MiB is explained but not requested. Zero/max values and integer-valued floating retention are allowed as documented.

The oracle computes direct dimensional products with `Fraction`, independently of candidate intermediate results. Float, Fraction and Decimal implementations pass; tolerance is max(1e-9 absolute, 1e-9 relative). Invalid inputs require ValueError, including each missing field, bool/string/null, nonfinite numbers, enormous integers, bounds, fractional days and invalid fields despite zero traffic. Inputs remain intact on both success and error. Extra metadata and optional p95 are ignored. The supplied workload identifies equivalent briefing context; no previous learner artifact is imported automatically.

### D03 — real consumer HTTP observations

The canonical `labs/contract/fixtures.py` is loaded outside the copied workspace and serves real HTTP on `127.0.0.1:0`. Two conforming implementations use imperative routing versus a dispatch table, compact versus sorted/indented JSON, different header casing/media parameters, and optional response fields. The probe must accept both, including repeated fresh fixtures and boundary/Unicode payloads.

| Public observation | Independently observed effect / impostor |
| --- | --- |
| create/replay/conflict | Actual three POST bodies in order, JSON request media type, 201/200/409 with exact typed required response fields |
| read/query | Two actual GETs, preserved original record, distinct full/summary `view`; query-insensitive fixture fails |
| missing | Actual unknown child-path request; success-on-unknown or wrong error body fails |
| effects | Actual GET /stats and fixture state; duplicate replay and conflicting-write effects are exposed |
| Every response | Status, X-Contract, media type, body and JSON corruption are injected independently at every check position |
| Transport | Held response until Event release → timeout; accepted request with EOF before any HTTP response → unavailable |

HTTP 500 and redirect fixtures must yield assertion failure, not transport unavailability. Strict source-string JSON comparison fails against conforming variants; Boolean quantity is tested specifically when the requested quantity is 1. The outer verifier compares named verdicts to the fixture's deliberate fault, observes the complete request trace and checks good-fixture state. Canned/always-pass reports and hidden extra requests do not pass. D03 demonstrates one consumer contract; it is not an authorization, durable database, concurrency, crash-recovery or production-load proof.

## Actual verification evidence

Environment: macOS Darwin **25.6.0 arm64**, Node **v25.8.1**; Python **3.14.5** and separately installed Python **3.11.7 arm64**. No new dependencies or downloads. Python >=3.10 is the authored minimum; Python 3.10 runtime and Linux have **not** been executed in this worker's scope.

Reproducible focused commands from repository root:

```sh
node --import tsx --test --test-concurrency=1 tests/architect.test.ts
RANKFORGE_TEST_PYTHON=/usr/local/bin/python3.11 node --import tsx --test --test-concurrency=1 tests/architect.test.ts
npm run typecheck
```

The second command documents this machine's installed interpreter; substitute an installed Python >=3.10 elsewhere. Tests call the existing real `run()` helper on copied temporary workspaces, not `Labs` registration or a simulated model. No GUI, authorization, model calls, external network, daemon-owned service, user save or existing workspace is used.

Observed run sequence on 2026-10-06:

- Baseline before edits: existing **56/56 Node tests PASS** (`npm test`).
- First focused run: **39 tests, 36 pass, 3 fail**. Both correct HTTP probes and the demo failed only the unavailable fixture because this machine timed out on a bound/non-listening port. That was an authoring defect, not a learner failure; see decisions below.
- After controlled disconnect and expanded assertions: **41/41 PASS**.
- Expanded block: **45/45 PASS**, 0 failures/skips, Python 3.14.5. Node runner 19.898 s, `/usr/bin/time -l` wall 19.96 s; reported maximum resident set size 87,769,088 bytes for that test command. These are measurements, not universal performance thresholds.
- Same **45/45 PASS**, 0 failures/skips on Python 3.11.7, runner 19.324 s. This run also covers the final workload provenance metadata and configurable test interpreter.
- The initial authoring review added observation of unsupported HTTP methods and required all unattempted checks to fail after first-request transport failure. That version had **46/46 PASS** on each interpreter, 0 failures/skips: **22.325 s** on Python 3.14.5 and **21.563 s** on Python 3.11.7. These suites ran concurrently using separate temporary workspaces/ports. This was the pre-cold-review candidate, not the final follow-up below.
- All **14 new Python files** passed Python-3.10-grammar `ast.parse(feature_version=(3,10))` and current-runtime `compile()` in memory, with no `.pyc` output. Grammar compatibility is not a Python 3.10 execution claim.
- Before cold review each accepted implementation produced **5 D01**, **92 D02**, or **52 D03** outer checks. D03's 52 checks comprised six conforming runs, 44 faulty response/effect scenarios, timeout and unavailable. Follow-up counts are **5 / 94 / 88**; see the evidence below.
- Three shipped starters return nonzero and failed behavioral checks. Two materially different solutions per lab pass; an additional Decimal/helper/dataclass capacity wrapper and explicitly open-question manifest pass. Static tickets, lost facts/cases/exclusions, invented assumptions, wrong units, stale/shared artifacts, arithmetic mistakes, malformed-input shortcuts, status-only probes, MIME substrings, ignored duplicate effects, exact serialization, wrong transport classifications and scenario mutation are rejected.
- Every candidate run snapshots the entire copied workspace before/after; no edits, deletions or `__pycache__` appeared. Unrelated notes survive. Isolated helper imports and postponed-annotation dataclasses pass. Syntax/import failures and an accelerated internal-deadline test return failed final JSON. The latter triggers the real signal handler at 0.05 seconds rather than spending 30 seconds in a deliberate infinite loop.
- Every documented demo command was executed on copied workspaces, including all three public tickets and both conforming/duplicate/timeout/unavailable HTTP modes, under stricter `-I -B` flags.

Reference solutions are author-written acceptance controls, not independent human learner attempts. A read-through by a new learner, pedagogical pacing/clarity, tutor quality and live assessment have not been established. Fresh inputs and mutants provide bounded transfer evidence, not an exhaustive proof against adversarial learner code.

### Cold independent review follow-up — validation snapshot 04:36 MSK

The parent reported four proven P2 gaps. All four were reproduced **before** editing the verifier/fixture on both Python 3.14.5 and 3.11.7. The new regression command returned **4 tests / 0 pass / 4 fail** on each interpreter (4.072 s / 4.055 s):

| Counterexample | Actual pre-patch result | Why the regression was RED |
| --- | --- | --- |
| Probe ignores `id` and `item` | **52/52 pass**, exit 0 | Existing body faults did not exercise these required fields |
| Calculator truncates both byte averages with `int(...)` | **92/92 pass**, exit 0 | All valid byte inputs were integers |
| Correct iterable UTF-8 / automatically chunked client | **0/52 pass**, exit 1; first response classified `unavailable` / ConnectionResetError | Fixture read Content-Length only and closed the valid request instead of decoding chunks |
| Probe always uses 1.0 s instead of `timeout_s` | **52/52 pass**, exit 0 | The checker verified only eventual timeout, not the configured budget |

The old statement that the published bounded contract had been adequately checked was too strong. These were validator/fixture omissions; the correct alternatives and old green counts did not establish coverage of those dimensions.

Narrow fixes and evidence:

- **Response fields:** 32 added cases independently replace with a wrong same-typed value and omit every required field at every applicable response: create 3, replay 3, conflict 1, read 4, query 3, missing 1, effects 1. State is not mutated by these response faults. The identity-blind probe now passes **74/88**, fails all 14 relevant field cases, and exits nonzero. Separate missing-default and type-only mutants are rejected for **all 16 fields** under the respective missing/wrong cases. Conforming optional fields remain accepted by both clients.
- **Fractional bytes:** two deterministic cases vary `response_bytes=0.5` and `written_bytes=0.5` independently, with nonzero expected bandwidth/storage; fresh byte averages also vary by eighths. The truncating mutant now fails both named deterministic checks and the relevant fresh cases. Final runs observed **86/94 pass**, exit nonzero, on both interpreters; an earlier intermediate run had **88/94** because fresh inputs vary. The oracle remains an independent Fraction dimensional calculation. Float/Fraction/Decimal alternatives still pass **94/94**.
- **Chunked framing:** decode bounded hexadecimal sizes, CRLF, final zero chunk and optional trailers; ignore extensions and do not merge trailers into headers. The decoded payload remains capped at 4,096 bytes, matching Content-Length. Metadata is capped at 4,096 bytes/line and 65,536 bytes total; incomplete/ambiguous/malformed framing returns 400, over-limit framing 413, with no delivery effect. The valid iterable client now passes **88/88**. An additional **22 actual HTTP cases** across both fixture styles cover UTF-8 split into single-byte chunks, extensions/trailers, exact payload boundaries, aggregate/single-chunk overflow, malformed/truncated frames and ambiguous framing; effects are inspected directly.
- **Timeout budgets:** ordinary scenarios vary 0.2/0.6/1.0 s; four new controlled reply gates exercise create and effects before/after a deadline. A 0.55 s gate with a 1.0 s budget must pass; a 0.8 s gate with a 0.2 s budget must time out. Timing starts at the received request, not interpreter startup. Failed/remaining check names are derived from actual traffic, preserving the permitted alternate GET order. The fixed-1.0 s mutant now passes **86/88** and exits nonzero; fixed-0.3 s fails both before-deadline cases. A further mutant labels a late response as `timeout` but is rejected by the **0.2 + 0.5 = 0.7 s physical return envelope**: final observations were **0.804/0.801 s** (3.14) and **0.800/0.801 s** (3.11), each explicitly reported as `Return budget exceeded`.

No correctness startup sleeps were added. Request-arrival, release and cancellation Events drive the delayed fixtures. A controller interval/unobserved scheduling gap >0.25 s or an in-budget release later than 0.8 s is `Environment blocked`, not PASS or a learner assertion verdict. The generous 0.5 s tolerance deliberately does not prove millisecond-accurate socket configuration or every connect/send/read operation. Large scheduling pauses can require a retry; hostile code is not sandboxed. The physical cases demonstrate both premature timeout and an ignored/late timeout at the published separation, rather than claiming a universal exact timing test.

Run history after the initial four REDs:

1. First patched regression run on 3.14: **4/4 PASS** (11.781 s); no intermediate patched failure.
2. Expanded P2 group: **8/8 PASS** on 3.14 (25.723 s) and **8/8 PASS** on 3.11 (26.465 s), including field coverage, short/late timeout mutants and 22 framing exchanges.
3. Final full **focused guild file only**: **54/54 PASS**, 0 fail/skip, on **Python 3.14.5 in 90.167 s** and **Python 3.11.7 in 90.217 s**. The two suites ran concurrently with isolated workspaces/ports. Both original correct HTTP clients, the iterable client, the arithmetic/manifest alternatives and every old control pass. Snapshot checks confirm unchanged copied learner files and no pycache. Both new delay demos run under `-I -B`.
4. Refreshed all **14 Python source** grammar/compile checks: Python-3.10 grammar and Python-3.14 in-memory compilation PASS. Actual Python 3.10/Linux execution is still absent.

Reproduce just the review controls with:

```sh
node --import tsx --test --test-concurrency=1 --test-name-pattern='P2 review' tests/architect.test.ts
RANKFORGE_TEST_PYTHON=/usr/local/bin/python3.11 node --import tsx --test --test-concurrency=1 --test-name-pattern='P2 review' tests/architect.test.ts
```

The follow-up edited only `server/verify_architect.py`, `labs/contract/{fixtures.py,demo.py,LEARN.md}`, `labs/capacity/LEARN.md`, `tests/architect.test.ts`, and this acceptance document. No parent source/type/registry/store/API/UI file or reference solution was changed. No full npm suite, build/E2E, commit/push, GUI, provider request, private data or owner preview on port 4173 was used.

## Measured resource profile

Measured inside separate successful Python verifiers with `resource.getrusage(RUSAGE_SELF)`; seconds cover `runpy` execution, excluding interpreter spawn. Workspace byte counts are sum of file content lengths for the copied lab with the named test solution and a 27-byte sentinel note, not filesystem allocated blocks. No interpreter/dependency footprint is included in disk totals.

### Pre-cold-review measurements (retained history)

| Lab | Checks | Python 3.11.7 elapsed | Peak RSS | Copied workspace bytes |
| --- | ---: | ---: | ---: | ---: |
| briefing / grouped | 5 | 0.0119 s | 20,480,000 B | 9,947 B |
| capacity / Fraction | 92 | 0.0120 s | 20,103,168 B | 6,878 B |
| contract / http.client | 52 | 1.0333 s | 28,196,864 B | 18,781 B |

Pre-review Python 3.14.5 measured 0.0116 / 0.0124 / 1.0836 s and 20,480,000 / 20,414,464 / 28,196,864 B respectively. Both profiles ended with **one thread**: every owned HTTP thread was joined. These measurements include the expanded request-attempt trace; the two earlier 45-test profiles preceded that change.

### Final follow-up measurements

| Lab | Checks | Python 3.11.7 elapsed | Peak RSS | Copied workspace bytes |
| --- | ---: | ---: | ---: | ---: |
| briefing / grouped | 5 | 0.0121 s | 20,725,760 B | 9,947 B |
| capacity / Fraction | 94 | 0.0129 s | 20,398,080 B | 7,123 B |
| contract / http.client | 88 | 3.3683 s | 28,164,096 B | 26,218 B |

Final Python 3.14.5 measured **0.0119 / 0.0140 / 3.3358 s**, peak RSS **20,594,688 / 20,709,376 / 28,688,384 B**, with the same workspace sizes. Both final profiles again ended with **one thread**, proving joined owned HTTP/controller threads for these runs. Durations now include four controlled delay cases and variable stalled-case timeout; they are observations, not performance requirements.

Each Verify uses one Python worker. D01/D02 use no sockets and no extra threads. D03 uses one server thread and ephemeral listener at a time; its four timed fixtures also use one cancellation-aware controller thread. No daemon is spawned. Before review, D03 observed **352 requests across 52 fixtures**. The final **88 fixtures** comprise six conforming, 76 faulty, two transport and four budget cases. With the reference http.client GET order they produce **598 actual requests**; with the alternate urllib order, **595** (a later timed-out effects check stops before its remaining GETs). These counts follow the exact accepted request traces: 82 ordinary fixtures ×7 +2 transport +14 in-budget +1 expired-create +4..7 expired-effects. The separate framing test adds 22 exchanges to the test suite, not to learner Verify.

`serve_forever`'s 0.01-second poll is only shutdown responsiveness; the controller uses cancellable Event waits and records scheduling gaps. Responses remain <=4 KiB and client reads <=8 KiB. Both framing forms cap decoded input at 4 KiB; chunk metadata has its own 64 KiB aggregate/4 KiB line limits. Nominal state is one tiny record per fixture, including deliberately broken counters. Download size is zero beyond already-installed runtimes. No Docker, database service, GPU or paid service is required.

The deadline/request contract is not an OS sandbox or a hard memory/network containment boundary for malicious Python. Neither static analysis nor runtime introspection claims to prove that arbitrary code uses no extra files/network. Tests verify file preservation and actual fixture traffic for the authored candidates, with the existing runner containing process lifetime/output. No new dependency/build artifacts were created; test temporary directories are cleaned, and pre-existing dependencies/builds are left for the parent.

## Decisions and failure history

### Artifact boundary
Chosen: a thin `build_manifest(ticket)` producing the manifest, with optional prose outside grading.
Reason: executable revisions expose stale facts while keeping feasibility/architecture critique explicitly formative.
Reversal: add an interactive manifest editor later without changing the fact/case schema.
Code: `labs/briefing/`, `server/verify_architect.py`.

### Unavailable versus timeout
Chosen: accept an owned connection and close before the HTTP response; hold a separate timeout fixture behind an Event.
Reason: first-run evidence showed bound/non-listening ports timing out here. The specific network/VPN cause was not established, and VPN was not changed. EOF is a published unavailable outcome and removes the OS-dependent assumption and port-rebind race.
Reversal: add a separate refused-connection environment probe if cross-platform evidence supports it; do not relabel a timeout as unavailable.
Code: `labs/contract/fixtures.py: unavailable`, `WireHandler.do_POST`.

### Equivalent prerequisite context
Chosen: supplied, versioned tickets/workload/HTTP contract in each copied lab; no implicit import of an old workspace.
Reason: D02 and D03 can be practiced independently after D01 without silently migrating learner artifacts or trusting stale manifests.
Reversal: parent may add an explicit validated import/checkpoint workflow later; current fixtures remain a documented equivalent.
Code: field manuals and public data files.

### Strictness and proof scope
Chosen: grade the public schema/equations and exact typed HTTP contract; allow decomposition, wording, Decimal/Fraction/float, response formatting, optional fields and GET observation order.
Reason: source spelling and architecture taste are not evidence of correctness. Each rejected impostor violates an observable published rule.
Reversal: version the relevant public contract alongside its verifier if scope changes.
Code: all three validators and the negative-control tests.

## Documentation consulted

Context7 `/websites/python_3_10` resolved and queried before implementation for HTTPConnection request/body/timeout/response semantics and importlib/isolated-mode loading; queried again for urllib HTTPError versus URLError and proxy/redirect configuration. Official Python 3.10.22 documentation read for [http.client](https://docs.python.org/3.10/library/http.client.html) and [socketserver](https://docs.python.org/3.10/library/socketserver.html).

The docs determine three implementation details: insert dynamically loaded modules into `sys.modules` **before** execution (dataclasses/helpers); explicitly inspect HTTP error responses instead of conflating them with transport exceptions; run server shutdown from a different thread and use documented `RemoteDisconnected`/EOF for controlled unavailability. http.client body strings default to Latin-1, so the Unicode acceptance control sends explicit UTF-8 bytes. These sources support API behavior; the actual focused tests establish this block's observed results.

Before the review fixes, Context7 was queried again for automatic chunking of iterable bodies, HTTPConnection blocking-operation timeout semantics, and threading.Event/Timer/join behavior. [RFC 9112 §7.1](https://www.rfc-editor.org/rfc/rfc9112.html#section-7.1) was read for hexadecimal chunk sizes, CRLF, the final zero chunk, extensions/trailers and bounded parsing. This confirmed that a valid standard-library iterable client must not be rejected merely for lacking Content-Length, and that timing gates must observe real events rather than assume Timer scheduling is exact. The fixture decoder is bounded test infrastructure, not a claim of a complete production HTTP parser.

## Remaining release work

Parent type/registry/verifier routing and chapter UX, real API/headless browser acceptance, optional post-brief/award/quota preservation, and final build/full-suite/E2E remain separate gates. Linux and Python 3.10 runtime evidence are absent. No claim of a production-ready course, validated teaching effectiveness, architecture mastery or live tutor quality follows from this standalone acceptance.
