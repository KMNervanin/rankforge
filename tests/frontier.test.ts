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
  const workspace = await mkdtemp(path.join(os.tmpdir(), 'rankforge-frontier-'))
  t.after(() => rm(workspace, { recursive: true, force: true }))
  await cp(path.join(root, 'labs', 'frontier'), workspace, { recursive: true })
  if (source !== undefined) await writeFile(path.join(workspace, 'frontier.py'), source)
  const stub = options.endpoint === false ? null : await startLlmStub({ reply: () => ({ content: 'Urgent.' }) })
  if (stub) { t.after(() => stub.close()); await writeFile(path.join(workspace, 'llm.json'), llmConfig(stub.baseUrl, stub.model)) }
  const result = await run('python3', ['-I', '-B', path.join(root, 'server', 'verify_frontier.py'), 'frontier', workspace], workspace)
  assert.notEqual(result.code, 124, result.stderr)
  const parsed = JSON.parse(result.stdout.trim().split('\n').at(-1) ?? '') as { checks: Check[] }
  assert.ok(parsed.checks.length, JSON.stringify(result))
  return { ...result, checks: parsed.checks, stub }
}
const solution = (name = 'records') => readFile(path.join(root, 'tests', 'solutions', 'frontier', `${name}.py`), 'utf8')
function rejected(result: Awaited<ReturnType<typeof candidate>>, check: string) {
  assert.equal(result.code, 1, JSON.stringify(result.checks))
  assert.ok(result.checks.some((item) => !item.passed && item.name.includes(check)), JSON.stringify(result.checks))
}
const requirements = ['same cases with the same settings', 'own runner', 'named reason', 'recomputes', 'Pareto', 'within tolerance', 'tighter latency budget']

test('Frontier: the starter is RED on every comparison requirement', async (t) => {
  const result = await candidate(t)
  for (const name of requirements) rejected(result, name)
  assert.equal(bonusPassed(result.checks), false)
  assert.ok(!result.checks.some((item) => item.name === 'Environment blocked'), 'A configured endpoint is not an environment problem')
})

for (const name of ['records', 'tabular']) {
  test(`Frontier: the ${name} implementation is GREEN on nine checks, earns the bonus and measures three live cases on the test-only endpoint`, async (t) => {
    const result = await candidate(t, await solution(name))
    assert.equal(result.code, 0, JSON.stringify(result.checks))
    assert.equal(result.checks.length, 9)
    assert.ok(result.checks.every((item) => item.passed), JSON.stringify(result.checks))
    assert.equal(bonusPassed(result.checks), true)
    const live = result.checks.find((item) => item.name.startsWith('Live run'))!
    assert.match(live.detail, /test-only at http:\/\/127\.0\.0\.1:\d+\/v1; 3 cases/)
    assert.match(live.detail, /[0-3]\/3 correct/)
    assert.equal(result.stub!.requests.length, 4, 'Verify makes one probe plus three requests through the learner runner')
  })
}

