import test from 'node:test'
import assert from 'node:assert/strict'
import { cp, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { run, root } from '../server/labs.js'
import type { Check } from '../shared/types.js'
import { bonusChecks, bonusPassed } from '../shared/checks.js'
import { llmConfig, startLlmStub, type StubBody } from './llm-stub.js'

// The test-only endpoint answers 'urgent' at temperature 0 and alternates at temperature 1, so the live measurement has a distribution.
function alternating() {
  let turn = 0
  return (body: StubBody) => ({ content: (body as { temperature?: number }).temperature === 0 ? 'urgent' : ['urgent', 'routine'][turn++ % 2]! })
}

async function candidate(t: test.TestContext, source?: string, options: { endpoint?: boolean } = {}) {
  const workspace = await mkdtemp(path.join(os.tmpdir(), 'rankforge-sampling-'))
  t.after(() => rm(workspace, { recursive: true, force: true }))
  await cp(path.join(root, 'labs', 'sampling'), workspace, { recursive: true })
  if (source !== undefined) await writeFile(path.join(workspace, 'experiment.py'), source)
  const stub = options.endpoint === false ? null : await startLlmStub({ reply: alternating() })
  if (stub) { t.after(() => stub.close()); await writeFile(path.join(workspace, 'llm.json'), llmConfig(stub.baseUrl, stub.model)) }
  const result = await run('python3', ['-I', '-B', path.join(root, 'server', 'verify_sampling.py'), 'sampling', workspace], workspace)
  assert.notEqual(result.code, 124, result.stderr)
  const parsed = JSON.parse(result.stdout.trim().split('\n').at(-1) ?? '') as { checks: Check[] }
  assert.ok(parsed.checks.length, JSON.stringify(result))
  return { ...result, checks: parsed.checks, stub }
}
const solution = (name = 'pool') => readFile(path.join(root, 'tests', 'solutions', 'sampling', `${name}.py`), 'utf8')
function rejected(result: Awaited<ReturnType<typeof candidate>>, check: string) {
  assert.equal(result.code, 1, JSON.stringify(result.checks))
  assert.ok(result.checks.some((item) => !item.passed && item.name.includes(check)), JSON.stringify(result.checks))
}

test('Sampling: the starter is RED on every requirement through the scripted adapter', async (t) => {
  const result = await candidate(t)
  for (const name of ['declared number', 'verbatim', 'recomputed from the raw file', 'rerun, not asserted', 'ignores the seed', 'refused']) rejected(result, name)
  assert.equal(bonusPassed(result.checks), false)
  assert.ok(!result.checks.some((item) => item.name === 'Environment blocked'), 'A configured endpoint is not an environment problem')
})

for (const name of ['pool', 'workers']) {
  test(`Sampling: the ${name} implementation is GREEN, earns the bonus and measures the test-only endpoint`, async (t) => {
    const result = await candidate(t, await solution(name))
    assert.equal(result.code, 0, JSON.stringify(result.checks))
    assert.equal(result.checks.length, 8)
    assert.ok(result.checks.every((item) => item.passed), JSON.stringify(result.checks))
    assert.equal(bonusPassed(result.checks), true)
    const live = result.checks.find((item) => item.name.startsWith('Live experiment'))!
    assert.match(live.detail, /test-only at http:\/\/127\.0\.0\.1:\d+\/v1/)
    assert.match(live.detail, /rerun matched/)
    assert.match(live.detail, /2 distinct answers/)
    assert.equal(result.stub!.requests.length, 10, 'Verify makes one probe plus 3 + 3 + 3 requests through the experiment')
  })
}

const mutations: [string, [string, string][], string][] = [
  ['the rerun skipped', [['            jobs.extend((setting, "rerun", index) for index in range(samples))', '            pass']], 'declared number'],
  ['one request per setting copied', [['jobs.extend((setting, "first", index) for index in range(samples))', 'jobs.extend((setting, "first", index) for index in range(1))']], 'declared number'],
  ['the seed not sent', [['        body["seed"] = setting["seed"]', '        body["seed"] = None']], 'declared number'],
  ['the raw file appended instead of replaced', [['open(out_path, "w"', 'open(out_path, "a"']], 'declared number'],
  ['usage not stored', [['"usage": payload.get("usage")', '"usage": None']], 'verbatim'],
  ['content stripped before storing', [['"content": choice["message"]["content"],', '"content": choice["message"]["content"].strip(),']], 'verbatim'],
  ['the report served from memory', [['def report(raw_path):\n    groups = {}', '_CACHE = {}\n\n\ndef report(raw_path):\n    if _CACHE:\n        return dict(_CACHE)\n    groups = {}'], ['        result[name] = stats\n    return result', '        result[name] = stats\n    _CACHE.update(result)\n    return result']], 'recomputed from the raw file'],
  ['a tie broken by first occurrence', [['majority = min(label for label, count in counts.items() if count == top)', 'majority = counts.most_common(1)[0][0]']], 'recomputed from the raw file'],
  ['entropy in nats', [['math.log2(count / n)', 'math.log(count / n)']], 'recomputed from the raw file'],
  ['agreement computed with replacement', [['agreement = sum(count * (count - 1) for count in counts.values()) / (n * (n - 1)) if n > 1 else 1.0', 'agreement = sum((count / n) ** 2 for count in counts.values())']], 'recomputed from the raw file'],
  ['reproducibility asserted from the seed', [['stats["reproducible"] = again == first', 'stats["reproducible"] = True']], 'rerun, not asserted'],
  ['reproducibility derived from first-run agreement', [['stats["reproducible"] = again == first', 'stats["reproducible"] = len(set(first)) == 1']], 'rerun, not asserted'],
  ['index validation dropped', [['    if sorted(by_index) != list(range(len(by_index))):\n        raise ValueError(f"{records[0][\'setting\']}/{run}: indices are not 0..n-1")\n', '']], 'refused'],
]
for (const [name, pairs, check] of mutations) {
  test(`Sampling rejects ${name}`, async (t) => {
    let source = await solution()
    for (const [before, after] of pairs) {
      assert.ok(source.includes(before), `Mutation anchor missing: ${name}`)
      source = source.replaceAll(before, after)
    }
    rejected(await candidate(t, source), check)
  })
}

test('Sampling: ignoring concurrency passes the contract but misses the hidden bonus; the bonus never fails the run', async (t) => {
  const source = (await solution()).replace('        if concurrency > 1:', '        if False:')
  assert.notEqual(source, await solution())
  const result = await candidate(t, source)
  assert.equal(result.code, 0, JSON.stringify(result.checks))
  assert.equal(bonusChecks(result.checks).length, 1)
  assert.ok(bonusChecks(result.checks)[0]!.name.startsWith('bonus:'))
  assert.equal(bonusPassed(result.checks), false)
})

test('Sampling: no model id in llm.json is environment blocked, never a failure or a pass', async (t) => {
  const result = await candidate(t, await solution(), { endpoint: false })
  assert.equal(result.code, 1)
  const blocked = result.checks.find((item) => item.name === 'Environment blocked')!
  assert.ok(blocked, JSON.stringify(result.checks))
  assert.match(blocked.detail, /llm\.json/)
  assert.ok(result.checks.filter((item) => item.name !== 'Environment blocked' && !item.optional).every((item) => item.passed), 'The adapter checks still pass')
})

test('Sampling: an endpoint that does not answer is environment blocked with the address in the detail', async (t) => {
  const workspace = await mkdtemp(path.join(os.tmpdir(), 'rankforge-sampling-'))
  t.after(() => rm(workspace, { recursive: true, force: true }))
  await cp(path.join(root, 'labs', 'sampling'), workspace, { recursive: true })
  await writeFile(path.join(workspace, 'experiment.py'), await solution())
  await writeFile(path.join(workspace, 'llm.json'), llmConfig('http://127.0.0.1:9/v1', 'unreachable'))
  const result = await run('python3', ['-I', '-B', path.join(root, 'server', 'verify_sampling.py'), 'sampling', workspace], workspace)
  const parsed = JSON.parse(result.stdout.trim().split('\n').at(-1) ?? '') as { checks: Check[] }
  const blocked = parsed.checks.find((item) => item.name === 'Environment blocked')!
  assert.ok(blocked, JSON.stringify(parsed.checks))
  assert.match(blocked.detail, /127\.0\.0\.1:9/)
})

test('Sampling reports import failure as a failed check', async (t) => {
  rejected(await candidate(t, 'raise ValueError("Controlled import failure")\n', { endpoint: false }), 'Load experiment')
})
