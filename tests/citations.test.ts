import test from 'node:test'
import assert from 'node:assert/strict'
import { cp, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { run, root } from '../server/labs.js'
import type { Check } from '../shared/types.js'
import { bonusChecks, bonusPassed } from '../shared/checks.js'
import { llmConfig, startLlmStub, type StubBody } from './llm-stub.js'

// The test-only endpoint cites the relay runbook verbatim for the answerable question and declines everything else.
const cited = 'Switch relay 4 off and wait 90 seconds before switching it on again [p1].\nSources:\n[p1] "wait 90 seconds, then switch it on again"'
const reply = (body: StubBody) => (body.messages ?? []).some((message) => String(message.content ?? '').includes('How long should the operator wait')) ? { content: cited } : { content: 'The archive does not answer this.' }

async function candidate(t: test.TestContext, source?: string, options: { endpoint?: boolean } = {}) {
  const workspace = await mkdtemp(path.join(os.tmpdir(), 'rankforge-citations-'))
  t.after(() => rm(workspace, { recursive: true, force: true }))
  await cp(path.join(root, 'labs', 'citations'), workspace, { recursive: true })
  if (source !== undefined) await writeFile(path.join(workspace, 'answer.py'), source)
  const stub = options.endpoint === false ? null : await startLlmStub({ reply })
  if (stub) { t.after(() => stub.close()); await writeFile(path.join(workspace, 'llm.json'), llmConfig(stub.baseUrl, stub.model)) }
  const result = await run('python3', ['-I', '-B', path.join(root, 'server', 'verify_citations.py'), 'citations', workspace], workspace)
  assert.notEqual(result.code, 124, result.stderr)
  const parsed = JSON.parse(result.stdout.trim().split('\n').at(-1) ?? '') as { checks: Check[] }
  assert.ok(parsed.checks.length, JSON.stringify(result))
  return { ...result, checks: parsed.checks, stub }
}
const solution = (name = 'inline') => readFile(path.join(root, 'tests', 'solutions', 'citations', `${name}.py`), 'utf8')
function rejected(result: Awaited<ReturnType<typeof candidate>>, check: string) {
  assert.equal(result.code, 1, JSON.stringify(result.checks))
  assert.ok(result.checks.some((item) => !item.passed && item.name.includes(check)), JSON.stringify(result.checks))
}

test('Citations: the starter is RED on every citation requirement through the scripted adapter', async (t) => {
  const result = await candidate(t)
  for (const name of ['empty passage set', 'request carries', 'cited answer', 'outside the retrieved set', 'verbatim span', 'retry bound holds', 'refusal abstains', 'Faithfulness', 'score of None', 'Transfer']) rejected(result, name)
  assert.equal(bonusPassed(result.checks), false)
  assert.ok(!result.checks.some((item) => item.name === 'Environment blocked'), 'A configured endpoint is not an environment problem')
})

for (const name of ['inline', 'footnote']) {
  test(`Citations: the ${name} implementation is GREEN, earns the bonus and measures two questions on the test-only endpoint`, async (t) => {
    const result = await candidate(t, await solution(name))
    assert.equal(result.code, 0, JSON.stringify(result.checks))
    assert.equal(result.checks.length, 12)
    assert.ok(result.checks.every((item) => item.passed), JSON.stringify(result.checks))
    assert.equal(bonusPassed(result.checks), true)
    const live = result.checks.find((item) => item.name.startsWith('Live run'))!
    assert.match(live.detail, /test-only at http:\/\/127\.0\.0\.1:\d+\/v1/)
    assert.match(live.detail, /Q \(answerable\): answered, 1 citation, 1\/1 verbatim, 1 claims, 1 request; Q \(unanswerable\): abstained after 1 request/)
    assert.equal(result.stub!.requests.length, 3, 'Verify pings the endpoint once, then asks two questions with no retry needed')
  })
}

const mutations: [string, string, string, string][] = [
  ['an unknown passage id accepted with the quote as its own evidence', 'passage = lookup.get(pid)', 'passage = lookup.get(pid) or {"text": citation["quote"]}', 'outside the retrieved set'],
  ['a paraphrased quote accepted', '        if start < 0:\n            problems.append(f"citation [{pid}] quotes', '        if start < -1:\n            problems.append(f"citation [{pid}] quotes', 'verbatim span'],
  ['whitespace in the passage not normalized before the span test', 'haystack = normalize(passage["text"])', 'haystack = passage["text"]', 'cited answer'],
  ['the retry bound hardcoded to one', 'max_retries=1):\n    conflicts = reconcile(passages)', 'max_retries=1):\n    max_retries = 1\n    conflicts = reconcile(passages)', 'retry bound holds'],
  ['a refusal retried instead of abstaining at once', '    if PHRASE in text.casefold():\n        return None', '    if False:\n        return None', 'refusal abstains'],
  ['an empty passage set still asked', '    if not passages:\n        return abstained(', '    if False:\n        return abstained(', 'empty passage set'],
  ['the judge ignored', 'verdict = bool(judge(claim, passages))', 'verdict = True', 'Faithfulness'],
  ['the conflict rule removed', '    for conflict in conflicts:\n        touched', '    for conflict in []:\n        touched', 'Transfer'],
  ['markers kept inside claims', 'flat = normalize(MARKER.sub("", body))', 'flat = normalize(body)', 'cited answer'],
  ['the abstention phrase never offered to the model', '    f"If the passages do not contain the answer, reply with exactly this sentence and nothing more: {PHRASE}\\n"\n', '    "If the passages do not contain the answer, say so.\\n"\n', 'request carries'],
]
for (const [name, before, after, check] of mutations) {
  test(`Citations rejects ${name}`, async (t) => {
    const source = await solution()
    assert.ok(source.includes(before), `Mutation anchor missing: ${name}`)
    rejected(await candidate(t, source.replaceAll(before, after)), check)
  })
}

test('Citations: citations without offsets pass the contract but miss the hidden bonus; the bonus never fails the run', async (t) => {
  const source = (await solution()).replace(', "start": start, "end": start + len(quote)}', '}')
  assert.notEqual(source, await solution())
  const result = await candidate(t, source)
  assert.equal(result.code, 0, JSON.stringify(result.checks))
  assert.equal(bonusChecks(result.checks).length, 1)
  assert.ok(bonusChecks(result.checks)[0]!.name.startsWith('bonus:'))
  assert.equal(bonusPassed(result.checks), false)
})

test('Citations: no model id in llm.json is environment blocked, never a failure or a pass', async (t) => {
  const result = await candidate(t, await solution(), { endpoint: false })
  assert.equal(result.code, 1)
  const blocked = result.checks.find((item) => item.name === 'Environment blocked')!
  assert.ok(blocked, JSON.stringify(result.checks))
  assert.match(blocked.detail, /llm\.json/)
  assert.ok(result.checks.filter((item) => item.name !== 'Environment blocked' && !item.optional).every((item) => item.passed), 'The adapter checks still pass')
})

test('Citations: an endpoint that does not answer is environment blocked with the address in the detail', async (t) => {
  const workspace = await mkdtemp(path.join(os.tmpdir(), 'rankforge-citations-'))
  t.after(() => rm(workspace, { recursive: true, force: true }))
  await cp(path.join(root, 'labs', 'citations'), workspace, { recursive: true })
  await writeFile(path.join(workspace, 'answer.py'), await solution())
  await writeFile(path.join(workspace, 'llm.json'), llmConfig('http://127.0.0.1:9/v1', 'unreachable'))
  const result = await run('python3', ['-I', '-B', path.join(root, 'server', 'verify_citations.py'), 'citations', workspace], workspace)
  const parsed = JSON.parse(result.stdout.trim().split('\n').at(-1) ?? '') as { checks: Check[] }
  const blocked = parsed.checks.find((item) => item.name === 'Environment blocked')!
  assert.ok(blocked, JSON.stringify(parsed.checks))
  assert.match(blocked.detail, /127\.0\.0\.1:9/)
})

test('Citations reports import failure as a failed check', async (t) => {
  rejected(await candidate(t, 'raise ValueError("Controlled import failure")\n', { endpoint: false }), 'Load answer module')
})
