import type { Mission } from './types.js'

export const httpTrialMission: Mission = {
  id: 'http-trial', chapter: 'outpost', bonus: true, order: 10, title: 'Beyond the health check', subtitle: 'An optional HTTP field trial', sector: 'Supply beacon', icon: '⇌',
  nudge: 'Rumour says some clients send query strings with empty and nameless pieces between the real ones.',
  skills: ['HTTP transfer', 'Query validation', 'Stable pagination'], prerequisites: ['signal', 'gateway'], xp: 180, duration: 'Self-paced', kind: 'assessment',
  briefs: {
    guided: 'The supply beacon repeats the wrong page. Repair its read-only HTTP endpoint. Use hints if useful; guided transfer earns the same rewards.',
    connected: 'Transfer your routing skills to a new endpoint: serve stable pages from a supply snapshot, validate query values and preserve the underlying records.',
    independent: 'Repair a paginated supply contract under varied snapshots and request order. Demonstrate that cursors, validation and unknown paths behave correctly without altering state.',
  },
  objectives: [
    'Keep service.py with an importable Handler for HTTPServer. Each server has server.supplies: 0–8 records {id: unique integer 1–100000, item: 1–128 Unicode characters, quantity: integer 1–1000000000}. Input order may vary. Read this supplied snapshot without changing it.',
    'GET /supplies returns 200 directly with JSON {"items": [...], "next_after": integer or null}. Items are original records in ascending id order with id > after, capped at limit. next_after is the last returned id only when more qualifying records remain; otherwise it is null.',
    'Query defaults: after=0 and limit=2. URL-decode query values. Each known parameter may occur at most once and must contain only ASCII digits (leading zeros allowed); after is 0–100000, limit is 1–4 inclusive. Blank, repeated, signed, fractional and out-of-range values return 400 with {"error":"invalid query"}. Ignore unknown parameters.',
    'Only the exact /supplies path exists. All other paths return 404 with {"error":"not found"}, even with an invalid query. All responses use application/json. Formatting, parameters and extra fields may vary within a 16384-byte body limit. HTTP framing must be complete; Content-Length, chunked or connection-close framing are accepted.',
    'Independent clients, repeats and interleaved cursors see the same snapshot. An unknown cursor is a lower id bound, not an offset. No request changes the supplied list or records. Verify starts its own loopback server; only GET is in scope.',
  ],
  languageGoal: 'Explain a transferred idea and the limits of your evidence.', prompt: 'What changed when you moved from a health endpoint to pagination? Describe one counterexample your checks caught.',
  hints: ['Separate the route from its query. A missing parameter and a present but blank parameter are different inputs.', 'Think of after as a lower bound on a record id, not an array index. What happens when that id is absent?', 'Sketch two pages from an unsorted snapshot. When should next_after be null, and what must remain unchanged after a request?'],
  sources: [{ title: 'Python HTTP server', url: 'https://docs.python.org/3.10/library/http.server.html' }, { title: 'URL parsing and query values', url: 'https://docs.python.org/3.10/library/urllib.parse.html' }],
  commands: ['python3 -B service.py', 'curl -i "http://127.0.0.1:45110/supplies?limit=2"', 'curl -i "http://127.0.0.1:45110/supplies?after=9&limit=2"', 'curl -i "http://127.0.0.1:45110/supplies?limit="'],
  lesson: 'Signal checked one fixed health response. This bonus changes the task to a read-only collection with query validation and continuation. LEARN.md gives the complete bounds and examples. Verify’s server handles requests on separate threads, so keep per-request state inside the handler, not in module globals. Parameter names are case-sensitive: Limit or AFTER is an unknown parameter and is ignored. Choose your parsing, selection and response strategy; there is no required algorithm. Guided and independent transfer are recorded separately from hints already used in earlier missions. Neither mode certifies general HTTP mastery. No model or English debrief is required.',
  artifact: 'Supply pagination probe',
}
