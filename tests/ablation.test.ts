import test from 'node:test'
import assert from 'node:assert/strict'
import { cp, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { run, root } from '../server/labs.js'
import type { Check } from '../shared/types.js'
import { bonusChecks, bonusPassed } from '../shared/checks.js'

// No live part: the runner is injected and Verify's runners are scripted, so no stub endpoint is needed.
async function candidate(t: test.TestContext, source?: string) {
  const workspace = await mkdtemp(path.join(os.tmpdir(), 'rankforge-ablation-'))
  t.after(() => rm(workspace, { recursive: true, force: true }))
  await cp(path.join(root, 'labs', 'ablation'), workspace, { recursive: true })
  if (source !== undefined) await writeFile(path.join(workspace, 'ablation.py'), source)
  const result = await run('python3', ['-I', '-B', path.join(root, 'server', 'verify_ablation.py'), 'ablation', workspace], workspace)
  assert.notEqual(result.code, 124, result.stderr)
  const parsed = JSON.parse(result.stdout.trim().split('\n').at(-1) ?? '') as { checks: Check[] }
  assert.ok(parsed.checks.length, JSON.stringify(result))
  return { ...result, checks: parsed.checks }
}
const solution = (name = 'pure') => readFile(path.join(root, 'tests', 'solutions', 'ablation', `${name}.py`), 'utf8')
function rejected(result: Awaited<ReturnType<typeof candidate>>, check: string) {
  assert.equal(result.code, 1, JSON.stringify(result.checks))
  assert.ok(result.checks.some((item) => !item.passed && item.name.includes(check)), JSON.stringify(result.checks))
}

test('Ablation: the starter is RED on every requirement', async (t) => {
  const result = await candidate(t)
  for (const name of ['full case set', 'paired standard error', 'keeps what measurably helps', 'Guards stay', 'Add-one-in', 'Transfer', 'Invalid input']) rejected(result, name)
  assert.equal(bonusPassed(result.checks), false)
  assert.ok(!result.checks.some((item) => item.name === 'Environment blocked'), 'Nothing in this mission depends on the environment')
})

for (const name of ['pure', 'matrix']) {
  test(`Ablation: the ${name} implementation is GREEN with the exact check count and earns the bonus`, async (t) => {
    const result = await candidate(t, await solution(name))
    assert.equal(result.code, 0, JSON.stringify(result.checks))
    assert.equal(result.checks.length, 8)
    assert.ok(result.checks.every((item) => item.passed), JSON.stringify(result.checks))
    assert.equal(bonusPassed(result.checks), true)
  })
}

const mutations: [string, string, string, string][] = [
  ['every row computed on every second case', '        ran = cases  # both arms, the whole set, every row', '        ran = cases[::2]', 'full case set'],
  ['a population variance instead of the sample variance', 'variance = sum((d - mean) ** 2 for d in diffs) / (n - 1)', 'variance = sum((d - mean) ** 2 for d in diffs) / n', 'paired standard error'],
  ['z hardcoded to 1.96 in the interval', 'return mean, se, mean - z * se, mean + z * se', 'return mean, se, mean - 1.96 * se, mean + 1.96 * se', 'Transfer'],
  ['a component kept on a positive mean instead of the interval', '        elif row["low"] > 0:', '        elif row["mean_delta"] > 0:', 'keeps what measurably helps'],
  ['a guard judged by its numbers', '        if component["kind"] == "guard":', '        if component["kind"] == "guard" and row["low"] > 0:', 'Guards stay'],
  ['the guard label dropped from the reason', 'f"kept for {component[\'reason\']}: a guard stays whatever its quality delta ({cited})"', 'f"kept as a guard whatever its quality delta ({cited})"', 'Guards stay'],
  ['the add-one-in strategy treated as leave-one-out', 'pool = names if strategy == "leave-one-out" else guards', 'pool = names', 'Add-one-in'],
  ['the token delta computed without minus with', 'tokens = [outcome(with_, case)["tokens"] - outcome(without, case)["tokens"] for case in ran]', 'tokens = [outcome(without, case)["tokens"] - outcome(with_, case)["tokens"] for case in ran]', 'paired standard error'],
  ['an unknown strategy accepted', '    if strategy not in STRATEGIES:', '    if False:', 'Invalid input'],
  ['the interval left out of the reason', 'interval = f"[{row[\'low\']:.3f}, {row[\'high\']:.3f}]"', 'interval = ""', 'keeps what measurably helps'],
]
for (const [name, before, after, check] of mutations) {
  test(`Ablation rejects ${name}`, async (t) => {
    const source = await solution()
    assert.ok(source.includes(before), `Mutation anchor missing: ${name}`)
    rejected(await candidate(t, source.replaceAll(before, after)), check)
  })
}

test('Ablation: a record without the comparison count passes the contract but misses the hidden bonus; the bonus never fails the run', async (t) => {
  const source = (await solution()).replace(',\n            "comparisons": len(table["rows"]), "z_adjusted": z_adjusted, "keep_adjusted": keep_adjusted}', '}')
  assert.notEqual(source, await solution())
  const result = await candidate(t, source)
  assert.equal(result.code, 0, JSON.stringify(result.checks))
  assert.equal(bonusChecks(result.checks).length, 1)
  assert.ok(bonusChecks(result.checks)[0]!.name.startsWith('bonus:'))
  assert.equal(bonusPassed(result.checks), false)
})

test('Ablation: a table fabricated without running the cases is RED on the full set and the numbers', async (t) => {
  const source = 'def ablate(components, cases, run, *, strategy="leave-one-out", z=1.96):\n    names = [c["name"] for c in components]\n    ids = [c["id"] for c in cases]\n    rows = [{"component": c["name"], "kind": c["kind"], "with": names, "without": [o for o in names if o != c["name"]], "cases": ids, "n": len(ids), "accuracy_with": 1.0, "accuracy_without": 0.5, "mean_delta": 0.5, "se": 0.1, "low": 0.3, "high": 0.7, "tokens_delta": 0.0, "latency_delta_ms": 0.0} for c in components]\n    return {"strategy": strategy, "z": z, "cases": ids, "reference": {"active": names, "n": len(ids), "accuracy": 1.0, "tokens": 0.0, "latency_ms": 0.0}, "rows": rows}\n\n\ndef decide(table, components):\n    decisions = [{"component": r["component"], "kind": r["kind"], "decision": "keep", "reason": "kept for cost [0.300, 0.700]", "n": r["n"], "mean_delta": r["mean_delta"], "low": r["low"], "high": r["high"], "tokens_delta": r["tokens_delta"], "latency_delta_ms": r["latency_delta_ms"]} for r in table["rows"]]\n    return {"strategy": table["strategy"], "z": table["z"], "n": len(table["cases"]), "keep": [d["component"] for d in decisions], "drop": [], "decisions": decisions}\n'
  const result = await candidate(t, source)
  for (const name of ['full case set', 'paired standard error', 'keeps what measurably helps', 'Transfer']) rejected(result, name)
})

test('Ablation reports import failure as a failed check', async (t) => {
  rejected(await candidate(t, 'raise ValueError("Controlled import failure")\n'), 'Load ablation module')
})
