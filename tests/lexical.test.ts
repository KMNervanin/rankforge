import test from 'node:test'
import assert from 'node:assert/strict'
import { cp, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { run, root } from '../server/labs.js'
import type { Check } from '../shared/types.js'
import { bonusChecks, bonusPassed } from '../shared/checks.js'

// No live part: the dense vectors come from the verifier's own embed stand-in, so no stub endpoint is needed.
async function candidate(t: test.TestContext, source?: string) {
  const workspace = await mkdtemp(path.join(os.tmpdir(), 'rankforge-lexical-'))
  t.after(() => rm(workspace, { recursive: true, force: true }))
  await cp(path.join(root, 'labs', 'lexical'), workspace, { recursive: true })
  if (source !== undefined) await writeFile(path.join(workspace, 'lexical.py'), source)
  const result = await run('python3', ['-I', '-B', path.join(root, 'server', 'verify_lexical.py'), 'lexical', workspace], workspace)
  assert.notEqual(result.code, 124, result.stderr)
  const parsed = JSON.parse(result.stdout.trim().split('\n').at(-1) ?? '') as { checks: Check[] }
  assert.ok(parsed.checks.length, JSON.stringify(result))
  return { ...result, checks: parsed.checks }
}
const solution = (name = 'fts5') => readFile(path.join(root, 'tests', 'solutions', 'lexical', `${name}.py`), 'utf8')
function rejected(result: Awaited<ReturnType<typeof candidate>>, check: string) {
  assert.equal(result.code, 1, JSON.stringify(result.checks))
  assert.ok(result.checks.some((item) => !item.passed && item.name.includes(check)), JSON.stringify(result.checks))
}

test('Lexical: the starter is RED on the tokenizer, exact codes, ordering, categories, verdict and transfer', async (t) => {
  const result = await candidate(t)
  for (const name of ['Tokenizer keeps', 'Exact-code queries', 'ascending by bm25', 'Per-category recall', 'compare names', 'Transfer']) rejected(result, name)
  assert.ok(result.checks.find((item) => item.name.startsWith('Dense ranking'))!.passed, 'The dense side of the starter is already right')
  assert.equal(bonusPassed(result.checks), false)
  assert.ok(!result.checks.some((item) => item.name === 'Environment blocked'), 'FTS5 is present, so nothing here is an environment problem')
})

for (const name of ['fts5', 'bm25']) {
  test(`Lexical: the ${name} implementation is GREEN with the exact check count and earns the bonus`, async (t) => {
    const result = await candidate(t, await solution(name))
    assert.equal(result.code, 0, JSON.stringify(result.checks))
    assert.equal(result.checks.length, 9)
    assert.ok(result.checks.every((item) => item.passed), JSON.stringify(result.checks))
    assert.equal(bonusPassed(result.checks), true)
    const report = result.checks.find((item) => item.name.startsWith('Per-category'))!
    assert.match(report.detail, /exact_code: lexical 1\.00, dense 0\.00 → lexical/)
    assert.match(report.detail, /paraphrase: .* → dense/)
  })
}

const mutations: [string, string, string, string][] = [
  ['a tokenizer that splits codes', 'tokens.append(match.group(0).lower())', 'tokens.extend(word.lower() for word in WORD.findall(match.group(0)))', 'Tokenizer keeps'],
  ['a query expanded with the pieces of each code', 'for token in dict.fromkeys(tokens))', 'for token in dict.fromkeys(tokens + [piece for token in tokens for piece in WORD.findall(token)]))', 'Exact-code queries'],
  ['bm25 sorted descending', 'ORDER BY rank, id LIMIT ?', 'ORDER BY rank DESC, id LIMIT ?', 'ascending by bm25'],
  ['dense ties broken by the higher id', 'scored.sort(key=lambda item: (-item[1], item[0]))', 'scored.sort(key=lambda item: (-item[1], item[0]), reverse=True)\n    scored.sort(key=lambda item: -item[1])', 'Dense ranking'],
  ['precision reported as recall', 'return len(set(expected) & set(ranked)) / len(set(expected))', 'return len(set(expected) & set(ranked)) / max(len(ranked), 1)', 'Per-category recall'],
  ['categories merged into one aggregate', '"categories": {name: _summary(group) for name, group in categories.items()},', '"categories": {"all": _summary(entries)},', 'Per-category recall'],
  ['a verdict that always picks the overall winner', 'verdict[name] = "tie" if abs(gap) <= 1e-9 else ("lexical" if gap > 0 else "dense")', 'verdict[name] = "lexical"', 'compare names'],
  ['the stored pattern list ignored at search time', 'tokens = tokenize(query, code_patterns=_patterns(connection))', 'tokens = tokenize(query)', 'Transfer'],
  ['the dense list cut one short', 'return scored[:k]', 'return scored[:k - 1]', 'Dense ranking'],
]
for (const [name, before, after, check] of mutations) {
  test(`Lexical rejects ${name}`, async (t) => {
    const source = await solution()
    assert.ok(source.includes(before), `Mutation anchor missing: ${name}`)
    rejected(await candidate(t, source.replaceAll(before, after)), check)
  })
}

test('Lexical: a report without normalized scores passes the contract but misses the hidden bonus; the bonus never fails the run', async (t) => {
  const source = (await solution()).replace('            "lexical_scored": _normalized(lexical), "dense_scored": _normalized(dense),\n', '')
  assert.notEqual(source, await solution())
  const result = await candidate(t, source)
  assert.equal(result.code, 0, JSON.stringify(result.checks))
  assert.equal(bonusChecks(result.checks).length, 1)
  assert.ok(bonusChecks(result.checks)[0]!.name.startsWith('bonus:'))
  assert.equal(bonusPassed(result.checks), false)
})

test('Lexical: an index kept only in memory is RED in a fresh process', async (t) => {
  const source = (await solution()).replace('def _connect(path):\n    connection = sqlite3.connect(path)', 'MEMORY = sqlite3.connect(":memory:")\n\n\ndef _connect(path):\n    connection = MEMORY').replaceAll('connection.close()', 'pass')
  assert.notEqual(source, await solution())
  rejected(await candidate(t, source), 'fresh process')
})

test('Lexical reports import failure as a failed check', async (t) => {
  rejected(await candidate(t, 'raise ValueError("Controlled import failure")\n'), 'Load lexical index')
})
