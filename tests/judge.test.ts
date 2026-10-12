import test from 'node:test'
import assert from 'node:assert/strict'
import { cp, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { run, root } from '../server/labs.js'
import type { Check } from '../shared/types.js'
import { bonusChecks, bonusPassed } from '../shared/checks.js'
import { llmConfig, startLlmStub, type StubBody } from './llm-stub.js'

// The test-only endpoint plays a judge that passes any answer naming RB-17 or RB-02: one true positive, one false negative,
// one false positive and one true negative on Verify's four live fixtures, so the measurement reads 2/4, 1/2, 1/2.
const reply = (body: StubBody) => ({ content: (body.messages ?? []).some((message) => /RB-17|RB-02/.test(String(message.content ?? ''))) ? 'PASS' : 'FAIL' })

async function candidate(t: test.TestContext, source?: string, options: { endpoint?: boolean } = {}) {
  const workspace = await mkdtemp(path.join(os.tmpdir(), 'rankforge-judge-'))
  t.after(() => rm(workspace, { recursive: true, force: true }))
  await cp(path.join(root, 'labs', 'judge'), workspace, { recursive: true })
  if (source !== undefined) await writeFile(path.join(workspace, 'judge.py'), source)
  const stub = options.endpoint === false ? null : await startLlmStub({ reply })
  if (stub) { t.after(() => stub.close()); await writeFile(path.join(workspace, 'llm.json'), llmConfig(stub.baseUrl, stub.model)) }
  const result = await run('python3', ['-I', '-B', path.join(root, 'server', 'verify_judge.py'), 'judge', workspace], workspace)
  assert.notEqual(result.code, 124, result.stderr)
  const parsed = JSON.parse(result.stdout.trim().split('\n').at(-1) ?? '') as { checks: Check[] }
  assert.ok(parsed.checks.length, JSON.stringify(result))
  return { ...result, checks: parsed.checks, stub }
}
const solution = (name = 'urllib') => readFile(path.join(root, 'tests', 'solutions', 'judge', `${name}.py`), 'utf8')
function rejected(result: Awaited<ReturnType<typeof candidate>>, check: string) {
  assert.equal(result.code, 1, JSON.stringify(result.checks))
  assert.ok(result.checks.some((item) => !item.passed && item.name.includes(check)), JSON.stringify(result.checks))
}

test('Judge: the starter is RED on every calibration requirement through the scripted adapter', async (t) => {
  const result = await candidate(t)
  for (const name of ['Binary judge', 'parse failure', 'hand-computed values', 'calibration report', 'swapped order', 'position-biased', 'length-bias probe', 'pins judge_version', 'Transfer']) rejected(result, name)
  assert.equal(bonusPassed(result.checks), false)
  assert.ok(!result.checks.some((item) => item.name === 'Environment blocked'), 'A configured endpoint is not an environment problem')
})

for (const name of ['urllib', 'counter']) {
  test(`Judge: the ${name} implementation is GREEN, earns the bonus and measures four labeled fixtures on the test-only endpoint`, async (t) => {
    const result = await candidate(t, await solution(name))
    assert.equal(result.code, 0, JSON.stringify(result.checks))
    assert.equal(result.checks.length, 11)
    assert.ok(result.checks.every((item) => item.passed), JSON.stringify(result.checks))
    assert.equal(bonusPassed(result.checks), true)
    const live = result.checks.find((item) => item.name.startsWith('Live run'))!
    assert.match(live.detail, /test-only at http:\/\/127\.0\.0\.1:\d+\/v1/)
    assert.match(live.detail, /4\/4 parsed, agreement 2\/4, TPR 1\/2, TNR 1\/2/)
    assert.match(live.detail, /judge 'live-judge', prompt [0-9a-f]{12}/)
    assert.equal(result.stub!.requests.length, 5, 'Verify pings the endpoint once, then judges four fixtures once each')
  })
}

const mutations: [string, string, string, string][] = [
  ['a score parsed as a verdict', '    if token not in allowed:\n        raise JudgeParseError', '    if token not in allowed and not token[:1].isdigit():\n        raise JudgeParseError', 'parse failure'],
  ['an unknown pairwise letter mapped to a tie', '    return prompt, raw, _parse(raw, {"A", "B", "TIE"})', '    return prompt, raw, (raw.strip(STRIP).upper() if raw.strip(STRIP).upper() in {"A", "B"} else "TIE")', 'parse failure'],
  ['the order never swapped', '_pairwise_call(criterion, b, a, **options)', '_pairwise_call(criterion, a, b, **options)', 'swapped order'],
  ['a disagreement between orders counted as a win', 'if preferred_first == preferred_second == "a":', 'if "a" in (preferred_first, preferred_second):', 'position-biased'],
  ['TNR divided by every item', '"tnr": float(Fraction(tn, n_neg)) if n_neg else None', '"tnr": float(Fraction(tn, n_pos + n_neg)) if n_neg else None', 'hand-computed values'],
  ['the prompt hash taken over text that was never sent', '"prompt_hash": _sha256(prompt)', '"prompt_hash": _sha256(prompt + judge_version)', 'pins judge_version'],
  ['the judge version hardcoded', '{"judge_version": judge_version,', '{"judge_version": "v1",', 'pins judge_version'],
  ['an unlabeled criterion accepted', '    if classes != {True, False}:\n        raise UnlabeledCriterionError', '    if False:\n        raise UnlabeledCriterionError', 'Transfer'],
  ['the padded win reported inverted', '"padded_won": pair["result"] == "loss"', '"padded_won": pair["result"] == "win"', 'length-bias probe'],
  ['the report reduced to a mean score', '    rates = calibrate(verdicts, labels)\n', '    rates = {"mean_score": sum(10 * int(verdict["verdict"]) for verdict in verdicts) / len(verdicts), "n": len(verdicts)}\n', 'calibration report'],
]
for (const [name, before, after, check] of mutations) {
  test(`Judge rejects ${name}`, async (t) => {
    const source = await solution()
    assert.ok(source.includes(before), `Mutation anchor missing: ${name}`)
    rejected(await candidate(t, source.replaceAll(before, after)), check)
  })
}

test('Judge: a judge without the self-consistency probe passes the contract but misses the hidden bonus; the bonus never fails the run', async (t) => {
  const source = (await solution()).replace('def consistency_probe(', 'def _no_consistency_probe(')
  assert.notEqual(source, await solution())
  const result = await candidate(t, source)
  assert.equal(result.code, 0, JSON.stringify(result.checks))
  assert.equal(bonusChecks(result.checks).length, 1)
  assert.ok(bonusChecks(result.checks)[0]!.name.startsWith('bonus:'))
  assert.equal(bonusPassed(result.checks), false)
})

test('Judge: no model id in llm.json is environment blocked, never a failure or a pass', async (t) => {
  const result = await candidate(t, await solution(), { endpoint: false })
  assert.equal(result.code, 1)
  const blocked = result.checks.find((item) => item.name === 'Environment blocked')!
  assert.ok(blocked, JSON.stringify(result.checks))
  assert.match(blocked.detail, /llm\.json/)
  assert.ok(result.checks.filter((item) => item.name !== 'Environment blocked' && !item.optional).every((item) => item.passed), 'The adapter checks still pass')
})

test('Judge: an endpoint that does not answer is environment blocked with the address in the detail', async (t) => {
  const workspace = await mkdtemp(path.join(os.tmpdir(), 'rankforge-judge-'))
  t.after(() => rm(workspace, { recursive: true, force: true }))
  await cp(path.join(root, 'labs', 'judge'), workspace, { recursive: true })
  await writeFile(path.join(workspace, 'judge.py'), await solution('counter'))
  await writeFile(path.join(workspace, 'llm.json'), llmConfig('http://127.0.0.1:9/v1', 'unreachable'))
  const result = await run('python3', ['-I', '-B', path.join(root, 'server', 'verify_judge.py'), 'judge', workspace], workspace)
  const parsed = JSON.parse(result.stdout.trim().split('\n').at(-1) ?? '') as { checks: Check[] }
  const blocked = parsed.checks.find((item) => item.name === 'Environment blocked')!
  assert.ok(blocked, JSON.stringify(parsed.checks))
  assert.match(blocked.detail, /127\.0\.0\.1:9/)
})

test('Judge reports import failure as a failed check', async (t) => {
  rejected(await candidate(t, 'raise ValueError("Controlled import failure")\n', { endpoint: false }), 'Load judge')
})
