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
  const workspace = await mkdtemp(path.join(os.tmpdir(), 'rankforge-window-'))
  t.after(() => rm(workspace, { recursive: true, force: true }))
  await cp(path.join(root, 'labs', 'window'), workspace, { recursive: true })
  if (source !== undefined) await writeFile(path.join(workspace, 'context.py'), source)
  const result = await run('python3', ['-I', '-B', path.join(root, 'server', 'verify_window.py'), 'window', workspace], workspace)
  assert.notEqual(result.code, 124, result.stderr)
  const parsed = JSON.parse(result.stdout.trim().split('\n').at(-1) ?? '') as { checks: Check[] }
  assert.ok(parsed.checks.length, JSON.stringify(result))
  return { ...result, checks: parsed.checks }
}
const solution = (name = 'prefix') => readFile(path.join(root, 'tests', 'solutions', 'window', `${name}.py`), 'utf8')
function rejected(result: Awaited<ReturnType<typeof candidate>>, check: string) {
  assert.equal(result.code, 1, JSON.stringify(result.checks))
  assert.ok(result.checks.some((item) => !item.passed && item.name.includes(check)), JSON.stringify(result.checks))
}

test('Window: the starter is RED on every budget requirement', async (t) => {
  const result = await candidate(t)
  for (const name of ['published order', 'reserved output', 'oldest-first', 'passage boundaries', 'Any counter', 'half the window', 'Deterministic']) rejected(result, name)
  assert.equal(bonusPassed(result.checks), false)
  assert.ok(!result.checks.some((item) => item.name === 'Environment blocked'), 'Nothing in this mission depends on the environment')
})

for (const name of ['prefix', 'retrieve']) {
  test(`Window: the ${name} implementation is GREEN with the exact check count and earns the bonus`, async (t) => {
    const result = await candidate(t, await solution(name))
    assert.equal(result.code, 0, JSON.stringify(result.checks))
    assert.equal(result.checks.length, 8)
    assert.ok(result.checks.every((item) => item.passed), JSON.stringify(result.checks))
    assert.equal(bonusPassed(result.checks), true)
  })
}

const mutations: [string, string, string, string][] = [
  ['the reserved output ignored', 'budget = window - reserve_output', 'budget = window', 'reserved output'],
  ['instructions treated as droppable', 'entry["kind"] in ("instructions", "pinned")', 'entry["kind"] == "pinned"', 'instructions, pinned facts and the newest turn survive'],
  ['history dropped newest-first', 'for entry in reversed(older):', 'for entry in older:', 'oldest-first'],
  ['a turn that does not fit skipped instead of ending the run', '            break\n        kept_history.insert(0, entry)', '            continue\n        kept_history.insert(0, entry)', 'oldest-first'],
  ['the fill ended at the first dropped document', '        else:\n            continue  # a dropped document does not end the fill', '        else:\n            break', 'instructions, pinned facts and the newest turn survive'],
  ['the shortening marker omitted', 'return f"[shortened: kept {kept} of {total} passages]"', 'return ""', 'passage boundaries'],
  ['a document cut mid-sentence by characters', 'content = "\\n\\n".join(parts[:kept] + [marker(kept, len(parts))])', 'content = whole[: len(whole) * kept // len(parts) - 7] + "\\n\\n" + marker(kept, len(parts))', 'passage boundaries'],
  ['a character count as the default estimate', 'return len(text.encode("utf-8"))', 'return len(text)', 'Any counter'],
  ['the per-message overhead left out of the report', 'return count(text) + overhead', 'return count(text)', 'published order'],
  ['equal priorities ordered newest-input-first', 'key=lambda entry: (int(entry["priority"]), entry["index"])', 'key=lambda entry: (int(entry["priority"]), -entry["index"])', 'Deterministic'],
]
for (const [name, before, after, check] of mutations) {
  test(`Window rejects ${name}`, async (t) => {
    const source = await solution()
    assert.ok(source.includes(before), `Mutation anchor missing: ${name}`)
    rejected(await candidate(t, source.replaceAll(before, after)), check)
  })
}

test('Window: keeping an orphaned assistant turn passes the contract but misses the hidden bonus; the bonus never fails the run', async (t) => {
  const source = (await solution()).replace('    while kept_history and kept_history[0]["role"] == "assistant":', '    while False:')
  assert.notEqual(source, await solution())
  const result = await candidate(t, source)
  assert.equal(result.code, 0, JSON.stringify(result.checks))
  assert.equal(bonusChecks(result.checks).length, 1)
  assert.ok(bonusChecks(result.checks)[0]!.name.startsWith('bonus:'))
  assert.equal(bonusPassed(result.checks), false)
})

test('Window: a builder that always returns everything is RED on the budget', async (t) => {
  const source = 'class BudgetError(Exception):\n    pass\n\n\ndef estimate(text):\n    return len(text.encode("utf-8"))\n\n\ndef build(sections, *, window, reserve_output, overhead, count=estimate):\n    messages = [{"role": s.get("role", "system"), "content": s["text"]} for s in sections]\n    total = sum(count(m["content"]) + overhead for m in messages)\n    report = {"window": window, "reserve_output": reserve_output, "budget": window - reserve_output, "overhead": overhead, "method": count.__name__, "total": total, "sections": [{"id": s["id"], "kind": s["kind"], "status": "kept", "tokens": count(s["text"]) + overhead, "kept": count(s["text"]) + overhead} for s in sections]}\n    return messages, report\n'
  const result = await candidate(t, source)
  for (const name of ['reserved output', 'oldest-first', 'passage boundaries', 'half the window']) rejected(result, name)
})

test('Window reports import failure as a failed check', async (t) => {
  rejected(await candidate(t, 'raise ValueError("Controlled import failure")\n'), 'Load context builder')
})
