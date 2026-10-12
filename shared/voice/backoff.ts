import type { Mission } from '../types.js'

export const mission: Mission = {
  id: 'backoff', chapter: 'voice', order: 4, title: 'An unreliable colleague', subtitle: 'Retry what can be retried, and nothing else', sector: 'Operator’s desk', icon: '↻',
  block: 'Calling the model', files: ['wrapper.py', 'policy.json', 'request.json'],
  nudge: 'Rumour says the relay whispers when its window resets even when it refuses to say how long to wait.',
  skills: ['Retry policy', 'Failure classification', 'Idempotency'], prerequisites: ['record', 'echo'], xp: 250, duration: 'Self-paced', kind: 'repair',
  briefs: {
    guided: 'The relay drops answers, asks for patience and sometimes says the quota is spent. Teach the wrapper to tell these apart: retry with growing waits, stop at the bound, never pass off a fragment as an answer. Hints are available; guided work earns the same rewards.',
    connected: 'Turn a retry-everything loop into a policy: classify each failure, honour Retry-After as a minimum, back off with jitter inside a time budget, pause on quota, keep one idempotency key per call and write a ledger line per attempt. Prove it against a fault adapter that scripts every failure.',
    independent: 'Build a call wrapper that treats the model as an unreliable dependency: bounded jittered backoff with Retry-After floors and a total budget, explicit incomplete results for length stops and cut streams, no retry on quota or client errors, one side effect per logical call, and a retry ledger. Demonstrate it on a shuffled failure order.',
  },
  objectives: [
    'Keep wrapper.py importable with call(request, *, base_url, policy, ledger_path, clock=time.monotonic, sleep=time.sleep, effect=None, idempotency_key=None). The policy has the shape of policy.json: max_attempts, base_delay, max_delay, jitter, total_budget, request_timeout, quota_pause. Read every number from the argument; measure and wait only through clock and sleep.',
    'POST {base_url}/chat/completions with the request as the body and an Idempotency-Key header that stays the same on every attempt of one call and differs between calls; when stream is true add stream_options.include_usage. Each attempt waits at most request_timeout seconds.',
    'Classify each attempt: complete, truncated (finish_reason length), rate_limited (429), quota (429 with insufficient_quota or a billing type or code), server_error (5xx), timeout, stream_cut (the stream ended before a finish_reason), rejected (other 4xx), transport. Retry only rate_limited, server_error, timeout, stream_cut and transport.',
    'After retryable attempt n the bare delay is min(base_delay × 2^(n−1), max_delay); the wait is uniform in [delay × (1 − jitter), delay × (1 + jitter)], and at least Retry-After when the response carried one. Never exceed max_attempts; never sleep when elapsed + wait would exceed total_budget, end the call instead.',
    'A length stop returns at once with complete false and the partial content; a cut stream is retried but, when the bound ends the call, comes back with complete false, finish_reason null and usage null. Quota errors end the call as paused after one request with pause = Retry-After or quota_pause, without sleeping; other 4xx end it as rejected after one request.',
    'Call effect(result) exactly once, only for a complete result, never per attempt and never for a fragment. Append one JSON line per attempt to ledger_path with key, attempt, outcome, status, retry_after, wait and elapsed; earlier lines stay unchanged. The result carries outcome, complete, content, finish_reason, usage, attempts, elapsed, last, status, retry_after, pause, stop, key and error.',
    'Verify runs a fault adapter (a labeled test tool that scripts 429 with Retry-After, timeouts, 5xx, a stream cut mid-answer, a length stop, a quota error, a 400 and endless 503s) with an injected clock and sleep, then a transfer run with a shuffled failure order. No model and no key are involved.',
  ],
  languageGoal: 'Describe a failure policy as rules with conditions, and say which failure each rule does not cover.', prompt: 'Explain to the operator what the assistant does when the relay fails. Name one failure it retries, one it refuses to retry and why, and what the operator sees when an answer was cut short.',
  hints: ['Run the demo with 429:3,ok and then with quota,ok and compare the ledger. Which of the starter’s retries made sense, and what did the relay actually tell it in each response?', 'Every attempt ends in one of a handful of classes, and only some of those deserve another request. Write the classes down before touching the loop, and decide where Retry-After, the bound and the budget enter.', 'Keep one key for the whole call and generate the wait from the attempt number: delay = min(base × 2^(n−1), max), then jitter, then max(that, Retry-After). Check elapsed + wait against the budget before sleeping, and write the ledger line after the wait is known.'],
  sources: [
    { title: 'OpenAI rate limits guide: Retry-After, exponential backoff with jitter, quota errors', url: 'https://developers.openai.com/api/docs/guides/rate-limits' },
    { title: 'OpenAI error codes: 429 variants and insufficient_quota', url: 'https://developers.openai.com/api/docs/guides/error-codes' },
    { title: 'OpenAI chat completions streaming: stream_options.include_usage and the final usage chunk', url: 'https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create' },
    { title: 'Python http.client: IncompleteRead and timeouts', url: 'https://docs.python.org/3.10/library/http.client.html' },
    { title: 'Python urllib.error.HTTPError: code and headers', url: 'https://docs.python.org/3.10/library/urllib.error.html' },
  ],
  commands: ['python3 -B demo.py 429:2,timeout,503,ok', 'python3 -B demo.py cut,ok --stream', 'python3 -B demo.py quota,ok', 'cat ledger.jsonl'],
  lesson: 'The starter retries every failure with the same fixed wait and no bound, retries quota errors, generates a new idempotency key on every attempt, calls the effect from inside the loop, returns a length stop and a cut stream as complete answers and writes one summary line instead of a ledger. LEARN.md gives the complete contract: outcome classes, the wait formula with its bounds, the attempt and time bounds, the pause rule and the ledger line. Verify talks to your call() through a fault adapter that scripts each response and injects the clock, so a correct run takes about a second; a wrapper that waits for real or loops forever is stopped and reported. Out of scope: streaming output to a consumer while it arrives, retrying across different models or endpoints, and anything a live model would add; no model is required for this mission.',
  artifact: 'Call wrapper with a retry ledger',
}

export const followUps: string[] = [
  'The operator asks why the assistant waited three seconds when the policy says half a second. Explain where the longer wait came from and why the shorter one would have been wrong.',
  'A colleague proposes retrying the quota error a few times "just in case". Explain what would happen to the pending request and to the bill, and what the wrapper does instead.',
]
