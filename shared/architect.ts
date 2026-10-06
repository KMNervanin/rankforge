import type { Mission } from './types.js'

export const architectMissions: Mission[] = [
  {
    id: 'briefing', chapter: 'guild', order: 7, title: 'Before the blueprint', subtitle: 'Separate promises from assumptions', sector: 'Briefing hall', icon: '◇',
    skills: ['Requirements', 'Traceability', 'Assumptions'], prerequisites: ['recovery'], xp: 220, duration: 'Self-paced', kind: 'build',
    briefs: {
      guided: 'The outpost needs a delivery service. Read the ticket. Keep facts, choices and excluded work separate. Link each requirement to an observation.',
      connected: 'Before choosing an architecture, turn the delivery ticket into a structured requirements manifest. Keep open questions visible and show what would count as evidence.',
      independent: 'Establish a versioned, traceable requirements boundary for the next delivery service. Preserve supplied facts through ticket changes without presenting assumptions as promises.',
    },
    objectives: [
      'Implement build_manifest(ticket) in manifest.py using the exact v1 schema and case categories in LEARN.md. ticket.json is the public facts sheet.',
      'Cover every supplied fact exactly once, with its typed value and unit intact. Link each published observation kind to the requirement containing that fact; case grouping and wording are your choice.',
      'Choose a published option as an assumption with its observable implication, or explicitly leave the question open. Preserve exclusions and reject no valid choice merely because it differs from an example.',
      'Follow changed ticket revisions and fresh facts without mutating input or changing prior returned artifacts. Return a stable manifest on repeat calls.',
      'Automatic success establishes structured traceability only. Prose rationale, feasibility and architecture quality remain optional review topics, not automatic mastery.',
    ],
    languageGoal: 'Distinguish a supplied fact, a chosen assumption and an unanswered question.',
    prompt: 'Which decision did you leave open or treat as an assumption? What evidence would settle it?',
    hints: ['Start with ticket.json, not a diagram. Which values are promises, and which options are still open?', 'Give requirements your own IDs, then connect the published case kinds to those IDs. A case can cover more than one requirement.', 'Try lowering quantity_limit and changing the actor in a copied ticket. Does your manifest still describe that ticket rather than the original example?'],
    sources: [{ title: 'Python data structures', url: 'https://docs.python.org/3.10/tutorial/datastructures.html' }],
    commands: ['python3 -B demo.py', 'python3 -B demo.py ticket.json'],
    lesson: 'A requirement states what must hold; an assumption records a choice that the ticket did not establish. The field manual publishes the complete manifest shape and the meanings of its observation categories. build_manifest is a thin interface for exercising changed tickets, not a demand to automate design reasoning. A schema-valid manifest does not prove its service has been built or measured. Save your work; the demo prints it and Verify checks the bounded contract.',
    artifact: 'Versioned requirements manifest',
  },
  {
    id: 'capacity', chapter: 'guild', order: 8, title: 'Count before choosing', subtitle: 'Give every estimate a unit', sector: 'Capacity desk', icon: '∑',
    skills: ['Capacity estimates', 'Units', 'Quantitative assumptions'], prerequisites: ['briefing'], xp: 240, duration: 'Self-paced', kind: 'repair',
    briefs: {
      guided: 'How much work will deliveries create? Repair the calculator. Convert daily requests to a rate, use mean time, and keep byte units clear.',
      connected: 'Estimate peak traffic, average in-flight work, bandwidth and retained data. Make assumptions explicit and check the equations with changed workloads.',
      independent: 'Build a parameterized capacity model with finite input bounds and explicit units. Separate stable-flow estimates from measured capacity and avoid treating a latency percentile as a mean.',
    },
    objectives: [
      'Implement estimate(workload) in capacity.py. LEARN.md publishes every required field, inclusive bound, unit, output name, equation and error rule; workload.json is the worked example.',
      'Use average daily requests / 86400 for average RPS, multiply by the peak factor for peak RPS, and multiply peak RPS by mean_ms / 1000 for fractional average in-flight work. Never substitute p95 or ceil concurrency.',
      'Compute peak response bytes/s from peak RPS. Retained bytes use average daily writes × retention × the combined storage multiplier, not all-day peak traffic. Report decimal MB/s and binary GiB as documented.',
      'Raise ValueError for missing, nonnumeric, Boolean, nonfinite, out-of-range inputs or fractional retention. Validate even at zero traffic; ignore extra metadata. Preserve all inputs.',
      'Return finite numbers without presentation rounding; float, Decimal and Fraction outputs are accepted within 1e-9 absolute or relative tolerance. Repeated/fresh workloads must agree with the public equations.',
    ],
    languageGoal: 'State an assumption and explain what an estimate does not establish.',
    prompt: 'Which assumptions would you measure before buying capacity? Explain why p95 cannot replace the mean here.',
    hints: ['Write the units beside each input. How many seconds are in the day that daily_requests describes?', 'A stable-flow in-flight average can be 0.5. A server count is a different decision; do not round this estimate up.', 'Use the public sample, then change only retention or peak_multiplier. Which outputs should change and which should stay the same?'],
    sources: [{ title: 'Python numeric types', url: 'https://docs.python.org/3.10/library/stdtypes.html#numeric-types-int-float-complex' }, { title: 'Decimal arithmetic', url: 'https://docs.python.org/3.10/library/decimal.html' }],
    commands: ['python3 -B demo.py', 'python3 -B demo.py workload.json'],
    lesson: 'The calculator predicts work under stated assumptions; it does not measure server throughput. Mean residence time includes queueing, while p95 describes a distribution threshold. The field manual supplies units practice and an explained example, so an unfinished foundation mission is not required. The supplied workload is equivalent briefing context; your earlier files stay in their own workspace.',
    artifact: 'Unit-aware capacity model',
  },
  {
    id: 'contract', chapter: 'guild', order: 9, title: 'A contract you can execute', subtitle: 'Catch the convincing impostor', sector: 'Contract chamber', icon: '⇌',
    skills: ['Consumer contracts', 'HTTP', 'Observable effects'], prerequisites: ['briefing'], xp: 280, duration: 'Self-paced', kind: 'build',
    briefs: {
      guided: 'A 201 status is not enough. Write a probe that checks the delivery response and the effect of a retry. Tell a timeout apart from a wrong response.',
      connected: 'Express the delivery service contract as seven executable observations. Accept different valid servers and expose wrong headers, payloads, routes and duplicate effects.',
      independent: 'Build a bounded consumer probe that accepts compatible representations and rejects behavioral impostors. Distinguish transport unavailability from assertion failure using fresh, owned loopback fixtures.',
    },
    objectives: [
      'Implement probe(base_url, scenario) in probe.py; LEARN.md publishes the exact seven requests, response schema, headers, effects and result names. Do not implement a service or target an external endpoint.',
      'Send create, exact replay and conflicting delivery in order, then the four documented GET observations once each. Check status, JSON media type, X-Contract and typed body fields; tolerate extra fields and harmless formatting.',
      'Read back the original delivery and effects=1. Check full versus summary query behavior and the unknown child route. HTTP contract mismatches do not skip the remaining observations.',
      'Return status passed/failed/timeout/unavailable plus seven {name,passed,detail} checks. Stop without retries on transport failure, close connections and preserve scenario. Apply timeout_s and read at most 8 KiB per response.',
      'Use only the supplied temporary loopback URL and bounded requests: no files, subprocesses, redirects, polling, sleeps or external services. Verify observes requests and state against both conforming styles and named faulty fixtures.',
    ],
    languageGoal: 'Distinguish a failed assertion from missing evidence and explain a counterexample.',
    prompt: 'Describe one service that looked healthy but violated the contract. How did your probe distinguish it from an unavailable endpoint?',
    hints: ['List each observation before writing the probe. A successful status does not establish the body, headers or effect.', 'Inspect an HTTP error response instead of treating it as a connection failure. Parse media types and JSON semantics rather than comparing serialization.', 'Use the duplicate and query demo modes. Can a replay add an effect even when its response looks correct?'],
    sources: [{ title: 'Python HTTP client', url: 'https://docs.python.org/3.10/library/http.client.html' }, { title: 'urllib request and response handling', url: 'https://docs.python.org/3.10/library/urllib.request.html' }],
    commands: ['python3 -B demo.py direct', 'python3 -B demo.py table', 'python3 -B demo.py duplicate', 'python3 -B demo.py timeout', 'python3 -B demo.py unavailable'],
    lesson: 'A consumer contract combines response assertions with observations of state. Verify creates short-lived real HTTP fixtures; it never depends on a daemon you happen to have running. The field manual explains path/query, error classification and both client APIs. Fixture timeout is event-controlled; an unavailable fixture closes before any HTTP response. Passing proves this narrow probe behavior, not service persistence, concurrent safety or production readiness.',
    artifact: 'Executable delivery contract',
  },
]

export const architectFollowUps: Record<string, string[]> = {
  briefing: ['A colleague describes automatic dispatch as a supplied fact. Explain how you would verify or correct that claim.', 'The quantity limit changed after review. Which manifest observations must follow the new ticket?', 'Why can a complete requirements manifest still need a design review?'],
  capacity: ['Peak traffic doubles but average daily writes stay unchanged. Explain which estimates change.', 'A teammate rounds 0.5 in-flight requests up to one server. Explain what the calculation actually means.', 'Compare a predicted bandwidth value with a measurement. What would make you revisit the assumptions?'],
  contract: ['A service returns correct JSON but counts a retry twice. Explain how you would expose the defect.', 'Your probe times out before seeing a response. What can you conclude, and what remains unknown?', 'An API adds an optional JSON field without changing behavior. Explain why your probe should still pass.'],
}
