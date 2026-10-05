# Six-mission contract audit — 2026-10-06

## Scope and result

Reviewed the story, objectives, field manuals, broken starters, executable validators and QA fixtures for all six existing missions. The changes remove demonstrated false rejections and false acceptances without adding missions, changing progression/types or supplying solutions in learner workspaces.

Implementation ownership is limited to:

- `shared/content.ts`: the six existing definitions only, including current UI objectives/lessons and diagnostic hints.
- `server/verify.py`; `server/labs.ts` **only** `checkGateway`.
- The six `labs/*/LEARN.md` files and one explanatory comment in `labs/signal/service.py`.
- `tests/labs.test.ts`, `tests/gateway.acceptance.ts`, three existing reference fixtures (`echo.py`, `ledger.py`, `recovery.py`) and three alternate fixtures (`echo-insert-first.py`, `ledger-decimal.py`, `recovery-transaction.py`).
- This audit record.

The other starters remain deliberately broken. `Labs.prepare`, workspace-copy behavior, UI, E2E files, session/curriculum documents and user saves were not modified. No dependencies were installed or removed. No editor, browser GUI, authorization or live tutor calls were initiated. No commit or push was made.

## Findings and implemented corrections

| Area | Demonstrated problem | Correction and evidence |
| --- | --- | --- |
| Python loader | Missing `sys.modules` registration rejects postponed dataclass annotations before mission checks run. | Register before execution and remove registration on import failure. A real temporary learner module with a dataclass and imported helper passes. |
| Signal teaching | Unconditional starter 503 can be mistaken for a required dependency outage. | Objectives, lesson, manual and starter comment explicitly identify it as the defect; only exact-path 200 and unknown-path 404 are required. Parsing remains the learner's choice. |
| Signal checks | Redirect-to-200 and a `text/plain` header containing `application/json` both previously passed 4/4. | Disable following redirects; parse the media type; exercise health-like unknown paths and query separation. Charset parameters, case-insensitive media type and different JSON key order pass. |
| Vault | Named-equivalent reordered columns failed 4 of 9 checks; TEMP tables passed 9/9 despite lacking persistence. | Named-column inserts, primary-key metadata, and a real commit/close/reconnect/setup cycle with multiple items and movements. Reordered table-level constraints pass; TEMP tables fail. |
| Echo | Application-only deduplication without the required PK and missing-field `KeyError` both passed 10/10. | Check the PK semantically; independently exercise malformed shapes, absent fields, wrong types and range boundaries. Invalid records must preserve existing events. Interleaved different ids and reconnect are checked. INSERT-first collision handling passes. |
| Ledger | Reversed rejected-index order failed despite reporting the correct rows; float arithmetic and permissive money spelling passed 5/5. The old Decimal reference also rounded sufficiently large amounts. | Compare unique rejected indices without imposing order, retain deterministic-repeat checks, declare an input range, and check lexical/date/identity boundaries and actual cent loss. The reference uses exact integer minor units. A separate Decimal implementation with another date parser and reversed rejection order passes. |
| Recovery | Upsert plus a separate empty-input clear passed 10/10 while preserving obsolete rows on nonempty replacement. Failure checks covered only one old row and quantity conflicts. | Check nonempty-to-different-nonempty replacement and empty replacement, PK, reordered existing columns, and late invalid records after two valid records. Compare old schema, named event rows and unrelated sentinel data after reconnect; check item and quantity conflicts. Prevalidation and rollback-transaction implementations both pass. |
| Gateway | Query preservation was required by log evidence but not stated explicitly; only the health route established prefix forwarding. | Publish query/log requirements; verify known and unknown forwarded paths with multi-parameter queries, unknown health-like paths, direct status and media type. Real nginx URI replacement and rewrite/named-upstream alternatives both pass. Lost-query and health-only configurations fail despite otherwise plausible HTTP responses. |

No checks compare Python source, SQL formatting, parser names, transaction spelling, numeric class or nginx configuration strings. The named entry points and required table/column identities remain integration interfaces. Primary-key checking uses SQLite metadata, not a CREATE TABLE text match.

## Boundary decisions

### Signal and Gateway

Signal's health JSON has the two specified keys/values; object key order and JSON whitespace are irrelevant. The 404 body is not graded. Health responses must be direct 200, not redirects. Media-type parameters are allowed.

Gateway uses the supplied Compose topology and unchanged relay/logging. Any working nginx routing approach is accepted. Removing `/api/` must preserve query parameters and forward unknown API paths as unknown paths, not silently replace them with health or synthesize them at nginx. The unique relay-log probes are published requirements, not secret implementation assumptions.

### Vault

The task remains a schema/persistence exercise over text identifiers and integer quantities, with explicit NULL name/item_id/quantity cases. NULL identifiers and non-integer quantities are outside its input scope. SQLite affinity and nullable ordinary TEXT PRIMARY KEY behavior are explained; stronger constraints are permitted but STRICT tables are not required. Setup is not a migration of a learner's old scratch database.

### Echo and Recovery

Required event fields are nonempty string `id`/`item` and a non-bool integer quantity in `1..9223372036854775807`. This limit is SQLite's signed INTEGER storage boundary, now visible rather than an accidental Python binding OverflowError. Extra fields are ignored. Identities are not trimmed or case-folded. Echo's caller owns the connection and commits before reconnecting; no particular commit-inside-function pattern is required.

Recovery accepts a list of events. Failed validation must preserve logical rows, schema and unrelated data in an existing database, not byte-identical SQLite files. Whole-archive prevalidation and validation within a rollback-capable transaction are both accepted. Success replaces the event set and reports its count/sum. Power failure, I/O exhaustion and concurrent recovery are outside this lab's evidence.

