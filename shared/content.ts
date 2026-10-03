import type { Mission } from './types.js'

export const missions: Mission[] = [
  {
    id: 'signal', order: 1, title: 'A signal in the dark', subtitle: 'Bring the command relay online', sector: 'Command relay', icon: '◈',
    skills: ['HTTP contracts', 'Diagnostics', 'Python foundations'], prerequisites: [], xp: 120, duration: '20–35 min', kind: 'repair',
    briefs: {
      guided: 'The outpost cannot hear the relay. Its health check is broken. Fix the HTTP response and test it.',
      connected: 'The command relay is running, but the outpost marks it offline. Investigate its HTTP contract, repair the health check, and explain your evidence.',
      independent: 'Restore the relay’s health contract without hiding failures elsewhere. Demonstrate correct success and unknown-route behavior, then brief the operator on your diagnosis.',
    },
    objectives: ['GET /health returns status 200 and JSON {"status":"ok","service":"relay"}.', 'The response uses application/json.', 'An unknown route returns 404, including when a query string is present.'],
    languageGoal: 'Describe a problem, an action and observable evidence.', prompt: 'What was wrong with the relay? What did you change, and how did you check it?',
    hints: ['Read Handler.do_GET in service.py. The process being alive is not the same as the HTTP contract being correct.', 'Parse the URL path separately from its query. A health request should return a JSON object with both required keys.', 'Use json.dumps, send_response, send_header and end_headers before writing encoded bytes. Keep a separate 404 branch.'],
    sources: [{ title: 'Python HTTP server', url: 'https://docs.python.org/3/library/http.server.html' }, { title: 'HTTP status codes', url: 'https://developer.mozilla.org/en-US/docs/Web/HTTP/Status' }],
    commands: ['python3 service.py', 'curl -i http://127.0.0.1:45101/health', 'curl -i http://127.0.0.1:45101/missing'],
    lesson: 'A running process can still be unhealthy. A health contract has a status, a content type and a body. Inspect all three. Use the terminal to observe behavior before editing; then repeat the same request. This first lab is a small diagnostic, not a claim that HTTP is new to you.',
    artifact: 'Relay health probe',
  },
  {
    id: 'vault', order: 2, title: 'Give memory a structure', subtitle: 'Protect the supply vault', sector: 'Memory vault', icon: '▤',
    skills: ['Relational modeling', 'Constraints', 'Transactions'], prerequisites: ['signal'], xp: 160, duration: '30–45 min', kind: 'build',
    briefs: {
      guided: 'The vault loses track of supplies. Create two linked tables. The database must reject invalid records.',
      connected: 'Design storage for supply items and movements. Put data integrity in the schema, and prove that invalid movements cannot enter the vault.',
      independent: 'Establish a relational integrity boundary for inventory movements. Justify your keys and constraints and demonstrate persistence across independent connections.',
    },
    objectives: ['create_schema(connection) creates items(id TEXT PRIMARY KEY, name TEXT NOT NULL) and movements(id TEXT PRIMARY KEY, item_id TEXT NOT NULL, quantity INTEGER NOT NULL).', 'movements.item_id references items.id; quantity must be positive.', 'Duplicate identifiers, missing names, unknown items and non-positive quantities are rejected by SQLite.', 'Calling create_schema twice preserves existing data.'],
    languageGoal: 'Explain a design choice and what it prevents.', prompt: 'Why did you choose these constraints? Give one example of data the vault now rejects.',
    hints: ['Use constraints in CREATE TABLE, not only checks in Python. Foreign key enforcement is enabled on each test connection.', 'Use NOT NULL, PRIMARY KEY, FOREIGN KEY and CHECK. IF NOT EXISTS makes schema creation repeatable.', 'Avoid dropping tables when creating the schema. A repeated startup should preserve movements already recorded.'],
    sources: [{ title: 'SQLite constraints', url: 'https://www.sqlite.org/lang_createtable.html' }, { title: 'Foreign keys', url: 'https://www.sqlite.org/foreignkeys.html' }],
    commands: ['python3 inspect_vault.py'],
    lesson: 'A database schema is an executable contract. Primary keys identify facts, foreign keys connect facts, and constraints block impossible states even if another client writes the data. SQLite foreign keys must be enabled per connection. This lesson tests schema-level integrity rather than a specific formatting of SQL.', artifact: 'Integrity seal',
  },
  {
    id: 'gateway', order: 3, title: 'Open the right gate', subtitle: 'Route traffic through nginx', sector: 'Transit gate', icon: '⌘',
    skills: ['Reverse proxy', 'nginx', 'Container networking'], prerequisites: ['signal'], xp: 200, duration: '35–50 min', kind: 'repair',
    briefs: {
      guided: 'Two containers are ready. nginx is the front door. Make /api/health reach the relay. Keep unknown routes closed.',
      connected: 'The relay works inside its container, but the gateway sends traffic to the wrong place. Repair nginx routing and verify the response from outside the gateway.',
      independent: 'Restore the gateway boundary between the published endpoint and its private upstream. Account for container DNS and URI rewriting; demonstrate both permitted and unknown routes.',
    },
    objectives: ['Use the supplied Compose project and start it from the terminal.', 'GET /api/health on the gateway returns 200 and the relay JSON.', 'The /api/ prefix is removed before forwarding to the relay.', 'GET /missing returns 404. Validate nginx configuration and reload after changes.'],
    languageGoal: 'Ask for clarification and explain a request path.', prompt: 'Describe how a request reaches the relay. Why does localhost not point to the other container?',
    hints: ['Inside the nginx container, localhost means nginx’s own container. Compose provides DNS using service names.', 'The upstream is relay:8000. Compare a proxy_pass URL with and without a trailing slash.', 'Use location /api/ { proxy_pass http://relay:8000/; } and a separate location / { return 404; }. Validate before reloading.'],
    sources: [{ title: 'nginx proxy_pass', url: 'https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_pass' }, { title: 'Compose networking', url: 'https://docs.docker.com/compose/how-tos/networking/' }],
    commands: ['docker compose up -d', 'docker compose exec gateway nginx -t', 'docker compose exec gateway nginx -s reload', 'docker compose port gateway 8080', 'curl -i http://127.0.0.1:45103/api/health', 'docker compose down'],
    lesson: 'A reverse proxy receives a client request and forwards it to another service. Containers have separate network namespaces: localhost inside one container is not the host or another container. Compose service names provide internal DNS. The slash in proxy_pass changes which part of the URI is forwarded. Try predicting the path before sending curl.', artifact: 'Gateway route map',
  },
  {
    id: 'echo', order: 4, title: 'An echo is not an event', subtitle: 'Make retries safe', sector: 'Event conduit', icon: '⇄',
    skills: ['Idempotency', 'Transactions', 'Event identity'], prerequisites: ['vault'], xp: 220, duration: '30–45 min', kind: 'repair',
    briefs: {
      guided: 'A sender retries after a timeout. The same delivery is counted twice. Store each event once, but reject a reused ID with different data.',
      connected: 'Retries are inflating the supply ledger. Implement repeat-safe event ingestion, distinguishing an exact replay from a conflicting event identity.',
      independent: 'Establish durable idempotency at the ingestion boundary. Preserve exactly one effect for repeated delivery and reject identity collisions without corrupting existing state.',
    },
    objectives: ['ingest(connection, event) stores events(id TEXT PRIMARY KEY, item TEXT, quantity INTEGER).', 'A new valid event returns True. An exact replay returns False and leaves one record.', 'The same id with a different item or quantity raises ValueError without changing stored data.', 'Missing/empty identifiers or item, non-integer (including bool), zero or negative quantities raise ValueError.', 'Replay detection survives closing and reopening the database.'],
    languageGoal: 'Explain cause and consequence.', prompt: 'Why did the totals change after a retry? Explain how your fix handles both a replay and a conflict.',
    hints: ['An in-memory set disappears on restart. The event identity needs durable storage.', 'Read an existing row by id and compare its payload. An exact duplicate and a conflicting duplicate are different cases.', 'Validate before writing; use a primary key for event id. Do not catch every database exception and silently call it a duplicate.'],
    sources: [{ title: 'Transactions in Python SQLite', url: 'https://docs.python.org/3/library/sqlite3.html#transaction-control' }],
    commands: ['python3 replay.py'], lesson: 'A network timeout does not tell a sender whether the receiver committed a write. Retrying is normal. Idempotency means the same logical operation has the same effect when repeated. An identifier cannot quietly change meaning: that is a conflict, not a retry. This pattern later connects to Kafka delivery and incremental data ingestion.', artifact: 'Replay guardian',
  },
  {
    id: 'ledger', order: 5, title: 'Numbers that tell the truth', subtitle: 'Rebuild the daily ledger', sector: 'Data observatory', icon: '▥',
    skills: ['ETL', 'Data quality', 'Decimal arithmetic'], prerequisites: ['echo'], xp: 240, duration: '35–50 min', kind: 'repair',
    briefs: {
      guided: 'The daily report is wrong. Read deliveries, remove exact duplicates and add their amounts. Report bad rows instead of hiding them.',
      connected: 'Build a trustworthy daily ledger from delivery records. Normalize dates, deduplicate exact replays, preserve decimal amounts and explain which rows were rejected.',
      independent: 'Repair the transformation contract for an operational data feed. Produce deterministic daily aggregates and row-level rejection evidence while distinguishing malformed input from conflicting identities.',
    },
    objectives: ['transform(rows) returns {"totals": {"YYYY-MM-DD": "0.00"}, "rejected": [zero-based row indices]}.', 'Rows contain id, date (strict YYYY-MM-DD or YYYY/MM/DD) and amount (non-negative decimal string, at most two decimal places).', 'Sum money exactly and render two decimal places. Sort day keys.', 'Exact normalized duplicates count once. Reject malformed rows and conflicting later occurrences of an id.', 'Do not mutate the input. Repeated calls produce the same result.'],
    languageGoal: 'Compare an expected result with an observed result.', prompt: 'What made the old report unreliable? Explain one rejected row and how you verified the new totals.',
    hints: ['Use decimal.Decimal rather than float for currency. Parse and validate input at the boundary.', 'Remember each accepted id with its normalized date and amount. Keep the first accepted event; record the index of a conflicting later row.', 'An invalid row should not reserve its id. Keep validation, deduplication and aggregation as distinct steps.'],
    sources: [{ title: 'Python Decimal', url: 'https://docs.python.org/3/library/decimal.html' }, { title: 'Data Engineering Zoomcamp', url: 'https://github.com/DataTalksClub/data-engineering-zoomcamp' }],
    commands: ['python3 preview.py'], lesson: 'A pipeline is responsible for data meaning as well as movement. Silent row loss and binary floating-point rounding both produce believable but wrong reports. Define what is valid, what counts as the same fact, and how rejected input remains visible. These contracts matter before choosing any orchestration or big-data tool.', artifact: 'Quality lens',
  },
  {
    id: 'recovery', order: 6, title: 'After the blackout', subtitle: 'Restore the outpost from evidence', sector: 'Recovery core', icon: '⬡',
    skills: ['Recovery', 'Atomicity', 'Transfer of learning'], prerequisites: ['gateway', 'ledger'], xp: 320, duration: '40–60 min', kind: 'assessment',
    briefs: {
      guided: 'The live database is gone. Recover it from the event archive. A failed recovery must keep the last working database safe.',
      connected: 'Restore the outpost from a delivery archive. Recovery must be repeatable, detect conflicting identities, and preserve the previous database when the archive is invalid.',
      independent: 'Design a recovery procedure with a clear commit boundary. Rebuild trusted state from an archive, prove repeatability and demonstrate that failed validation cannot damage the last known-good database.',
    },
    objectives: ['recover(db_path, events) rebuilds events(id TEXT PRIMARY KEY, item TEXT, quantity INTEGER) and returns {"event_count": int, "total_quantity": int}.', 'Validate the same event contract as Echo. Exact duplicate events count once; conflicts and invalid events raise ValueError.', 'A successful recovery replaces old events. Repeating the same archive gives the same state.', 'On any validation failure the old database remains unchanged, including when the invalid event follows valid events.'],
    languageGoal: 'Give a connected incident debrief and defend a decision.', prompt: 'Brief the next operator: what did you restore, how did you protect existing data, and what evidence shows recovery is safe?',
    hints: ['First write down what must remain true if recovery fails halfway through.', 'Complete validation before destructive changes, or use a transaction whose rollback preserves old state.', 'Treat replacement as one transaction. Validate every record and detect conflicts before committing the rebuilt event set.'],
    sources: [{ title: 'SQLite atomic commit', url: 'https://www.sqlite.org/atomiccommit.html' }],
    commands: ['python3 drill.py'], lesson: 'This is a transfer challenge. Apply earlier knowledge to a new situation before requesting a hint. A backup is useful only if recovery can be demonstrated. A recovery job should establish a trustworthy state, and a bad archive should not destroy the last good state. Completion with help still restores the base; independent evidence is tracked separately.', artifact: 'Recovery sentinel',
  },
]

export const futureChapters = [
  { title: "The architect's guild", topics: 'System design · requirements · capacity estimates · service boundaries · trade-offs · design reviews' },
  { title: 'Under pressure', topics: 'Query plans · indexes · load measurement · timeouts · caching · backpressure' },
  { title: 'Reliable operations', topics: 'CI/CD · migrations · Linux permissions · observability · backup and restore · access control' },
  { title: 'The event frontier', topics: 'Queues · Kafka topics and partitions · consumer groups · offsets · delivery semantics' },
  { title: 'The data district', topics: 'Incremental pipelines · orchestration · warehouse modeling · lineage · schema evolution' },
  { title: 'The model laboratory', topics: 'Dataset splits · leakage · baselines · basic metrics · simple training · serving' },
]

export const followUpQuestions: Record<string, string[]> = {
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
