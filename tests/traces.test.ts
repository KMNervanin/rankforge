import test from 'node:test'
import assert from 'node:assert/strict'
import { cp, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { run, root } from '../server/labs.js'
import type { Check } from '../shared/types.js'
import { bonusChecks, bonusPassed } from '../shared/checks.js'

// No live part: the mission is offline, so there is no llm.json and no stub endpoint.
const solutionDir = path.join(root, 'tests', 'solutions', 'traces')

async function candidate(t: test.TestContext, source?: string, options: { reading?: boolean; annotations?: string } = {}) {
  const workspace = await mkdtemp(path.join(os.tmpdir(), 'rankforge-traces-'))
  t.after(() => rm(workspace, { recursive: true, force: true }))
  await cp(path.join(root, 'labs', 'traces'), workspace, { recursive: true })
  if (source !== undefined) await writeFile(path.join(workspace, 'taxonomy.py'), source)
  if (options.reading !== false && source !== undefined) {
    await cp(path.join(solutionDir, 'annotations.jsonl'), path.join(workspace, 'annotations.jsonl'))
    await cp(path.join(solutionDir, 'taxonomy.json'), path.join(workspace, 'taxonomy.json'))
  }
  if (options.annotations !== undefined) await writeFile(path.join(workspace, 'annotations.jsonl'), options.annotations)
  const started = Date.now()
  const result = await run('python3', ['-I', '-B', path.join(root, 'server', 'verify_traces.py'), 'traces', workspace], workspace)
  assert.notEqual(result.code, 124, result.stderr)
  const parsed = JSON.parse(result.stdout.trim().split('\n').at(-1) ?? '') as { checks: Check[] }
  assert.ok(parsed.checks.length, JSON.stringify(result))
  return { ...result, checks: parsed.checks, elapsed: Date.now() - started }
}
const solution = (name = 'ledger') => readFile(path.join(solutionDir, `${name}.py`), 'utf8')
function rejected(result: Awaited<ReturnType<typeof candidate>>, check: string) {
  assert.equal(result.code, 1, JSON.stringify(result.checks))
  assert.ok(result.checks.some((item) => !item.passed && item.name.includes(check)), JSON.stringify(result.checks))
}

test('Traces: the starter is RED on every reading and reconciliation requirement', async (t) => {
  const result = await candidate(t)
  for (const name of ['Annotations load', 'Taxonomy counts', 'planted inconsistency', 'no trace references', 'Coverage', 'Recurrence', 'workspace annotations cover', 'workspace taxonomy reconciles']) rejected(result, name)
  assert.equal(bonusPassed(result.checks), false)
})

for (const name of ['ledger', 'sqlite']) {
  test(`Traces: the ${name} implementation with the reference reading is GREEN and earns the bonus`, async (t) => {
    const result = await candidate(t, await solution(name))
    assert.equal(result.code, 0, JSON.stringify(result.checks))
    assert.equal(result.checks.length, 11)
    assert.ok(result.checks.every((item) => item.passed), JSON.stringify(result.checks))
    assert.equal(bonusPassed(result.checks), true)
    assert.ok(result.elapsed < 20000, `Verify took ${result.elapsed} ms`)
    const agreement = result.checks.find((item) => item.name.includes('agree with the recorded outcomes'))!
    assert.match(agreement.detail, /120 of 120 pass-or-failure decisions agree/)
  })
}

const mutations: [string, string, string, string][] = [
  ['a duplicated trace id accepted', '            if trace_id in seen:\n                raise ValueError(f"{trace_id}: annotated twice")', '            if False:\n                raise ValueError(f"{trace_id}: annotated twice")', 'Annotations load'],
  ['a list of labels reduced to its first element', '            if not isinstance(label, str) or not label.strip():', '            if isinstance(label, list) and label:\n                label = str(label[0])\n            if not isinstance(label, str) or not label.strip():', 'Annotations load'],
  ['pass counted as a category', '        if record["first_failure"] != "pass":\n            groups.setdefault', '        if True:\n            groups.setdefault', 'Taxonomy counts'],
  ['the count taken from the taxonomy instead of the citations', '        if category.get("count") != len(set(ids)):', '        if False:', 'planted inconsistency'],
  ['an unknown trace id tolerated', '                problems.append(f"unknown: category {name!r} cites {trace_id}, which has no annotation")', '                pass', 'planted inconsistency'],
  ['the totals never compared with the annotations', '    if taxonomy.get("total") != len(annotations) or taxonomy.get("passes") != passes or failures + passes != taxonomy.get("total"):', '    if False:', 'planted inconsistency'],
  ['a category without trace references tolerated', '        if not ids:\n            problems.append(f"empty:', '        if False:\n            problems.append(f"empty:', 'no trace references'],
  ['the hundred-trace bound lowered', 'MIN_TRACES = 100', 'MIN_TRACES = 50', 'Coverage'],
  ['the thirty-note bound lowered', 'HAND_NOTES = 30', 'HAND_NOTES = 20', 'Coverage'],
  ['recurrence copying the taxonomy counts', '"recurring": {name: counts[name] for name in names if counts[name]},', '"recurring": {category["name"]: category["count"] for category in taxonomy.get("categories", []) if counts[category["name"]]},', 'Recurrence'],
]
for (const [name, before, after, check] of mutations) {
  test(`Traces rejects ${name}`, async (t) => {
    const source = await solution()
    assert.ok(source.includes(before), `Mutation anchor missing: ${name}`)
    rejected(await candidate(t, source.replaceAll(before, after)), check)
  })
}

test('Traces: labelling every shipped trace as pass fails the agreement check even with notes on the first 30', async (t) => {
  const lines = Array.from({ length: 120 }, (_, index) => JSON.stringify({ trace_id: `tr-${String(index + 1).padStart(4, '0')}`, open_note: index < 30 ? 'looks fine' : '', first_failure: 'pass' }))
  const result = await candidate(t, await solution(), { annotations: lines.join('\n') + '\n' })
  rejected(result, 'agree with the recorded outcomes')
  assert.ok(result.checks.find((item) => item.name.includes('workspace annotations cover'))!.passed, 'Coverage alone is satisfied by an all-pass file')
})

test('Traces: ignoring the example rule passes the contract but misses the hidden bonus; the bonus never fails the run', async (t) => {
  const source = (await solution()).replace('        example = TRACE_ID.search(str(category.get("definition") or ""))\n        if example is None or example.group(0) not in ids:\n            problems.append(f"example: category {name!r} should cite one of its own traces in its definition")\n', '')
  assert.notEqual(source, await solution())
  const result = await candidate(t, source)
  assert.equal(result.code, 0, JSON.stringify(result.checks))
  assert.equal(bonusChecks(result.checks).length, 1)
  assert.ok(bonusChecks(result.checks)[0]!.name.startsWith('bonus:'))
  assert.equal(bonusPassed(result.checks), false)
})

test('Traces reports import failure as a failed check', async (t) => {
  rejected(await candidate(t, 'raise ValueError("Controlled import failure")\n'), 'Load taxonomy module')
})
