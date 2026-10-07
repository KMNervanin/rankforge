import type { Mission } from './types.js'
import { architectMissions, architectFollowUps } from './architect.js'
import { httpTrialMission } from './http-trial.js'

export const chapters = [
  { id: 'outpost', number: 'I', title: 'The silent outpost', place: 'THE FLOATING OUTPOST', heading: 'A world worth restoring.', description: 'Every system you repair becomes a skill you carry.' },
  { id: 'guild', number: 'II', title: "The architect’s guild", place: 'THE ARCHITECT’S GUILD', heading: 'Think before you build.', description: 'Trace the promises, estimate the work, then test the boundary.' },
] as const

export const missions: Mission[] = [
  {
    id: 'signal', chapter: 'outpost', order: 1, title: 'A signal in the dark', subtitle: 'Bring the command relay online', sector: 'Command relay', icon: '◈',
    skills: ['HTTP contracts', 'Diagnostics', 'Python foundations'], prerequisites: [], xp: 120, duration: '20–35 min', kind: 'repair',
    briefs: {
      guided: 'The outpost cannot hear the relay. Its health check is broken. Fix the HTTP response and test it.',
      connected: 'The command relay is running, but the outpost marks it offline. Investigate its HTTP contract, repair the health check, and explain your evidence.',
      independent: 'Restore the relay’s published health contract. Demonstrate correct success and unknown-route behavior, then brief the operator on your diagnosis.',
    },
    objectives: ['GET /health returns 200 directly, without a redirect, and a JSON object containing "status":"ok" and "service":"relay". Extra JSON fields, key order and whitespace do not matter.', 'The health response uses application/json; parameters such as charset=utf-8 are allowed.', 'Match the path exactly: every other path returns 404, including /health/ with a trailing slash, /healthcheck and /health/extra. Query parameters do not change routing. Each response must arrive within 3 seconds.', 'Keep service.py and its importable Handler entry point. The unconditional starter 503 is the defect, not a required dependency-failure scenario.'],
    languageGoal: 'Describe a problem, an action and observable evidence.', prompt: 'What was wrong with the relay? What did you change, and how did you check it?',
    hints: ['Read Handler.do_GET in service.py. The process being alive is not the same as the HTTP contract being correct.', 'Separate the URL path from its query before deciding which route was requested.', 'Trace the status, headers and body for known and unknown paths. Which operation finishes headers before body bytes are written?'],
    sources: [{ title: 'Python HTTP server', url: 'https://docs.python.org/3/library/http.server.html' }, { title: 'HTTP status codes', url: 'https://developer.mozilla.org/en-US/docs/Web/HTTP/Status' }],
    commands: ['python3 service.py', 'curl -i http://127.0.0.1:45101/health', 'curl -i http://127.0.0.1:45101/missing'],
    lesson: 'Inspect status, content type and body before and after editing. The starter always returns 503 on purpose: there is no unavailable dependency to detect. The required outcomes are 200 for the exact /health path and 404 elsewhere, including /health/ with a trailing slash, regardless of query parameters. Only the two required JSON keys are compared; extra fields are allowed. Choose your own parsing and response construction. Verify uses a fresh temporary server, not your terminal process. Existing workspace documents are preserved; these objectives are the current contract.',
    artifact: 'Relay health probe',
  },
  {
    id: 'vault', chapter: 'outpost', order: 2, title: 'Give memory a structure', subtitle: 'Protect the supply vault', sector: 'Memory vault', icon: '▤',
    skills: ['Relational modeling', 'Constraints', 'Transactions'], prerequisites: ['signal'], xp: 160, duration: '30–45 min', kind: 'build',
    briefs: {
      guided: 'The vault loses track of supplies. Create two linked tables. The database must reject invalid records.',
      connected: 'Design storage for supply items and movements. Put data integrity in the schema, and prove that invalid movements cannot enter the vault.',
      independent: 'Establish a relational integrity boundary for inventory movements. Justify your keys and constraints and demonstrate persistence across independent connections.',
    },
    objectives: ['create_schema(connection) creates persistent items(id TEXT PRIMARY KEY, name TEXT NOT NULL) and movements(id TEXT PRIMARY KEY, item_id TEXT NOT NULL, quantity INTEGER NOT NULL). In each table id is the only primary key column. Column order and SQL formatting are your choice.', 'movements.item_id references items.id; quantity must be positive. Foreign key enforcement is enabled on every verifier connection.', 'SQLite rejects duplicate identifiers, NULL names/item_id/quantity, unknown items and zero or negative quantities by raising sqlite3.IntegrityError on INSERT or COMMIT. Other test inputs use text identifiers and integer quantities.', 'Repeated setup preserves all data, including after the caller commits, closes and reconnects. Verify commits its own writes before calling setup again. Setup is not a migration of an old permissive scratch schema.'],
    languageGoal: 'Explain a design choice and what it prevents.', prompt: 'Why did you choose these constraints? Give one example of data the vault now rejects.',
    hints: ['Put integrity at the database boundary, not only in a Python client. Foreign key enforcement is enabled on each test connection.', 'Look up primary keys, foreign keys and value constraints. How will setup behave when a table already exists?', 'Record two items and several movements, commit and reconnect. Does running setup again preserve every record?'],
    sources: [{ title: 'SQLite constraints', url: 'https://www.sqlite.org/lang_createtable.html' }, { title: 'Foreign keys', url: 'https://www.sqlite.org/foreignkeys.html' }],
    commands: ['python3 inspect_vault.py'],
    lesson: 'A schema protects data written by different clients. This lab requires persistent tables and repeatable setup, not a particular column order or SQL spelling. SQLite foreign keys must be enabled per connection. Ordinary TEXT PRIMARY KEY permits NULL and INTEGER is an affinity, not strict type validation. NULL identifiers and non-integer quantities are outside this lab’s input scope; stronger constraints are welcome. Use a new scratch filename when changing a schema. Existing workspace documents are preserved; use these current objectives.', artifact: 'Integrity seal',
  },
  {
    id: 'gateway', chapter: 'outpost', order: 3, title: 'Open the right gate', subtitle: 'Route traffic through nginx', sector: 'Transit gate', icon: '⌘',
    skills: ['Reverse proxy', 'nginx', 'Container networking'], prerequisites: ['signal'], xp: 200, duration: '35–50 min', kind: 'repair',
    briefs: {
      guided: 'Two containers are ready. nginx is the front door. Make /api/health reach the relay. Keep unknown routes closed.',
      connected: 'The relay works inside its container, but the gateway sends traffic to the wrong place. Repair nginx routing and verify the response from outside the gateway.',
      independent: 'Restore the gateway boundary between the published endpoint and its private upstream. Account for container DNS and URI rewriting; demonstrate both permitted and unknown routes.',
    },
    objectives: ['Use the supplied Compose project, keep the relay unchanged, and start it from the terminal. Publish gateway port 8080 on host loopback; the host port may vary.', 'GET /api/health returns 200 directly, application/json and the relay JSON. Media-type parameters and JSON formatting may vary.', 'Only paths under /api/ are forwarded to the relay. Remove the /api/ prefix and pass the rest of the path and the query through unchanged, byte for byte. Verify checks the supplied relay log for a unique request.', 'Unknown paths inside and outside /api/ return 404, with or without a query. Validate the nginx configuration and reload nginx before Verify: a valid but unreloaded config still fails the HTTP checks.'],
    languageGoal: 'Ask for clarification and explain a request path.', prompt: 'Describe how a request reaches the relay. Why does localhost not point to the other container?',
    hints: ['Inside the nginx container, localhost means nginx’s own container. Compose provides DNS using service names.', 'The upstream is relay:8000. Compare URI replacement with a rewrite followed by proxying.', 'Predict the upstream path and query for known and unknown /api/ routes, then compare with the relay log. A syntax check alone cannot prove routing.'],
    sources: [{ title: 'nginx proxy_pass', url: 'https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_pass' }, { title: 'Compose networking', url: 'https://docs.docker.com/compose/how-tos/networking/' }],
    commands: ['docker compose up -d', 'docker compose exec gateway nginx -t', 'docker compose exec gateway nginx -s reload', 'docker compose port gateway 8080', 'curl -i http://127.0.0.1:45103/api/health', 'docker compose down'],
    lesson: 'A reverse proxy forwards requests across separate container network namespaces. Compose names provide internal DNS. Preserve the query while removing the /api/ path prefix; unknown API paths must reach the relay as unknown paths. URI replacement, explicit rewrites and named upstreams can satisfy the same contract. Keep the supplied relay and logging unchanged so Verify can prove forwarding. No particular nginx configuration text is required. Existing workspace documents are preserved; use these current objectives.', artifact: 'Gateway route map',
  },
  {
    id: 'echo', chapter: 'outpost', order: 4, title: 'An echo is not an event', subtitle: 'Make retries safe', sector: 'Event conduit', icon: '⇄',
    skills: ['Idempotency', 'Transactions', 'Event identity'], prerequisites: ['vault'], xp: 220, duration: '30–45 min', kind: 'repair',
    briefs: {
      guided: 'A sender retries after a timeout. The same delivery is counted twice. Store each event once, but reject a reused ID with different data.',
      connected: 'Retries are inflating the supply ledger. Implement repeat-safe event ingestion, distinguishing an exact replay from a conflicting event identity.',
      independent: 'Establish durable idempotency at the ingestion boundary. Preserve exactly one effect for repeated delivery and reject identity collisions without corrupting existing state.',
    },
    objectives: ['ingest(connection, event) stores persistent events(id TEXT PRIMARY KEY, item TEXT, quantity INTEGER) and creates that table if it does not exist; Verify supplies fresh connections without a schema. Physical column order is not part of the contract.', 'An event is a dictionary with nonempty string id/item and an int quantity from 1 to 9223372036854775807 (SQLite INTEGER range). bool and floats such as 7.0 are not integers here. Extra fields are ignored.', 'A new valid identity returns exactly True and an exact replay returns exactly False (the bool objects, not any truthy or falsy value) without changing records; different ids remain different events even with equal payloads.', 'A conflicting id, missing field, invalid field value or non-dictionary input raises ValueError without changing existing events.', 'After the caller commits, closes and reconnects, replay detection still works. The caller owns the supplied connection.'],
    languageGoal: 'Explain cause and consequence.', prompt: 'Why did the totals change after a retry? Explain how your fix handles both a replay and a conflict.',
    hints: ['An in-memory set disappears on restart. The event identity needs durable storage.', 'How can you distinguish equal and conflicting payloads for an existing identity? Reading first and handling an insert collision are both possible.', 'Test a replay between two different deliveries. A database exception does not automatically mean an exact duplicate.'],
    sources: [{ title: 'Transactions in Python SQLite', url: 'https://docs.python.org/3/library/sqlite3.html#transaction-control' }],
    commands: ['python3 replay.py'], lesson: 'A timeout does not tell a sender whether a write committed. Identity and payload distinguish replays from conflicts; invalid input must not change existing events. SQLite’s positive INTEGER range ends at 9223372036854775807; a float such as 7.0 is rejected like any other non-int. Return the bool objects True and False, not 1 and 0. Names and ids are nonempty strings; this lab does not trim or case-fold them. The caller commits and closes the connection. Choose your validation and insertion strategy; concurrent writers are a later exercise. Existing workspace documents are preserved; use these current objectives.', artifact: 'Replay guardian',
  },
  {
    id: 'ledger', chapter: 'outpost', order: 5, title: 'Numbers that tell the truth', subtitle: 'Rebuild the daily ledger', sector: 'Data observatory', icon: '▥',
    skills: ['ETL', 'Data quality', 'Decimal arithmetic'], prerequisites: ['echo'], xp: 240, duration: '35–50 min', kind: 'repair',
    briefs: {
      guided: 'The daily report is wrong. Read deliveries, remove exact duplicates and add their amounts. Report bad rows instead of hiding them.',
      connected: 'Build a trustworthy daily ledger from delivery records. Normalize dates, deduplicate exact replays, preserve decimal amounts and explain which rows were rejected.',
      independent: 'Repair the transformation contract for an operational data feed. Produce deterministic daily aggregates and row-level rejection evidence while distinguishing malformed input from conflicting identities.',
    },
    objectives: ['transform(rows) takes a list and returns {"totals": {"YYYY-MM-DD": "0.00"}, "rejected": [zero-based row indices]}. Each rejected index appears once; any deterministic index order is accepted.', 'Each row is a dictionary with nonempty string id, a real calendar date in exact YYYY-MM-DD or YYYY/MM/DD format, and an amount string. Extra fields are ignored.', 'Amounts use ASCII digits with an optional point and one or two fractional digits, from 0 to 9999999999999999.99 inclusive. Leading zeros are allowed; signs, spaces and scientific notation are not.', 'Sum money exactly and render two decimal places. Daily totals may exceed the per-row maximum. Sort day keys; use any exact arithmetic strategy.', 'Normalize date and amount before comparing ids. Keep the first valid occurrence, ignore exact normalized replays, and reject later conflicts. An invalid row does not reserve its id.', 'Reject malformed rows, preserve the input, and produce the same output on repeated calls.'],
    languageGoal: 'Compare an expected result with an observed result.', prompt: 'What made the old report unreliable? Explain one rejected row and how you verified the new totals.',
    hints: ['Consider integer minor units or Decimal with sufficient precision. Does your arithmetic retain cents near the amount maximum?', 'Compare an identity’s normalized date and amount, not its original spelling. A replay and a conflict have different outcomes.', 'Can an invalid row prevent a later valid row with the same id from being accepted? Keep rejection evidence visible.'],
    sources: [{ title: 'Python Decimal', url: 'https://docs.python.org/3/library/decimal.html' }, { title: 'Data Engineering Zoomcamp', url: 'https://github.com/DataTalksClub/data-engineering-zoomcamp' }],
    commands: ['python3 preview.py'], lesson: 'A pipeline owns data meaning: valid shape, normalization, identity, exact totals and visible rejected rows. The per-row amount maximum is 9999999999999999.99, but totals may be larger. Decimal precision applies to arithmetic; integer minor units are also valid. Rejected indices need not be sorted, but must be unique and repeatable. Invalid rows do not reserve ids. Existing workspace documents are preserved; these objectives contain the current input contract.', artifact: 'Quality lens',
  },
  {
    id: 'recovery', chapter: 'outpost', order: 6, title: 'After the blackout', subtitle: 'Restore the outpost from evidence', sector: 'Recovery core', icon: '⬡',
    skills: ['Recovery', 'Atomicity', 'Transfer of learning'], prerequisites: ['gateway', 'ledger'], xp: 320, duration: '40–60 min', kind: 'assessment',
    briefs: {
      guided: 'The live database is gone. Recover it from the event archive. A failed recovery must keep the last working database safe.',
      connected: 'Restore the outpost from a delivery archive. Recovery must be repeatable, detect conflicting identities, and preserve the previous database when the archive is invalid.',
      independent: 'Design a recovery procedure with a clear commit boundary. Rebuild trusted state from an archive, prove repeatability and demonstrate that failed validation cannot damage the last known-good database.',
    },
    objectives: ['recover(db_path, events) rebuilds persistent events(id TEXT PRIMARY KEY, item TEXT, quantity INTEGER) and returns {"event_count": int, "total_quantity": int}. Column order is not significant.', 'The archive is a list of dictionaries with nonempty string id/item and integer quantity from 1 to 9223372036854775807, excluding bool. Extra fields are ignored, as in Echo.', 'Exact duplicates count once. Invalid records and ids reused with a different item or quantity raise ValueError.', 'Successful recovery replaces the entire old event set with the archive, including when either set is empty. Repeating the archive gives the same state and summary.', 'On validation failure, preserve existing database rows, schema and unrelated data, even after several valid records. This is logical state preservation, not byte-for-byte file identity.'],
    languageGoal: 'Give a connected incident debrief and defend a decision.', prompt: 'Brief the next operator: what did you restore, how did you protect existing data, and what evidence shows recovery is safe?',
    hints: ['First write down what must remain true if recovery fails halfway through.', 'Complete validation before destructive changes, or use a transaction whose rollback preserves old state.', 'Treat replacement as one transaction. Validate every record and detect conflicts before committing the rebuilt event set.'],
    sources: [{ title: 'SQLite atomic commit', url: 'https://www.sqlite.org/atomiccommit.html' }],
    commands: ['python3 drill.py'], lesson: 'Apply identity, validation and persistence to replacement. A different nonempty archive must remove old events, not merely add or update rows. A late invalid record must leave the last good rows and schema intact. Prevalidation, staging or rollback-based validation can all satisfy the contract; no transaction syntax is prescribed. This exercise checks validation failures, not power loss, disk exhaustion or concurrent recovery. Existing workspace documents are preserved; use these current objectives.', artifact: 'Recovery sentinel',
  },
  ...architectMissions,
  httpTrialMission,
]

