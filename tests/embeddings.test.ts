import test from 'node:test'
import assert from 'node:assert/strict'
import { cp, mkdtemp, readdir, readFile, rm, writeFile } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { run, root } from '../server/labs.js'
import type { Check } from '../shared/types.js'
import { bonusChecks, bonusPassed } from '../shared/checks.js'
import { llmConfig, startLlmStub } from './llm-stub.js'

// Test-only embedding: four dimensions from character codes, L2-normalized. It is never a model.
function unitFromText(text: string): number[] {
  const raw = [0, 0, 0, 0]
  for (let i = 0; i < text.length; i += 1) raw[i % 4] += ((text.charCodeAt(i) % 17) - 8) / 8
  const norm = Math.sqrt(raw.reduce((sum, value) => sum + value * value, 0)) || 1
  return raw.map((value) => value / norm)
}
const EMBEDDING_MODEL = 'test-only-embed'
const embeddingConfig = (baseUrl: string) => JSON.stringify({ base_url: baseUrl, model: 'test-only', embedding_model: EMBEDDING_MODEL })

async function candidate(t: test.TestContext, source?: string, options: { endpoint?: boolean | 'chat-only' } = {}) {
  const workspace = await mkdtemp(path.join(os.tmpdir(), 'rankforge-embeddings-'))
  t.after(() => rm(workspace, { recursive: true, force: true }))
  await cp(path.join(root, 'labs', 'embeddings'), workspace, { recursive: true })
  if (source !== undefined) await writeFile(path.join(workspace, 'store.py'), source)
  const stub = options.endpoint === false ? null : await startLlmStub(options.endpoint === 'chat-only' ? {} : { embeddings: unitFromText })
  if (stub) {
    t.after(() => stub.close())
    await writeFile(path.join(workspace, 'llm.json'), options.endpoint === 'chat-only' ? llmConfig(stub.baseUrl, stub.model) : embeddingConfig(stub.baseUrl))
  }
  const result = await run('python3', ['-I', '-B', path.join(root, 'server', 'verify_embeddings.py'), 'embeddings', workspace], workspace)
  assert.notEqual(result.code, 124, result.stderr)
  const parsed = JSON.parse(result.stdout.trim().split('\n').at(-1) ?? '') as { checks: Check[] }
  assert.ok(parsed.checks.length, JSON.stringify(result))
  return { ...result, checks: parsed.checks, stub }
}
const solution = (name = 'jsonrows') => readFile(path.join(root, 'tests', 'solutions', 'embeddings', `${name}.py`), 'utf8')
function rejected(result: Awaited<ReturnType<typeof candidate>>, check: string) {
  assert.equal(result.code, 1, JSON.stringify(result.checks))
  assert.ok(result.checks.some((item) => !item.passed && item.name.includes(check)), JSON.stringify(result.checks))
}

test('Embeddings: the starter is RED on every store requirement through the scripted adapter', async (t) => {
  const result = await candidate(t)
  for (const name of ['Cosine similarity', 'Ingest sends', 'Top-k', 'compared by cosine', 'refused on add', 'persists on disk', 're_embed']) rejected(result, name)
  assert.equal(bonusPassed(result.checks), false)
  assert.ok(!result.checks.some((item) => item.name === 'Environment blocked'), 'A configured endpoint is not an environment problem')
})

for (const name of ['jsonrows', 'unitblobs']) {
  test(`Embeddings: the ${name} implementation is GREEN, earns the bonus and measures a live embedding against the test-only endpoint`, async (t) => {
    const result = await candidate(t, await solution(name))
    assert.equal(result.code, 0, JSON.stringify(result.checks))
    assert.equal(result.checks.length, 9)
    assert.ok(result.checks.every((item) => item.passed), JSON.stringify(result.checks))
    assert.equal(bonusPassed(result.checks), true)
    const live = result.checks.find((item) => item.name.startsWith('Live embeddings'))!
    assert.match(live.detail, /test-only-embed at http:\/\/127\.0\.0\.1:\d+\/v1; dimension 4;/)
    assert.equal(result.stub!.requests.length, 3, 'Verify makes its own direct request, then one ingest batch and one query through the store')
  })
}