### Ledger

Inputs are lists of row dictionaries. Dates use ASCII digits in the two advertised exact formats and must be real calendar dates. Amounts use ASCII digits with an optional dot and one or two fractional digits. Leading zeros and zero are valid; signs, spaces, exponent notation, `.50`, `1.`, NaN and infinity are not.

Per-row amount range: **0 through 9999999999999999.99 inclusive**. Sixteen integral digits make cent loss observable with binary floating point while keeping a finite, explicit input domain. Daily totals are not capped at the per-row maximum. The integer reference remains exact without relying on ambient Decimal precision; the alternate Decimal fixture sizes a local context from the input count. Rejected indices are unique, zero-based and repeatable, in any deterministic order.

## Verification record

Environment: macOS arm64, Node **25.8.1**, Python **3.14.5**. Docker daemon was already accessible and reported **29.1.2**; the supplied nginx image served **1.28.3** during acceptance. Dates below use the local October 6 session; gateway timestamps are October 5 23:31 UTC.

| Command / run | Actual result |
| --- | --- |
| Pre-change `node --import tsx --test --test-concurrency=1 tests/labs.test.ts` | **10 passed, 0 failed**. This baseline did not establish alternate-solution correctness. |
| Pre-change read-only in-memory counterexamples | Reordered Vault **5/9**, reverse-order Ledger **3/5**, unregistered dataclass import raised AttributeError. Redirect/MIME Signal **4/4**, TEMP Vault **9/9**, missing-PK Echo/Recovery **10/10**, float/permissive Ledger **5/5**, incremental Recovery **10/10** falsely passed. These were controlled executable probes, not live model evaluations. |
| First implementation `node --import tsx --test --test-concurrency=1 tests/labs.test.ts` | **30 passed, 0 failed, 0 skipped**, approximately 5.29 seconds. Includes broken-starter failures, references, alternate solutions, targeted wrong candidates and preserved workspace documents. |
| `npm run typecheck` | **PASS, exit 0**, twice: after core changes and after extending gateway acceptance. |
| `npm run test:gateway` | **PASS, exit 0**. Seven real configurations: broken starter rejected; URI replacement **9/9**; rewrite + named upstream **9/9**; lost query, health-only forwarding, redirect and wrong media type rejected at their intended checks. |
| Final `node --import tsx --test --test-concurrency=1 tests/labs.test.ts tests/app.test.ts` | **35 passed, 0 failed, 0 skipped**, approximately 7.35 seconds. The five additional tests exercise the existing local API/reward/preservation and controlled provider/editor boundaries, without live external calls. |
| `git diff --check` | **PASS**. |

The gateway acceptance waits for a per-scenario response header before grading each reloaded configuration, so a verdict cannot accidentally describe the previous nginx workers. It uses a unique temporary Compose project and an ephemeral loopback port. Cleanup ran `compose down --volumes --remove-orphans` only for that project; subsequent `compose ps -a -q` was empty. Its temporary workspace was removed. No Docker context, daemon lifecycle or other project was changed, and shared images/dependencies were retained.

No automated implementation verification run failed. Expected red outcomes above are broken exercises or deliberately invalid candidates, retained as regression cases rather than weakened assertions. One atomic content patch was rejected because its final context omitted the adjacent `commands` text; it made no changes and was reapplied with correct context. No failing test attempt has been discarded from this record.

## Integration handoff and remaining limits

- Existing learner code, annotated manuals and generated MISSION.md are intentionally preserved. Reopening a workspace is tested not to overwrite them. The current objectives and lessons are in `shared/content.ts` for the parent-owned UI; an old saved manual may differ. Do not reset learner workspaces to deliver these corrections.
- The suite checks concrete behavioral boundaries, not all possible inputs or adversarial attempts to tamper with a trusted local verifier. It is not a security sandbox or a correctness proof.
- Gateway evidence depends on the supplied relay logs, the latest 100 log lines and an otherwise quiet local lab. It does not test arbitrary relay logging formats, concurrent high traffic, every URI normalization rule or production deployment security.
- Concurrent ingestion, crash durability, migrations, every malformed HTTP request, non-GET methods and arbitrary extra schema designs are not accepted competencies from this chapter. Vault checks currently expect its invalid insert to raise immediately; deferred-constraint timing has not been expanded or claimed here.
- Reference solutions remain QA-only under `tests/solutions`; field manuals/hints give investigation guidance, not full repaired programs. English coaching quality was not evaluated with a live model.
- Full build, whole-project test suite and headless UI/E2E acceptance are left to the parent integration run. The scoped checks above do not stand in for those results.

## Sources that informed the corrections

- Python 3.14 [direct-file import recipe](https://docs.python.org/3.14/library/importlib.html#importing-a-source-file-directly): register the module before executing it. Checked through Context7 during the audit.
- Python 3.14 [redirect handler](https://docs.python.org/3.14/library/urllib.request.html#httpredirecthandler-objects) and [media-type parser](https://docs.python.org/3.14/library/email.message.html#email.message.EmailMessage.get_content_type): do not mistake a followed response or header substring for the declared contract.
- SQLite [type affinity](https://www.sqlite.org/datatype3.html) and [PRIMARY KEY caveats](https://www.sqlite.org/quirks.html#primary_keys_can_sometimes_contain_nulls): declared types alone do not provide the stronger invariants a learner might infer. Context7 coverage was supplemented by official documentation.
- Python 3.14 [Decimal](https://docs.python.org/3.14/library/decimal.html): exact construction does not remove arithmetic context rounding.
- nginx [proxy_pass](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_pass): URI replacement and rewritten URI forwarding are both valid; Context7 documentation was followed by the real supplied-image acceptance above.
