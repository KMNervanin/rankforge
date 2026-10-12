import test from 'node:test'
import assert from 'node:assert/strict'
import { cp, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { run, root } from '../server/labs.js'
import type { Check } from '../shared/types.js'
import { bonusChecks, bonusPassed } from '../shared/checks.js'

// No live part: the verifier never opens a socket, so no stub endpoint is needed.
async function candidate(t: test.TestContext, source?: string) {
  const workspace = await mkdtemp(path.join(os.tmpdir(), 'rankforge-errorbars-'))
  t.after(() => rm(workspace, { recursive: true, force: true }))
  await cp(path.join(root, 'labs', 'errorbars'), workspace, { recursive: true })
  if (source !== undefined) await writeFile(path.join(workspace, 'metrics.py'), source)
  const result = await run('python3', ['-I', '-B', path.join(root, 'server', 'verify_errorbars.py'), 'errorbars', workspace], workspace)
  assert.notEqual(result.code, 124, result.stderr)
  const parsed = JSON.parse(result.stdout.trim().split('\n').at(-1) ?? '') as { checks: Check[] }
  assert.ok(parsed.checks.length, JSON.stringify(result))
  return { ...result, checks: parsed.checks }
}
const solution = (name = 'pure') => readFile(path.join(root, 'tests', 'solutions', 'errorbars', `${name}.py`), 'utf8')
function rejected(result: Awaited<ReturnType<typeof candidate>>, check: string) {
  assert.equal(result.code, 1, JSON.stringify(result.checks))
  assert.ok(result.checks.some((item) => !item.passed && item.name.includes(check)), JSON.stringify(result.checks))
}

test('Errorbars: the starter is RED on every metric requirement', async (t) => {
  const result = await candidate(t)
  for (const name of ['Field scores', 'Abstention accuracy', 'Wilson interval', '+2 points on 30 cases', 'Transfer', 'published rule is paired', 'Report composes', 'Misaligned case ids']) rejected(result, name)
  const thirty = result.checks.find((item) => item.name.includes('+2 points on 30 cases'))!
  assert.match(thirty.detail, /got 'better'/, 'The starter declares +2 points on 30 cases a win')
  assert.equal(bonusPassed(result.checks), false)
  assert.ok(!result.checks.some((item) => item.name === 'Environment blocked'), 'Nothing in this mission depends on the environment')
})

for (const name of ['pure', 'stats']) {
  test(`Errorbars: the ${name} implementation is GREEN with the exact check count and earns the bonus`, async (t) => {
    const result = await candidate(t, await solution(name))
    assert.equal(result.code, 0, JSON.stringify(result.checks))
    assert.equal(result.checks.length, 9)
    assert.ok(result.checks.every((item) => item.passed), JSON.stringify(result.checks))
    assert.equal(bonusPassed(result.checks), true)
  })
}

const mutations: [string, string, string, string][] = [
  ['normalization dropped', 'return " ".join(str(value).split()).casefold()', 'return str(value)', 'Field scores'],
  ['a mismatch counted only as a false negative', '            if got is not None:\n                counts[field]["fp"] += 1', '            if got is not None and wanted is None:\n                counts[field]["fp"] += 1', 'Field scores'],
  ['abstention divided by every case', 'expected = [case for case in ids if references[case] == ABSTAIN]', 'expected = list(ids)', 'Abstention accuracy'],
  ['the naive interval instead of Wilson', 'half = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / denominator', 'half = z * math.sqrt(p * (1 - p) / n)', 'Wilson interval'],
  ['a win declared on the sign of the mean', 'verdict = "better" if low > 0 else "worse" if high < 0 else "inconclusive"', 'verdict = "better" if mean > 0 else "worse" if mean < 0 else "inconclusive"', '+2 points on 30 cases'],
  ['the population standard deviation', '/ (n - 1)\n        se = math.sqrt(variance / n)', '/ n\n        se = math.sqrt(variance / n)', '+2 points on 30 cases'],
  ['two overlapping intervals as the rule', 'verdict = "better" if low > 0 else "worse" if high < 0 else "inconclusive"', 'verdict = "better" if wilson(round(sum(scores_b.values())), n, z)[0] > wilson(round(sum(scores_a.values())), n, z)[1] else "inconclusive"', 'published rule is paired'],
  ['always inconclusive', 'verdict = "better" if low > 0 else "worse" if high < 0 else "inconclusive"', 'verdict = "inconclusive"', 'Transfer'],
  ['case ids never aligned', '    if set(predictions) != set(references):', '    if False:', 'Misaligned case ids'],
  ['needed_n without the power term', 'return math.ceil((z + z_power) ** 2 * variance / (mean * mean))', 'return math.ceil(z ** 2 * variance / (mean * mean))', 'Report composes'],
]
for (const [name, before, after, check] of mutations) {
  test(`Errorbars rejects ${name}`, async (t) => {
    const source = await solution()
    assert.ok(source.includes(before), `Mutation anchor missing: ${name}`)
    rejected(await candidate(t, source.replaceAll(before, after)), check)
  })
}

test('Errorbars: ignoring clusters passes the contract but misses the hidden bonus; the bonus never fails the run', async (t) => {
  const source = (await solution()).replace('    if clusters is None:\n        variance', '    if True:\n        variance')
  assert.notEqual(source, await solution())
  const result = await candidate(t, source)
  assert.equal(result.code, 0, JSON.stringify(result.checks))
  assert.equal(bonusChecks(result.checks).length, 1)
  assert.ok(bonusChecks(result.checks)[0]!.name.startsWith('bonus:'))
  assert.equal(bonusPassed(result.checks), false)
})

test('Errorbars: a calculator that always reports a tight winning interval is RED on the comparison checks', async (t) => {
  const source = 'FIELDS = ("item", "quantity", "unit", "urgency")\n\n\ndef field_scores(predictions, references):\n    return {f: {"tp": 1, "fp": 0, "fn": 0, "precision": 1.0, "recall": 1.0, "f1": 1.0} for f in FIELDS}\n\n\ndef abstention_accuracy(predictions, references):\n    return {"n": 1, "correct": 1, "accuracy": 1.0, "low": 0.2, "high": 1.0}\n\n\ndef case_scores(predictions, references):\n    return {k: 1.0 for k in references}\n\n\ndef wilson(successes, n, z=1.96):\n    return 0.0, 1.0\n\n\ndef paired_comparison(scores_a, scores_b, z=1.96, clusters=None):\n    return {"n": len(scores_a), "mean_diff": 0.02, "se": 0.001, "low": 0.018, "high": 0.022, "verdict": "better"}\n\n\ndef report(run_a, run_b, z=1.96, clusters=None):\n    return {"n": len(run_a["references"]), "z": z, "a": {}, "b": {}, "paired": paired_comparison({}, {}), "needed_n": 10}\n'
  const result = await candidate(t, source)
  for (const name of ['Field scores', 'Wilson interval', '+2 points on 30 cases', 'published rule is paired', 'Misaligned case ids']) rejected(result, name)
})

test('Errorbars reports import failure as a failed check', async (t) => {
  rejected(await candidate(t, 'raise ValueError("Controlled import failure")\n'), 'Load metric calculator')
})
