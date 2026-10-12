import test from 'node:test'
import assert from 'node:assert/strict'
import { cp, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { run, root } from '../server/labs.js'
import type { Check } from '../shared/types.js'
import { bonusChecks, bonusPassed } from '../shared/checks.js'

// No live part: the embedding function is injected by the verifier, so no stub endpoint is needed.
async function candidate(t: test.TestContext, source?: string) {
  const workspace = await mkdtemp(path.join(os.tmpdir(), 'rankforge-reindex-'))
  t.after(() => rm(workspace, { recursive: true, force: true }))
  await cp(path.join(root, 'labs', 'reindex'), workspace, { recursive: true })
  if (source !== undefined) await writeFile(path.join(workspace, 'indexer.py'), source)
  const result = await run('python3', ['-I', '-B', path.join(root, 'server', 'verify_reindex.py'), 'reindex', workspace], workspace)
  assert.notEqual(result.code, 124, result.stderr)
  const parsed = JSON.parse(result.stdout.trim().split('\n').at(-1) ?? '') as { checks: Check[] }
  assert.ok(parsed.checks.length, JSON.stringify(result))
  return { ...result, checks: parsed.checks }
}
const solution = (name = 'versioned') => readFile(path.join(root, 'tests', 'solutions', 'reindex', `${name}.py`), 'utf8')
function rejected(result: Awaited<ReturnType<typeof candidate>>, check: string) {
  assert.equal(result.code, 1, JSON.stringify(result.checks))
  assert.ok(result.checks.some((item) => !item.passed && item.name.includes(check)), JSON.stringify(result.checks))
}

test('Reindex: the starter is RED on every archive-change requirement', async (t) => {
  const result = await candidate(t)
  for (const name of ['zero embed calls', 'never answered from its old version', 'deleted runbook', 'complete new version', 'atomic', 'Rollback', 'chunking', 'fresh process']) rejected(result, name)
  assert.equal(bonusPassed(result.checks), false)
  assert.ok(!result.checks.some((item) => item.name === 'Environment blocked'), 'Nothing in this mission depends on the environment')
})

for (const name of ['versioned', 'swap']) {
  test(`Reindex: the ${name} implementation is GREEN with the exact check count and earns the bonus`, async (t) => {
    const result = await candidate(t, await solution(name))
    assert.equal(result.code, 0, JSON.stringify(result.checks))
    assert.equal(result.checks.length, 9)
    assert.ok(result.checks.every((item) => item.passed), JSON.stringify(result.checks))
    assert.equal(bonusPassed(result.checks), true)
  })
}

const mutations: [string, string, string, string][] = [
  ['old chunks reachable after an update', 'AND d.version = c.doc_version AND d.deleted = 0 WHERE', 'AND d.deleted = 0 WHERE', 'never answered from its old version'],
  ['a deleted document keeping its chunks searchable', 'AND d.version = c.doc_version AND d.deleted = 0 WHERE', 'AND d.version = c.doc_version WHERE', 'deleted runbook'],
  ['the content hash never compared', 'existing["content_hash"] == digest and not existing["deleted"]', 'False', 'zero embed calls'],
  ['a rebuild that writes into the active version', 'rows.extend(self._rows(name, model, width,', 'rows.extend(self._rows(active["version"], model, width,', 'complete new version'],
  ['a switch split into two transactions', '        with self.conn:\n            self.conn.execute("UPDATE index_versions SET active = 0 WHERE active = 1")\n            self.conn.execute("UPDATE index_versions SET active = 1 WHERE version = ?", (target,))', '        with self.conn:\n            self.conn.execute("UPDATE index_versions SET active = 0 WHERE active = 1")\n        with self.conn:\n            self.conn.execute("UPDATE index_versions SET active = 1 WHERE version = ?", (target,))', 'atomic'],
  ['a rollback that re-activates the current version', 'self.switch(last["previous"])', 'self.switch(last["version"])', 'Rollback'],
  ['a chunk rule that ignores the chunking version', 'parts[start:start + width]', 'parts[start:start + 1]', 'chunking'],
  ['the query embedded with a fixed model instead of the version’s', 'self.embed([str(query)], model=row["embed_model"])', 'self.embed([str(query)], model="relay-embed-a")', 'atomic'],
]
for (const [name, before, after, check] of mutations) {
  test(`Reindex rejects ${name}`, async (t) => {
    const source = await solution()
    assert.ok(source.includes(before), `Mutation anchor missing: ${name}`)
    rejected(await candidate(t, source.replaceAll(before, after)), check)
  })
}

test('Reindex: switching to an incomplete version passes the contract but misses the hidden bonus; the bonus never fails the run', async (t) => {
  const source = (await solution()).replace('        if missing:\n            raise ValueError(f"index version {target!r} lacks current documents: {missing}")\n', '')
  assert.notEqual(source, await solution())
  const result = await candidate(t, source)
  assert.equal(result.code, 0, JSON.stringify(result.checks))
  assert.equal(bonusChecks(result.checks).length, 1)
  assert.ok(bonusChecks(result.checks)[0]!.name.startsWith('bonus:'))
  assert.equal(bonusPassed(result.checks), false)
})

test('Reindex: an indexer that answers nothing is RED on the archive, not GREEN by silence', async (t) => {
  const source = (await solution()).replace('for score, item in scored[:int(k)]]', 'for score, item in scored[:0]]')
  assert.notEqual(source, await solution())
  const result = await candidate(t, source)
  for (const name of ['zero embed calls', 'never answered from its old version', 'complete new version']) rejected(result, name)
})

test('Reindex reports import failure as a failed check', async (t) => {
  rejected(await candidate(t, 'raise ValueError("Controlled import failure")\n'), 'Load incremental indexer')
})
