import test from 'node:test'
import assert from 'node:assert/strict'
import { cp, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { run, root } from '../server/labs.js'
import type { Check } from '../shared/types.js'
import { bonusChecks, bonusPassed } from '../shared/checks.js'

async function candidate(t: test.TestContext, source?: string) {
  const workspace = await mkdtemp(path.join(os.tmpdir(), 'rankforge-prompts-'))
  t.after(() => rm(workspace, { recursive: true, force: true }))
  await cp(path.join(root, 'labs', 'prompts'), workspace, { recursive: true })
  if (source !== undefined) await writeFile(path.join(workspace, 'registry.py'), source)
  const result = await run('python3', ['-I', '-B', path.join(root, 'server', 'verify_prompts.py'), 'prompts', workspace], workspace)
  assert.notEqual(result.code, 124, result.stderr)
  const parsed = JSON.parse(result.stdout.trim().split('\n').at(-1) ?? '') as { checks: Check[] }
  assert.ok(parsed.checks.length, JSON.stringify(result))
  return { ...result, checks: parsed.checks }
}
const solution = (name = 'files') => readFile(path.join(root, 'tests', 'solutions', 'prompts', `${name}.py`), 'utf8')
function rejected(result: Awaited<ReturnType<typeof candidate>>, check: string) {
  assert.equal(result.code, 1, JSON.stringify(result.checks))
  assert.ok(result.checks.some((item) => !item.passed && item.name.includes(check)), JSON.stringify(result.checks))
}
const requirements = ['content hash', 'carries prompt version', 'delimited', 'Changed template text', 'rejected', 'rolled-back']

test('Prompts: the starter is RED on every registry requirement', async (t) => {
  const result = await candidate(t)
  for (const name of requirements) rejected(result, name)
  assert.equal(bonusPassed(result.checks), false)
  assert.ok(!result.checks.some((item) => item.name === 'Environment blocked'), 'The mission has no live part')
})

for (const name of ['files', 'table']) {
  test(`Prompts: the ${name} implementation is GREEN on seven checks and earns the bonus`, async (t) => {
    const result = await candidate(t, await solution(name))
    assert.equal(result.code, 0, JSON.stringify(result.checks))
    assert.equal(result.checks.length, 7)
    assert.ok(result.checks.every((item) => item.passed), JSON.stringify(result.checks))
    assert.equal(bonusPassed(result.checks), true)
  })
}

const mutations: [string, string, string, string][] = [
  ['values inserted unescaped', 'return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")', 'return value', 'delimited'],
  ['ampersands escaped last and therefore twice', 'return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")', 'return value.replace("<", "&lt;").replace(">", "&gt;").replace("&", "&amp;")', 'delimited'],
  ['values inserted without a delimiter pair', 'f"<{match.group(1)}>{escape(variables[match.group(1)])}</{match.group(1)}>"', 'escape(variables[match.group(1)])', 'delimited'],
  ['sequential replace that scans earlier values for slots', '    return SLOT.sub(lambda match: f"<{match.group(1)}>{escape(variables[match.group(1)])}</{match.group(1)}>", template)', '    for key, value in variables.items():\n        template = template.replace("{{" + key + "}}", f"<{key}>{escape(value)}</{key}>")\n    return template', 'delimited'],
  ['raw file bytes hashed instead of the normalized text', 'return normalize(handle.read())', 'return handle.read()', 'content hash'],
  ['index hash never compared with the file', 'if digest != entry["sha256"]:', 'if False:', 'Changed template text'],
  ['two entries under one version tolerated', 'if version in catalog.get(name, {}):', 'if False:', 'rejected'],
  ['identical text under two versions tolerated', 'if twin is not None:', 'if False:', 'rejected'],
  ['parameters not forwarded to the request', '{"model": model, "messages": messages, **params}', '{"model": model, "messages": messages, "max_tokens": params.get("max_tokens", 64)}', 'carries prompt version'],
  ['log overwritten on every call', 'open(log_path, "a"', 'open(log_path, "w"', 'carries prompt version'],
  ['replay re-renders today’s registry without comparing with the log', '        rendered, template_digest, _ = self._render(record["prompt"], record["version"], record["variables"])', '        return self._render(record["prompt"], record["version"], record["variables"])[0]\n        rendered, template_digest = "", ""', 'rolled-back'],
]
for (const [name, before, after, check] of mutations) {
  test(`Prompts rejects ${name}`, async (t) => {
    const source = await solution()
    assert.ok(source.includes(before), `Mutation anchor missing: ${name}`)
    rejected(await candidate(t, source.replaceAll(before, after)), check)
  })
}

test('Prompts: ignoring the --- separator passes the contract but misses the hidden bonus; the bonus never fails the run', async (t) => {
  const source = (await solution()).replace('SEPARATOR = "\\n---\\n"', 'SEPARATOR = "\\n--- never ---\\n"')
  assert.notEqual(source, await solution())
  const result = await candidate(t, source)
  assert.equal(result.code, 0, JSON.stringify(result.checks))
  assert.equal(bonusChecks(result.checks).length, 1)
  assert.ok(bonusChecks(result.checks)[0]!.name.startsWith('bonus:'))
  assert.equal(bonusPassed(result.checks), false)
})

test('Prompts reports import failure as a failed check', async (t) => {
  rejected(await candidate(t, 'raise ValueError("Controlled import failure")\n'), 'Load prompt registry')
})