const mutations: [string, string, string, string][] = [
  ['half the set for every candidate after the first', '        for case in cases["cases"]:', '        for case in (cases["cases"] if not manifests else cases["cases"][: len(cases["cases"]) // 2]):', 'same cases with the same settings'],
  ['a per-candidate max_tokens tweak', 'outcome = runner(candidate["model"], case, settings)', 'outcome = runner(candidate["model"], case, dict(settings, max_tokens=settings["max_tokens"] + len(manifests)))', 'same cases with the same settings'],
  ['hash validation removed', '            if manifest[field] != first[field]:', '            if False:', 'named reason'],
  ['a summary block trusted over raw results', '        correct = sum(r["correct"] for r in results)', '        correct = manifest.get("summary", {}).get("correct", sum(r["correct"] for r in results))', 'recomputes'],
  ['percentiles taken by index instead of nearest rank', '    return ordered[(q * len(ordered) + 99) // 100 - 1]', '    return ordered[q * len(ordered) // 100]', 'recomputes'],
  ['dominance requiring strictly higher accuracy', 'at_least = other["accuracy"] >= row["accuracy"]', 'at_least = other["accuracy"] > row["accuracy"]', 'Pareto'],
  ['tolerance ignored', 'if row["accuracy"] + tolerance + 1e-9 < best["accuracy"]:', 'if row["accuracy"] < best["accuracy"]:', 'within tolerance'],
  ['a summary that cites no numbers', '"rejected": rejected, "summary": summary}', '"rejected": rejected, "summary": "Chose " + str(chosen["candidate"] if chosen else None) + " over " + best["candidate"] + "."}', 'cites measured numbers'],
  ['the latency budget ignored', 'elif row["p95_ms"] > budget["p95_ms"]:', 'elif False:', 'tighter latency budget'],
  ['tokens estimated from characters', '"input_tokens": int(usage["prompt_tokens"])', '"input_tokens": len(body) // 4', 'own runner'],
  ['correctness by substring', '"correct": 1 if normalize(content) == normalize(case["expected"]) else 0', '"correct": 1 if normalize(case["expected"]) in normalize(content) else 0', 'own runner'],
]
for (const [name, before, after, check] of mutations) {
  test(`Frontier rejects ${name}`, async (t) => {
    const source = await solution()
    assert.ok(source.includes(before), `Mutation anchor missing: ${name}`)
    rejected(await candidate(t, source.replaceAll(before, after)), check)
  })
}

test('Frontier: skipping the paired comparison passes the contract but misses the hidden bonus; the bonus never fails the run', async (t) => {
  const source = (await solution()).replace('        row["paired_vs_best"] = {"best": best["candidate"], **paired(by_candidate[row["candidate"]], by_candidate[best["candidate"]])}', '        pass')
  assert.notEqual(source, await solution())
  const result = await candidate(t, source)
  assert.equal(result.code, 0, JSON.stringify(result.checks))
  assert.equal(bonusChecks(result.checks).length, 1)
  assert.ok(bonusChecks(result.checks)[0]!.name.startsWith('bonus:'))
  assert.equal(bonusPassed(result.checks), false)
})

test('Frontier: no model id in llm.json is environment blocked, never a failure or a pass', async (t) => {
  const result = await candidate(t, await solution(), { endpoint: false })
  assert.equal(result.code, 1)
  const blocked = result.checks.find((item) => item.name === 'Environment blocked')!
  assert.ok(blocked, JSON.stringify(result.checks))
  assert.match(blocked.detail, /llm\.json/)
  assert.ok(result.checks.filter((item) => item.name !== 'Environment blocked' && !item.optional).every((item) => item.passed), 'The adapter checks still pass')
})

test('Frontier: an endpoint that does not answer is environment blocked with the address in the detail', async (t) => {
  const workspace = await mkdtemp(path.join(os.tmpdir(), 'rankforge-frontier-'))
  t.after(() => rm(workspace, { recursive: true, force: true }))
  await cp(path.join(root, 'labs', 'frontier'), workspace, { recursive: true })
  await writeFile(path.join(workspace, 'frontier.py'), await solution())
  await writeFile(path.join(workspace, 'llm.json'), llmConfig('http://127.0.0.1:9/v1', 'unreachable'))
  const result = await run('python3', ['-I', '-B', path.join(root, 'server', 'verify_frontier.py'), 'frontier', workspace], workspace)
  const parsed = JSON.parse(result.stdout.trim().split('\n').at(-1) ?? '') as { checks: Check[] }
  const blocked = parsed.checks.find((item) => item.name === 'Environment blocked')!
  assert.ok(blocked, JSON.stringify(parsed.checks))
  assert.match(blocked.detail, /127\.0\.0\.1:9/)
})

test('Frontier reports import failure as a failed check', async (t) => {
  rejected(await candidate(t, 'raise ValueError("Controlled import failure")\n', { endpoint: false }), 'Load frontier module')
})
