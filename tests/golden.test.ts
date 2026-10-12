import test from 'node:test'
import assert from 'node:assert/strict'
import { cp, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { run, root } from '../server/labs.js'
import type { Check } from '../shared/types.js'
import { bonusChecks, bonusPassed } from '../shared/checks.js'

async function candidate(t: test.TestContext, source?: string) {
  const workspace = await mkdtemp(path.join(os.tmpdir(), 'rankforge-golden-'))
  t.after(() => rm(workspace, { recursive: true, force: true }))
  await cp(path.join(root, 'labs', 'golden'), workspace, { recursive: true })
  if (source !== undefined) await writeFile(path.join(workspace, 'goldenset.py'), source)
  const result = await run('python3', ['-I', '-B', path.join(root, 'server', 'verify_golden.py'), 'golden', workspace], workspace)
  assert.notEqual(result.code, 124, result.stderr)
  const parsed = JSON.parse(result.stdout.trim().split('\n').at(-1) ?? '') as { checks: Check[] }
  assert.ok(parsed.checks.length, JSON.stringify(result))
  return { ...result, checks: parsed.checks }
}
const solution = (name = 'ledger') => readFile(path.join(root, 'tests', 'solutions', 'golden', `${name}.py`), 'utf8')
function rejected(result: Awaited<ReturnType<typeof candidate>>, check: string) {
  assert.equal(result.code, 1, JSON.stringify(result.checks))
  assert.ok(result.checks.some((item) => !item.passed && item.name.includes(check)), JSON.stringify(result.checks))
}
const requirements = ['hashed', 'Provenance', 'category below', 'deterministic', 'Held-out digest', 'few-shot example', 'add_case']

test('Golden: the starter is RED on every manifest requirement', async (t) => {
  const result = await candidate(t)
  for (const name of requirements) rejected(result, name)
  assert.equal(bonusPassed(result.checks), false)
  assert.ok(!result.checks.some((item) => item.name === 'Environment blocked'), 'The mission has no live part')
})

for (const name of ['ledger', 'catalog']) {
  test(`Golden: the ${name} implementation is GREEN on eight checks and earns the bonus`, async (t) => {
    const result = await candidate(t, await solution(name))
    assert.equal(result.code, 0, JSON.stringify(result.checks))
    assert.equal(result.checks.length, 8)
    assert.ok(result.checks.every((item) => item.passed), JSON.stringify(result.checks))
    assert.equal(bonusPassed(result.checks), true)
  })
}

const mutations: [string, string, string, string][] = [
  ['case hashed from its repr instead of the canonical JSON', 'canonical = json.dumps({key: case[key] for key in HASHED_FIELDS}, sort_keys=True, ensure_ascii=False, separators=(",", ":"))', 'canonical = repr({key: case[key] for key in HASHED_FIELDS})', 'hashed'],
  ['split taken from the hash of the id alone, ignoring the seed', 'digest = hashlib.sha256(f"{seed}:{case_id}".encode("utf-8")).hexdigest()', 'digest = hashlib.sha256(f"{case_id}".encode("utf-8")).hexdigest()', 'deterministic'],
  ['per-category minimum never enforced at build time', '    if short:\n        raise ValueError', '    if False:\n        raise ValueError', 'category below'],
  ['provenance kind not restricted to real or synthetic', 'provenance.get("kind") not in PROVENANCE_KINDS or', 'False or', 'Provenance'],
  ['held-out digest taken over every split', 'digest = held_out_digest([case["hash"] for case in stamped if case["split"] == "test"])', 'digest = held_out_digest([case["hash"] for case in stamped])', 'Held-out digest'],
  ['verify trusts the stored hash instead of recomputing it', '        if case.get("hash") != case_hash(case):', '        if False:', 'Held-out digest'],
  ['leakage compared without casefolding', 'return " ".join(kept.split()).casefold()', 'return " ".join(kept.split())', 'few-shot example'],
  ['add_case mutates the manifest it was given', '    updated = copy.deepcopy(manifest)', '    updated = manifest', 'add_case'],
  ['add_case rewrites history with a single entry', '    updated["history"].append(', '    updated["history"] = []\n    updated["history"].append(', 'add_case'],
]
for (const [name, before, after, check] of mutations) {
  test(`Golden rejects ${name}`, async (t) => {
    const source = await solution()
    assert.ok(source.includes(before), `Mutation anchor missing: ${name}`)
    rejected(await candidate(t, source.replaceAll(before, after)), check)
  })
}

test('Golden: skipping near-duplicate detection passes the contract but misses the hidden bonus; the bonus never fails the run', async (t) => {
  const source = (await solution()).replace('        if len(ids) > 1:\n            errors.append(f"duplicate:', '        if False:\n            errors.append(f"duplicate:')
  assert.notEqual(source, await solution())
  const result = await candidate(t, source)
  assert.equal(result.code, 0, JSON.stringify(result.checks))
  assert.equal(bonusChecks(result.checks).length, 1)
  assert.ok(bonusChecks(result.checks)[0]!.name.startsWith('bonus:'))
  assert.equal(bonusPassed(result.checks), false)
})

test('Golden reports import failure as a failed check', async (t) => {
  rejected(await candidate(t, 'raise ValueError("Controlled import failure")\n'), 'Load golden set')
})