export const futureChapters = [
  { title: "The architect's guild · next steps", topics: 'Service boundaries · alternatives · architecture decisions · changing requirements' },
  { title: 'The service workshop', topics: 'API design · persistence · pagination · concurrent transactions · compatible migrations' },
  { title: 'Evidence and trust', topics: 'Contract tests · fault injection · authentication · authorization · safe boundaries' },
  { title: 'Reliable operations', topics: 'CI/CD · Linux processes · observability · rollout · backup and restore' },
  { title: 'Under pressure', topics: 'Query plans · indexes · load measurement · deadlines · caching · backpressure' },
  { title: 'The event frontier', topics: 'Queues · Kafka topics and partitions · consumer groups · offsets · delivery semantics' },
  { title: 'The data district', topics: 'Incremental pipelines · orchestration · warehouse modeling · lineage · schema evolution' },
  { title: 'The model laboratory', topics: 'Dataset splits · leakage · baselines · basic metrics · simple training · serving' },
  { title: 'The independent outpost', topics: 'A connected system · failure drill · changed requirement · reproducible handover' },
]

export const followUpQuestions: Record<string, string[]> = {
  ...architectFollowUps,
  'http-trial': ['Explain why a cursor that is not in the snapshot can still be valid.', 'Two clients request different pages. What should stay unchanged between their requests?'],
  signal: ['A new operator says a running process must be healthy. Explain why this is not enough and suggest a check.', 'Your colleague checked /health but forgot unknown routes. Ask a useful follow-up question and explain why it matters.', 'Tell the next shift what evidence they should collect before changing an HTTP handler.'],
  vault: ['Imagine a second application writes directly to the vault. Explain which rules still protect the data.', 'A colleague wants to duplicate the item name in every movement. Explain one consequence of that design.', 'Ask the operator to clarify whether a quantity of zero represents a real movement. Explain why you need to know.'],
  gateway: ['A teammate used localhost for an upstream in another container. Explain the mistake in simple words.', 'The nginx syntax check passes but the endpoint returns 502. What would you investigate next, and why?', 'Explain the route a request takes without using the words proxy or upstream.'],
  echo: ['A sender lost the response and wants to retry. Explain why retrying can be safe in your design.', 'Two messages have the same id but different quantities. Explain why silently ignoring the second message is risky.', 'Tell an operator what should happen after a process restart when an old event arrives again.'],
  ledger: ['A report looks plausible but has no record of rejected input. Explain why you would question it.', 'Compare an exact duplicate with a conflicting record. Explain what each should do to the report.', 'Ask a source owner to clarify the meaning of a missing amount. Explain how their answer affects the pipeline.'],
  recovery: ['Hand over the recovery procedure to a colleague who has never run it. State one thing they must verify.', 'Explain what should happen when the last archive record is invalid, even if earlier records were valid.', 'A manager asks whether having a backup proves recovery is safe. Explain what evidence you would need.'],
}

export function missionById(id: string): Mission {
  const mission = missions.find((item) => item.id === id)
  if (!mission) throw new Error('Unknown mission')
  return mission
}
