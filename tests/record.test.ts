import test from 'node:test'
import assert from 'node:assert/strict'
import { cp, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { run, root } from '../server/labs.js'
import type { Check } from '../shared/types.js'
import { bonusChecks, bonusPassed } from '../shared/checks.js'
import { llmConfig, startLlmStub, type StubBody } from './llm-stub.js'

// The test-only endpoint answers a catalog-valid record when the request is schema-enforced and prose otherwise.
const validRecord = JSON.stringify({ item: 'water filter', quantity: 12, unit: 'piece', urgency: 'high', requester: 'Mara' })
const reply = (body: StubBody) => body.response_format?.type === 'json_schema' ? { content: validRecord } : { content: `Here is the record you asked for: ${validRecord}` }

async function candidate(t: test.TestContext, source?: string, options: { endpoint?: boolean } = {}) {
  const workspace = await mkdtemp(path.join(os.tmpdir(), 'rankforge-record-'))
  t.after(() => rm(workspace, { recursive: true, force: true }))
  await cp(path.join(root, 'labs', 'record'), workspace, { recursive: true })
  if (source !== undefined) await writeFile(path.join(workspace, 'extract.py'), source)
  const stub = options.endpoint === false ? null : await startLlmStub({ reply })
  if (stub) { t.after(() => stub.close()); await writeFile(path.join(workspace, 'llm.json'), llmConfig(stub.baseUrl, stub.model)) }
  const result = await run('python3', ['-I', '-B', path.join(root, 'server', 'verify_record.py'), 'record', workspace], workspace)
  assert.notEqual(result.code, 124, result.stderr)
  const parsed = JSON.parse(result.stdout.trim().split('\n').at(-1) ?? '') as { checks: Check[] }
  assert.ok(parsed.checks.length, JSON.stringify(result))
  return { ...result, checks: parsed.checks, stub }
}
const solution = (name = 'interpreter') => readFile(path.join(root, 'tests', 'solutions', 'record', `${name}.py`), 'utf8')
function rejected(result: Awaited<ReturnType<typeof candidate>>, check: string) {
  assert.equal(result.code, 1, JSON.stringify(result.checks))
  assert.ok(result.checks.some((item) => !item.passed && item.name.includes(check)), JSON.stringify(result.checks))
}

test('Record: the starter is RED on every extraction requirement through the scripted adapter', async (t) => {
  const result = await candidate(t)
  for (const name of ['syntactic errors', 'separately from schema errors', 'absent from the catalog', 'repaired within the bound', 'repair request carries', 'retry bound holds', 'response_format json_schema', 'new optional field']) rejected(result, name)
  assert.equal(bonusPassed(result.checks), false)
  assert.ok(!result.checks.some((item) => item.name === 'Environment blocked'), 'A configured endpoint is not an environment problem')
})

for (const name of ['interpreter', 'fieldtable']) {
  test(`Record: the ${name} implementation is GREEN, earns the bonus and measures prompt-only versus schema-enforced validity on the test-only endpoint`, async (t) => {
    const result = await candidate(t, await solution(name))
    assert.equal(result.code, 0, JSON.stringify(result.checks))
    assert.equal(result.checks.length, 10)
    assert.ok(result.checks.every((item) => item.passed), JSON.stringify(result.checks))
    assert.equal(bonusPassed(result.checks), true)
    const live = result.checks.find((item) => item.name.startsWith('Live run'))!
    assert.match(live.detail, /test-only at http:\/\/127\.0\.0\.1:\d+\/v1/)
    assert.match(live.detail, /prompt-only: 0\/3 schema-valid, 0\/3 catalog-valid, 0\/3 exact/)
    assert.match(live.detail, /schema-enforced: 3\/3 schema-valid, 3\/3 catalog-valid, 1\/3 exact/)
    assert.equal(result.stub!.requests.length, 7, 'Verify pings the endpoint once, then runs three fixtures in each mode with max_repairs=0')
  })
}

const mutations: [string, string, string, string][] = [
  ['the catalog check removed', '    if entry is None:\n        return [f"domain: /item', '    if False:\n        return [f"domain: /item', 'absent from the catalog'],
  ['domain errors labelled as schema errors', 'f"domain: /unit', 'f"schema: /unit', 'separately from schema errors'],
  ['extra fields tolerated', 'elif schema.get("additionalProperties") is False:', 'elif False:', 'syntactic errors'],
  ['the optional notes field never checked', '            if key in properties:\n                _check(item', '            if key == "notes":\n                continue\n            if key in properties:\n                _check(item', 'syntactic errors'],
  ['a truncated answer parsed as complete', '    if finish_reason == "length":\n        return', '    if False:\n        return', 'repaired within the bound'],
  ['the repair request without the validation errors', '"Your previous answer was rejected:\\n" + "\\n".join(f"- {error}" for error in errors)', '"Your previous answer was rejected."', 'repair request carries'],
  ['one repair more than the bound', 'for attempt in range(max_repairs + 1):', 'for attempt in range(max_repairs + 2):', 'retry bound holds'],
  ['exhaustion accepted silently', 'return {"ok": False, "record": None, "errors": attempts[-1]["errors"]', 'return {"ok": True, "record": json.loads(attempts[-1]["content"]), "errors": []', 'retry bound holds'],
  ['response_format never sent', 'if schema_enforced else None', 'if False else None', 'response_format json_schema'],
  ['the schema argument ignored', '    schema = schema or load_schema()\n    response_format', '    schema = load_schema()\n    response_format', 'new optional field'],
]
for (const [name, before, after, check] of mutations) {
  test(`Record rejects ${name}`, async (t) => {
    const source = await solution()
    assert.ok(source.includes(before), `Mutation anchor missing: ${name}`)
    rejected(await candidate(t, source.replaceAll(before, after)), check)
  })
}

test('Record: treating a refusal as empty output passes the contract but misses the hidden bonus; the bonus never fails the run', async (t) => {
  const source = (await solution()).replace('    if refusal:\n        return [f"schema: the model refused instead of answering: {refusal}"], None\n', '')
  assert.notEqual(source, await solution())
  const result = await candidate(t, source)
  assert.equal(result.code, 0, JSON.stringify(result.checks))
  assert.equal(bonusChecks(result.checks).length, 1)
  assert.ok(bonusChecks(result.checks)[0]!.name.startsWith('bonus:'))
  assert.equal(bonusPassed(result.checks), false)
})

test('Record: no model id in llm.json is environment blocked, never a failure or a pass', async (t) => {
  const result = await candidate(t, await solution(), { endpoint: false })
  assert.equal(result.code, 1)
  const blocked = result.checks.find((item) => item.name === 'Environment blocked')!
  assert.ok(blocked, JSON.stringify(result.checks))
  assert.match(blocked.detail, /llm\.json/)
  assert.ok(result.checks.filter((item) => item.name !== 'Environment blocked' && !item.optional).every((item) => item.passed), 'The adapter checks still pass')
})

test('Record: an endpoint that does not answer is environment blocked with the address in the detail', async (t) => {
  const workspace = await mkdtemp(path.join(os.tmpdir(), 'rankforge-record-'))
  t.after(() => rm(workspace, { recursive: true, force: true }))
  await cp(path.join(root, 'labs', 'record'), workspace, { recursive: true })
  await writeFile(path.join(workspace, 'extract.py'), await solution('fieldtable'))
  await writeFile(path.join(workspace, 'llm.json'), llmConfig('http://127.0.0.1:9/v1', 'unreachable'))
  const result = await run('python3', ['-I', '-B', path.join(root, 'server', 'verify_record.py'), 'record', workspace], workspace)
  const parsed = JSON.parse(result.stdout.trim().split('\n').at(-1) ?? '') as { checks: Check[] }
  const blocked = parsed.checks.find((item) => item.name === 'Environment blocked')!
  assert.ok(blocked, JSON.stringify(parsed.checks))
  assert.match(blocked.detail, /127\.0\.0\.1:9/)
})

test('Record reports import failure as a failed check', async (t) => {
  rejected(await candidate(t, 'raise ValueError("Controlled import failure")\n', { endpoint: false }), 'Load extractor')
})
