import test from 'node:test'
import assert from 'node:assert/strict'
import { cp, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { run, root } from '../server/labs.js'
import type { Check } from '../shared/types.js'
import { bonusChecks, bonusPassed } from '../shared/checks.js'
import { llmConfig, startLlmStub } from './llm-stub.js'

async function candidate(t: test.TestContext, source?: string, options: { endpoint?: boolean } = {}) {
  const workspace = await mkdtemp(path.join(os.tmpdir(), 'rankforge-price-'))
  t.after(() => rm(workspace, { recursive: true, force: true }))
  await cp(path.join(root, 'labs', 'price'), workspace, { recursive: true })
  if (source !== undefined) await writeFile(path.join(workspace, 'client.py'), source)
  const stub = options.endpoint === false ? null : await startLlmStub()
  if (stub) { t.after(() => stub.close()); await writeFile(path.join(workspace, 'llm.json'), llmConfig(stub.baseUrl, stub.model)) }
  const result = await run('python3', ['-I', '-B', path.join(root, 'server', 'verify_price.py'), 'price', workspace], workspace)
  assert.notEqual(result.code, 124, result.stderr)
  const parsed = JSON.parse(result.stdout.trim().split('\n').at(-1) ?? '') as { checks: Check[] }
  assert.ok(parsed.checks.length, JSON.stringify(result))
  return { ...result, checks: parsed.checks, stub }
}
const solution = (name = 'urllib') => readFile(path.join(root, 'tests', 'solutions', 'price', `${name}.py`), 'utf8')
function rejected(result: Awaited<ReturnType<typeof candidate>>, check: string) {
  assert.equal(result.code, 1, JSON.stringify(result.checks))
  assert.ok(result.checks.some((item) => !item.passed && item.name.includes(check)), JSON.stringify(result.checks))
}

test('Price: the starter is RED on every metered requirement through the recording adapter', async (t) => {
  const result = await candidate(t)
  for (const name of ['parameters sent', 'Usage and finish reason', 'Cost follows', 'Latency', 'refused before sending', 'appends one JSON line']) rejected(result, name)
  assert.equal(bonusPassed(result.checks), false)
  assert.ok(!result.checks.some((item) => item.name === 'Environment blocked'), 'A configured endpoint is not an environment problem')
})

for (const name of ['urllib', 'httpclient']) {
  test(`Price: the ${name} implementation is GREEN, earns the bonus and reconciles one live call with the test-only endpoint`, async (t) => {
    const result = await candidate(t, await solution(name))
    assert.equal(result.code, 0, JSON.stringify(result.checks))
    assert.equal(result.checks.length, 8)
    assert.ok(result.checks.every((item) => item.passed), JSON.stringify(result.checks))
    assert.equal(bonusPassed(result.checks), true)
    const live = result.checks.find((item) => item.name.startsWith('Live call'))!
    assert.match(live.detail, /test-only at http:\/\/127\.0\.0\.1:\d+\/v1/)
    assert.equal(result.stub!.requests.length, 2, 'Verify makes its own direct request plus one through the client')
  })
}

const mutations: [string, string, string, string][] = [
  ['cost estimated from characters', 'cost = ((input_tokens - cached_tokens)', 'cost = ((len(prompt) // 4 - cached_tokens)', 'Cost follows'],
  ['finish reason hardcoded', '"finish_reason": choice["finish_reason"]', '"finish_reason": "stop"', 'Usage and finish reason'],
  ['window checked only after the request', '    if bound + max_tokens > int(prices["context_window"]):\n        raise WindowError', '    if False:\n        raise WindowError', 'refused before sending'],
  ['character bound instead of a byte bound', 'len(prompt.encode("utf-8"))', 'len(prompt)', 'refused before sending'],
  ['latency measured around parsing only', '    started = time.perf_counter()\n    with urllib', '    with urllib', 'Latency'],
  ['temperature not sent', '"max_tokens": max_tokens, "temperature": temperature}', '"max_tokens": max_tokens}', 'parameters sent'],
  ['log overwritten on every call', 'open(log_path, "a"', 'open(log_path, "w"', 'appends one JSON line'],
  ['total tokens logged as input tokens', 'input_tokens = int(usage["prompt_tokens"])', 'input_tokens = int(usage["total_tokens"])', 'Usage and finish reason'],
  ['prices read from a constant instead of the manifest', 'prices = _prices(manifest, model)', 'prices = {"context_window": 4096, "input_price_per_million": 0.15, "output_price_per_million": 0.6}', 'Cost follows'],
]
for (const [name, before, after, check] of mutations) {
  test(`Price rejects ${name}`, async (t) => {
    const source = await solution()
    assert.ok(source.includes(before), `Mutation anchor missing: ${name}`)
    rejected(await candidate(t, source.replaceAll(before, after)), check)
  })
}

test('Price: ignoring cached tokens passes the contract but misses the hidden bonus; the bonus never fails the run', async (t) => {
  const source = (await solution()).replace('cached_tokens = int((usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0)', 'cached_tokens = 0')
  assert.notEqual(source, await solution())
  const result = await candidate(t, source)
  assert.equal(result.code, 0, JSON.stringify(result.checks))
  assert.equal(bonusChecks(result.checks).length, 1)
  assert.ok(bonusChecks(result.checks)[0]!.name.startsWith('bonus:'))
  assert.equal(bonusPassed(result.checks), false)
})

test('Price: no model id in llm.json is environment blocked, never a failure or a pass', async (t) => {
  const result = await candidate(t, await solution(), { endpoint: false })
  assert.equal(result.code, 1)
  const blocked = result.checks.find((item) => item.name === 'Environment blocked')!
  assert.ok(blocked, JSON.stringify(result.checks))
  assert.match(blocked.detail, /llm\.json/)
  assert.ok(result.checks.filter((item) => item.name !== 'Environment blocked' && !item.optional).every((item) => item.passed), 'The adapter checks still pass')
})

test('Price: an endpoint that does not answer is environment blocked with the address in the detail', async (t) => {
  const workspace = await mkdtemp(path.join(os.tmpdir(), 'rankforge-price-'))
  t.after(() => rm(workspace, { recursive: true, force: true }))
  await cp(path.join(root, 'labs', 'price'), workspace, { recursive: true })
  await writeFile(path.join(workspace, 'client.py'), await solution())
  await writeFile(path.join(workspace, 'llm.json'), llmConfig('http://127.0.0.1:9/v1', 'unreachable'))
  const result = await run('python3', ['-I', '-B', path.join(root, 'server', 'verify_price.py'), 'price', workspace], workspace)
  const parsed = JSON.parse(result.stdout.trim().split('\n').at(-1) ?? '') as { checks: Check[] }
  const blocked = parsed.checks.find((item) => item.name === 'Environment blocked')!
  assert.ok(blocked, JSON.stringify(parsed.checks))
  assert.match(blocked.detail, /127\.0\.0\.1:9/)
})

test('Price reports import failure as a failed check', async (t) => {
  rejected(await candidate(t, 'raise ValueError("Controlled import failure")\n', { endpoint: false }), 'Load metered client')
})
