import test from 'node:test'
import assert from 'node:assert/strict'
import { cp, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { run, root } from '../server/labs.js'
import type { Check } from '../shared/types.js'
import { bonusChecks, bonusPassed } from '../shared/checks.js'

// No live part: the vectors are seeded inside the verifier, so no stub endpoint is needed.
async function candidate(t: test.TestContext, source?: string) {
  const workspace = await mkdtemp(path.join(os.tmpdir(), 'rankforge-annindex-'))
  t.after(() => rm(workspace, { recursive: true, force: true }))
  await cp(path.join(root, 'labs', 'annindex'), workspace, { recursive: true })
  if (source !== undefined) await writeFile(path.join(workspace, 'annindex.py'), source)
  const result = await run('python3', ['-I', '-B', path.join(root, 'server', 'verify_annindex.py'), 'annindex', workspace], workspace)
  assert.notEqual(result.code, 124, result.stderr)
  const parsed = JSON.parse(result.stdout.trim().split('\n').at(-1) ?? '') as { checks: Check[] }
  assert.ok(parsed.checks.length, JSON.stringify(result))
  return { ...result, checks: parsed.checks }
}
const solution = (name = 'ivf') => readFile(path.join(root, 'tests', 'solutions', 'annindex', `${name}.py`), 'utf8')
function rejected(result: Awaited<ReturnType<typeof candidate>>, check: string) {
  assert.equal(result.code, 1, JSON.stringify(result.checks))
  assert.ok(result.checks.some((item) => !item.passed && item.name.includes(check)), JSON.stringify(result.checks))
}

test('Annindex: the starter is RED on the filter count, the recall report, the timings and the tenfold archive', async (t) => {
  const result = await candidate(t)
  for (const name of ['k results or says fewer', 'Recall@k meets', 'latency are measured', 'Tenfold']) rejected(result, name)
  assert.equal(bonusPassed(result.checks), false)
  assert.ok(!result.checks.some((item) => item.name === 'Environment blocked'), 'Nothing in this mission depends on the environment')
})

for (const name of ['ivf', 'lsh']) {
  test(`Annindex: the ${name} implementation is GREEN with the exact check count and earns the bonus`, async (t) => {
    const result = await candidate(t, await solution(name))
    assert.equal(result.code, 0, JSON.stringify(result.checks))
    assert.equal(result.checks.length, 7)
    assert.ok(result.checks.every((item) => item.passed), JSON.stringify(result.checks))
    assert.equal(bonusPassed(result.checks), true)
    const transfer = result.checks.find((item) => item.name.startsWith('Tenfold'))!
    assert.match(transfer.detail, /meets the bound with \{'lists': 64/)
  })
}

const mutations: [string, string, string, string][] = [
  ['a fixed candidate list filtered afterwards', 'while position < len(order) and (position < self.probes or len(found) < k):', 'while position < len(order) and position < self.probes:', 'k results or says fewer'],
  ['the access filter ignored', 'partitions = list(self.partitions.values()) if outpost is None else [self.partitions[outpost]] if outpost in self.partitions else []', 'partitions = list(self.partitions.values())', 'never returns another outpost'],
  ['truncated never reported', '"truncated": len(results) < k, "scanned": scanned}', '"truncated": False, "scanned": scanned}', 'k results or says fewer'],
  ['a bare dot product on vectors of different length', 'self.rows = [(str(item["id"]), item["outpost"], unit(item["vector"])) for item in items]', 'self.rows = [(str(item["id"]), item["outpost"], list(item["vector"])) for item in items]', 'Exact search matches'],
  ['recall hardcoded in the report', '"recall_mean": sum(recalls) / len(recalls) if recalls else 1.0', '"recall_mean": 1.0', 'Recall@k meets'],
  ['the most accurate params chosen instead of the cheapest', 'if meets and (best is None or report["scanned_mean"] < best[1]["scanned_mean"]):', 'if meets:', 'Recall@k meets'],
  ['the seed ignored', 'rng = random.Random(self.seed)', 'rng = random.Random()', 'Recall@k meets'],
  ['build time never measured', 'self.build_seconds = time.perf_counter() - started', 'self.build_seconds = 0.0', 'latency are measured'],
  ['no params reported although a candidate meets the bound', 'return {"params": best[0] if best else None,', 'return {"params": None,', 'Tenfold'],
]
for (const [name, before, after, check] of mutations) {
  test(`Annindex rejects ${name}`, async (t) => {
    const source = await solution()
    assert.ok(source.includes(before), `Mutation anchor missing: ${name}`)
    rejected(await candidate(t, source.replaceAll(before, after)), check)
  })
}

test('Annindex: a report without the per-outpost breakdown passes the contract but misses the hidden bonus; the bonus never fails the run', async (t) => {
  const source = (await solution()).replace('"per_outpost": {outpost: sum(values) / len(values) for outpost, values in per_outpost.items()},', '')
  assert.notEqual(source, await solution())
  const result = await candidate(t, source)
  assert.equal(result.code, 0, JSON.stringify(result.checks))
  assert.equal(bonusChecks(result.checks).length, 1)
  assert.ok(bonusChecks(result.checks)[0]!.name.startsWith('bonus:'))
  assert.equal(bonusPassed(result.checks), false)
})

test('Annindex reports import failure as a failed check', async (t) => {
  rejected(await candidate(t, 'raise ValueError("Controlled import failure")\n'), 'Load approximate index')
})
