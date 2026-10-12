import test from 'node:test'
import assert from 'node:assert/strict'
import { cp, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { run, root } from '../server/labs.js'
import type { Check } from '../shared/types.js'
import { bonusChecks, bonusPassed } from '../shared/checks.js'

async function candidate(t: test.TestContext, source?: string) {
  const workspace = await mkdtemp(path.join(os.tmpdir(), 'rankforge-chunking-'))
  t.after(() => rm(workspace, { recursive: true, force: true }))
  await cp(path.join(root, 'labs', 'chunking'), workspace, { recursive: true })
  if (source !== undefined) await writeFile(path.join(workspace, 'chunker.py'), source)
  const result = await run('python3', ['-I', '-B', path.join(root, 'server', 'verify_chunking.py'), 'chunking', workspace], workspace)
  assert.notEqual(result.code, 124, result.stderr)
  const parsed = JSON.parse(result.stdout.trim().split('\n').at(-1) ?? '') as { checks: Check[] }
  assert.ok(parsed.checks.length, JSON.stringify(result))
  return { ...result, checks: parsed.checks }
}
const solution = (name = 'stream') => readFile(path.join(root, 'tests', 'solutions', 'chunking', `${name}.py`), 'utf8')
function rejected(result: Awaited<ReturnType<typeof candidate>>, check: string) {
  assert.equal(result.code, 1, JSON.stringify(result.checks))
  assert.ok(result.checks.some((item) => !item.passed && item.name.includes(check)), JSON.stringify(result.checks))
}
const requirements = ['Fixed chunks', 'Structural', 'audit', 'recompute', 'chosen strategy', 'retrievable', 'longer']

test('Chunking: the starter is RED on every chunking requirement', async (t) => {
  const result = await candidate(t)
  for (const name of requirements) rejected(result, name)
  assert.equal(bonusPassed(result.checks), false)
  assert.ok(!result.checks.some((item) => item.name === 'Environment blocked'), 'The mission has no live part')
})

for (const name of ['stream', 'cursor']) {
  test(`Chunking: the ${name} implementation is GREEN on eight checks and earns the bonus`, async (t) => {
    const result = await candidate(t, await solution(name))
    assert.equal(result.code, 0, JSON.stringify(result.checks))
    assert.equal(result.checks.length, 8)
    assert.ok(result.checks.every((item) => item.passed), JSON.stringify(result.checks))
    assert.equal(bonusPassed(result.checks), true)
  })
}

const mutations: [string, string, string, string][] = [
  ['overlap ignored by the fixed stride', '        start += size - overlap', '        start += size', 'Fixed chunks'],
  ['warning field dropped from the passage text', '        text = f"{text}\\nWarning: {warning}"', '        text = text', 'Fixed chunks'],
  ['structural treats a Warning paragraph as its own unit', '                elif index + 1 < len(self.passages) and is_warning_paragraph(self.passages[index + 1]):', '                elif False:', 'Structural'],
  ['structural ignores the size bound', '        if open_start is not None and (open_end - open_start + length > size or cut_before(index)):', '        if open_start is not None and cut_before(index):', 'Structural'],
  ['audit ignores the warning field form', '                if isinstance(passage.get("warning"), str) and passage["warning"].strip():\n                    unit["step_id"], unit["warning_id"] = passage["id"], passage["id"]', '                if False:\n                    pass', 'audit'],
  ['recall counted as any hit instead of the covered fraction', '        recall[k] = Fraction(len(covered), len(expected)) if expected else Fraction(0)', '        recall[k] = Fraction(1 if covered else 0)', 'recompute'],
  ['MRR without the k cutoff', '        top = ranking[:k]', '        top = ranking', 'recompute'],
  ['metrics echoes the stored aggregates', 'def metrics(report):\n    k_values', 'def metrics(report):\n    if "recall" in report and "mrr" in report:\n        return {"recall": dict(report["recall"]), "mrr": dict(report["mrr"])}\n    k_values', 'recompute'],
  ['choose takes the highest recall regardless of cost', '    winner = min(meeting, key=lambda item: (item["chunk_count"], item["avg_words"], item["strategy"]))', '    winner = max(meeting, key=lambda item: item["recall"])', 'chosen strategy'],
  ['choose trusts the stored recall of a report', '        recomputed = metrics(report)', '        recomputed = {"recall": {str(k): v for k, v in report["recall"].items()}, "mrr": {str(k): v for k, v in report["mrr"].items()}}', 'chosen strategy'],
]
for (const [name, before, after, check] of mutations) {
  test(`Chunking rejects ${name}`, async (t) => {
    const source = await solution()
    assert.ok(source.includes(before), `Mutation anchor missing: ${name}`)
    rejected(await candidate(t, source.replaceAll(before, after)), check)
  })
}

test('Chunking: leaving semantic chunking out passes the contract but misses the hidden bonus; the bonus never fails the run', async (t) => {
  const source = (await solution()).replace('            texts = [" ".join(document.words[unit["start"]:unit["end"]]) for unit in document.units]', '            raise NotImplementedError("semantic chunking is not implemented")')
  assert.notEqual(source, await solution())
  const result = await candidate(t, source)
  assert.equal(result.code, 0, JSON.stringify(result.checks))
  assert.equal(bonusChecks(result.checks).length, 1)
  assert.ok(bonusChecks(result.checks)[0]!.name.startsWith('bonus:'))
  assert.equal(bonusPassed(result.checks), false)
})

test('Chunking reports import failure as a failed check', async (t) => {
  rejected(await candidate(t, 'raise ValueError("Controlled import failure")\n'), 'Load chunker')
})