const mutations: [string, string, string, string][] = [
  ['ties broken by id descending', 'scored.sort(key=lambda item: (-item[1], item[0]))', 'scored.sort(key=lambda item: (-item[1], [-ord(c) for c in item[0]]))', 'Top-k'],
  ['model and version never checked', 'if model != meta["model"] or (version is not None and version != meta["version"]):', 'if False:', 'refused on add'],
  ['dimension never checked', 'if dimension != meta["dimension"]:', 'if False:', 'refused on add'],
  ['cosine without normalization', 'return dot / (norm_a * norm_b)', 'return dot', 'Cosine similarity'],
  ['search by dot product on vectors that were never normalized', 'scored.append((passage_id, cosine(query, json.loads(vector))))', 'scored.append((passage_id, math.fsum(x * y for x, y in zip(query, json.loads(vector)))))', 'compared by cosine'],
  ['re_embed keeps the old vectors', '            self.connection.execute("DELETE FROM vectors")\n', '', 're_embed'],
  ['store kept in memory', 'sqlite3.connect(path)', 'sqlite3.connect(":memory:")', 'persists on disk'],
  ['usage ignored', 'int(usage.get("prompt_tokens") or 0)', '0', 'usage per batch'],
  ['input sent as one joined string', '"input": list(texts)', '"input": "\\n".join(texts)', 'Ingest sends'],
  ['re_embed calls embed_fn on an empty store', 'for chunk in _batches([passage["text"] for passage in passages], batch_size):', 'for chunk in [[passage["text"] for passage in passages]]:', 're_embed'],
]
for (const [name, before, after, check] of mutations) {
  test(`Embeddings rejects ${name}`, async (t) => {
    const source = await solution()
    assert.ok(source.includes(before), `Mutation anchor missing: ${name}`)
    rejected(await candidate(t, source.replaceAll(before, after)), check)
  })
}

test('Embeddings: one request for everything passes the contract but misses the hidden bonus; the bonus never fails the run', async (t) => {
  const source = (await solution()).replace('for chunk in _batches(passages, batch_size):', 'for chunk in [passages]:')
  assert.notEqual(source, await solution())
  const result = await candidate(t, source)
  assert.equal(result.code, 0, JSON.stringify(result.checks))
  assert.equal(bonusChecks(result.checks).length, 1)
  assert.ok(bonusChecks(result.checks)[0]!.name.startsWith('bonus:'))
  assert.equal(bonusPassed(result.checks), false)
})

test('Embeddings: no embedding_model in llm.json is environment blocked, never a failure or a pass', async (t) => {
  const result = await candidate(t, await solution(), { endpoint: 'chat-only' })
  assert.equal(result.code, 1)
  const blocked = result.checks.find((item) => item.name === 'Environment blocked')!
  assert.ok(blocked, JSON.stringify(result.checks))
  assert.match(blocked.detail, /embedding_model/)
  assert.match(blocked.detail, /ollama pull/)
  assert.ok(result.checks.filter((item) => item.name !== 'Environment blocked' && !item.optional).every((item) => item.passed), 'The adapter checks still pass')
  assert.equal(result.stub!.requests.length, 0, 'Nothing is sent to an endpoint without an embedding model')
})

test('Embeddings: the verifier leaves no scratch database in the workspace', async (t) => {
  const workspace = await mkdtemp(path.join(os.tmpdir(), 'rankforge-embeddings-'))
  t.after(() => rm(workspace, { recursive: true, force: true }))
  await cp(path.join(root, 'labs', 'embeddings'), workspace, { recursive: true })
  await writeFile(path.join(workspace, 'store.py'), await solution())
  const result = await run('python3', ['-I', '-B', path.join(root, 'server', 'verify_embeddings.py'), 'embeddings', workspace], workspace)
  assert.equal(result.code, 1, result.stdout)
  assert.deepEqual((await readdir(workspace)).filter((name) => name.startsWith('.verify')), [])
})

test('Embeddings: an endpoint that does not answer is environment blocked with the address in the detail', async (t) => {
  const workspace = await mkdtemp(path.join(os.tmpdir(), 'rankforge-embeddings-'))
  t.after(() => rm(workspace, { recursive: true, force: true }))
  await cp(path.join(root, 'labs', 'embeddings'), workspace, { recursive: true })
  await writeFile(path.join(workspace, 'store.py'), await solution())
  await writeFile(path.join(workspace, 'llm.json'), embeddingConfig('http://127.0.0.1:9/v1'))
  const result = await run('python3', ['-I', '-B', path.join(root, 'server', 'verify_embeddings.py'), 'embeddings', workspace], workspace)
  const parsed = JSON.parse(result.stdout.trim().split('\n').at(-1) ?? '') as { checks: Check[] }
  const blocked = parsed.checks.find((item) => item.name === 'Environment blocked')!
  assert.ok(blocked, JSON.stringify(parsed.checks))
  assert.match(blocked.detail, /127\.0\.0\.1:9/)
})

test('Embeddings reports import failure as a failed check', async (t) => {
  rejected(await candidate(t, 'raise ValueError("Controlled import failure")\n', { endpoint: false }), 'Load embedding store')
})
