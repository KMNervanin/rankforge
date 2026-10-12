import test from 'node:test'
import assert from 'node:assert/strict'
import { cp, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { run, root } from '../server/labs.js'
import type { Check } from '../shared/types.js'
import { bonusChecks, bonusPassed } from '../shared/checks.js'

async function candidate(t: test.TestContext, source?: string) {
  const workspace = await mkdtemp(path.join(os.tmpdir(), 'rankforge-backoff-'))
  t.after(() => rm(workspace, { recursive: true, force: true }))
  await cp(path.join(root, 'labs', 'backoff'), workspace, { recursive: true })
  if (source !== undefined) await writeFile(path.join(workspace, 'wrapper.py'), source)
  const result = await run('python3', ['-I', '-B', path.join(root, 'server', 'verify_backoff.py'), 'backoff', workspace], workspace)
  assert.notEqual(result.code, 124, result.stderr)
  const parsed = JSON.parse(result.stdout.trim().split('\n').at(-1) ?? '') as { checks: Check[] }
  assert.ok(parsed.checks.length, JSON.stringify(result))
  return { ...result, checks: parsed.checks }
}
const solution = (name = 'urllib') => readFile(path.join(root, 'tests', 'solutions', 'backoff', `${name}.py`), 'utf8')
function rejected(result: Awaited<ReturnType<typeof candidate>>, check: string) {
  assert.equal(result.code, 1, JSON.stringify(result.checks))
  assert.ok(result.checks.some((item) => !item.passed && item.name.includes(check)), JSON.stringify(result.checks))
}

test('Backoff: the starter is RED on every retry requirement through the fault adapter', async (t) => {
  const result = await candidate(t)
  for (const name of ['Retry-After', 'Backoff grows', 'max_attempts', 'length stop', 'stream cut', 'Quota', 'side effect', 'ledger', 'Transfer']) rejected(result, name)
  assert.equal(bonusPassed(result.checks), false)
})

for (const name of ['urllib', 'httpclient']) {
  test(`Backoff: the ${name} implementation is GREEN against every scripted fault and earns the bonus`, async (t) => {
    const result = await candidate(t, await solution(name))
    assert.equal(result.code, 0, JSON.stringify(result.checks))
    assert.equal(result.checks.length, 10)
    assert.ok(result.checks.every((item) => item.passed), JSON.stringify(result.checks))
    assert.equal(bonusPassed(result.checks), true)
    assert.ok(!result.checks.some((item) => item.name === 'Environment blocked'), 'No live part: nothing can be environment blocked')
  })
}

const mutations: [string, string, string, string][] = [
  ['Retry-After ignored in favour of the bare backoff', '                wait = max(wait, outcome.floor)', '                wait = wait', 'Retry-After'],
  ['jitter removed', 'return random.uniform(delay * (1 - self.jitter), delay * (1 + self.jitter))', 'return delay', 'Backoff grows'],
  ['attempt bound a thousand times too loose', 'if stop is None and attempt >= rules.max_attempts:', 'if stop is None and attempt >= rules.max_attempts * 1000:', 'max_attempts'],
  ['budget checked only after sleeping', 'if elapsed + wait > rules.total_budget:', 'if elapsed > rules.total_budget:', 'max_attempts'],
  ['a length stop reported as complete', '"truncated" if finish == "length" else "complete"', '"complete"', 'length stop'],
  ['a cut stream reported as complete', '    if finish is None:\n        return Attempt("stream_cut"', '    if False:\n        return Attempt("stream_cut"', 'stream cut'],
  ['quota errors retried like rate limits', 'if any(label == "insufficient_quota" or label.startswith("billing") for label in labels):', 'if False:', 'Quota'],
  ['a fresh idempotency key on every attempt', 'outcome = send(request, base_url, key, rules.request_timeout)', 'outcome = send(request, base_url, idempotency_key or f"call-{uuid.uuid4()}", rules.request_timeout)', 'side effect'],
  ['the effect run for incomplete answers', 'if result["complete"] and effect is not None:', 'if effect is not None:', 'length stop'],
  ['the ledger written once per call instead of once per attempt', '            ledger.write(json.dumps({"key": key, "attempt": attempt', '            stop is None or ledger.write(json.dumps({"key": key, "attempt": attempt', 'ledger'],
]
for (const [name, before, after, check] of mutations) {
  test(`Backoff rejects ${name}`, async (t) => {
    const source = await solution()
    assert.ok(source.includes(before), `Mutation anchor missing: ${name}`)
    rejected(await candidate(t, source.replaceAll(before, after)), check)
  })
}

test('Backoff: ignoring x-ratelimit-reset-requests passes the contract but misses the hidden bonus; the bonus never fails the run', async (t) => {
  const source = (await solution()).replace('floor = retry_after if retry_after is not None else duration(error.headers.get("x-ratelimit-reset-requests"))', 'floor = retry_after')
  assert.notEqual(source, await solution())
  const result = await candidate(t, source)
  assert.equal(result.code, 0, JSON.stringify(result.checks))
  assert.equal(bonusChecks(result.checks).length, 1)
  assert.ok(bonusChecks(result.checks)[0]!.name.startsWith('bonus:'))
  assert.equal(bonusPassed(result.checks), false)
})

test('Backoff reports import failure as a failed check', async (t) => {
  rejected(await candidate(t, 'raise ValueError("Controlled import failure")\n'), 'Load call wrapper')
})
