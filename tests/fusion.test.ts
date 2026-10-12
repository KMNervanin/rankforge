import test from 'node:test'
import assert from 'node:assert/strict'
import { cp, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { run, root } from '../server/labs.js'
import type { Check } from '../shared/types.js'
import { bonusChecks, bonusPassed } from '../shared/checks.js'

// No live part: retrievers, the scorer and the clock are injected by the verifier, so no stub endpoint is needed.
async function candidate(t: test.TestContext, source?: string) {
  const workspace = await mkdtemp(path.join(os.tmpdir(), 'rankforge-fusion-'))
  t.after(() => rm(workspace, { recursive: true, force: true }))
  await cp(path.join(root, 'labs', 'fusion'), workspace, { recursive: true })
  if (source !== undefined) await writeFile(path.join(workspace, 'fusion.py'), source)
  const result = await run('python3', ['-I', '-B', path.join(root, 'server', 'verify_fusion.py'), 'fusion', workspace], workspace)
  assert.notEqual(result.code, 124, result.stderr)
  const parsed = JSON.parse(result.stdout.trim().split('\n').at(-1) ?? '') as { checks: Check[] }
  assert.ok(parsed.checks.length, JSON.stringify(result))
  return { ...result, checks: parsed.checks }
}
const solution = (name = 'tuples') => readFile(path.join(root, 'tests', 'solutions', 'fusion', `${name}.py`), 'utf8')
function rejected(result: Awaited<ReturnType<typeof candidate>>, check: string) {
  assert.equal(result.code, 1, JSON.stringify(result.checks))
  assert.ok(result.checks.some((item) => !item.passed && item.name.includes(check)), JSON.stringify(result.checks))
}

test('Fusion: the starter is RED on every fusion, rerank, measurement and decision requirement', async (t) => {
  const result = await candidate(t)
  for (const name of ['RRF matches', 'Ties break', 'Weighted fusion', 'exactly the top_n', 'clock latencies', 'p95 recompute', 'keeps a reranker that pays', 'never adopted', 'tighter latency budget']) rejected(result, name)
  assert.equal(bonusPassed(result.checks), false)
  assert.ok(!result.checks.some((item) => item.name === 'Environment blocked'), 'Nothing in this mission depends on the environment')
})

for (const name of ['tuples', 'exact']) {
  test(`Fusion: the ${name} implementation is GREEN with the exact check count and earns the bonus`, async (t) => {
    const result = await candidate(t, await solution(name))
    assert.equal(result.code, 0, JSON.stringify(result.checks))
    assert.equal(result.checks.length, 10)
    assert.ok(result.checks.every((item) => item.passed), JSON.stringify(result.checks))
    assert.equal(bonusPassed(result.checks), true)
  })
}

const mutations: [string, string, string, string][] = [
  ['k ignored in the reciprocal rank', 'weight / (k + rank)', 'weight / rank', 'RRF matches'],
  ['ranks counted from zero', 'for rank, (doc_id, _score) in enumerate(ranking, start=1):', 'for rank, (doc_id, _score) in enumerate(ranking, start=0):', 'RRF matches'],
  ['ties left to dict insertion order', 'key=lambda item: (-item[1], item[0])', 'key=lambda item: -item[1]', 'Ties break'],
  ['weighted fusion summing raw scores', 'for doc_id, value in _normalized(ranking).items():', 'for doc_id, value in ranking:', 'Weighted fusion'],
  ['the reranker applied to every candidate', '    head = list(candidates[:top_n])\n    tail = list(candidates[top_n:])', '    head = list(candidates)\n    tail = []', 'exactly the top_n'],
  ['latency read from the wall clock instead of the injected one', ' = clock()', ' = __import__("time").perf_counter()', 'clock latencies'],
  ['p95 reported as the maximum sample', 'position = max(1, math.ceil(p / 100 * len(ordered)))', 'position = len(ordered) if p > 50 else max(1, math.ceil(p / 100 * len(ordered)))', 'p95 recompute'],
  ['a miss counted as the last rank instead of zero', 'return sum(1.0 / rank for rank in ranks if rank) / len(ranks)', 'return sum(1.0 / (rank or len(ranks)) for rank in ranks) / len(ranks)', 'MRR gain'],
  ['the latency budget ignored by the decision', 'keep = gain >= min_gain and p95_reranked <= limit', 'keep = gain >= min_gain', 'tighter latency budget'],
  ['the minimum gain ignored by the decision', 'keep = gain >= min_gain and p95_reranked <= limit', 'keep = p95_reranked <= limit', 'keeps a reranker that pays'],
  ['the decision trusting the report summaries', 'gain = mrr([row["hit"]["reranked"] for row in rows]) - mrr([row["hit"]["fused"] for row in rows])', 'gain = report["mrr"]["reranked"] - report["mrr"]["fused"]', 'keeps a reranker that pays'],
  ['a report without samples not refused', '    if not samples.get("reranked") or not samples.get("fused"):\n        raise ValueError(', '    if False:\n        raise ValueError(', 'never adopted'],
]
for (const [name, before, after, check] of mutations) {
  test(`Fusion rejects ${name}`, async (t) => {
    const source = await solution()
    assert.ok(source.includes(before), `Mutation anchor missing: ${name}`)
    rejected(await candidate(t, source.replaceAll(before, after)), check)
  })
}

test('Fusion: RRF without per-list weights passes the contract but misses the hidden bonus; the bonus never fails the run', async (t) => {
  const source = (await solution()).replace(
    'def rrf(rankings, k=60, weights=None):\n    if k <= 0:\n        raise ValueError("k must be positive")\n    if weights is None:\n        weights = [1.0] * len(rankings)',
    'def rrf(rankings, k=60):\n    if k <= 0:\n        raise ValueError("k must be positive")\n    weights = [1.0] * len(rankings)',
  )
  assert.notEqual(source, await solution())
  const result = await candidate(t, source)
  assert.equal(result.code, 0, JSON.stringify(result.checks))
  assert.equal(bonusChecks(result.checks).length, 1)
  assert.ok(bonusChecks(result.checks)[0]!.name.startsWith('bonus:'))
  assert.equal(bonusPassed(result.checks), false)
})

test('Fusion reports import failure as a failed check', async (t) => {
  rejected(await candidate(t, 'raise ValueError("Controlled import failure")\n'), 'Load hybrid retriever')
})
