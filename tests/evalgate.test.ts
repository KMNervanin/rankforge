import test from 'node:test'
import assert from 'node:assert/strict'
import { cp, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { run, root } from '../server/labs.js'
import type { Check } from '../shared/types.js'
import { bonusChecks, bonusPassed } from '../shared/checks.js'

// No live part: the verifier plays the model and judge with a scripted runner and never opens a socket.
async function candidate(t: test.TestContext, source?: string) {
  const workspace = await mkdtemp(path.join(os.tmpdir(), 'rankforge-evalgate-'))
  t.after(() => rm(workspace, { recursive: true, force: true }))
  await cp(path.join(root, 'labs', 'evalgate'), workspace, { recursive: true })
  if (source !== undefined) await writeFile(path.join(workspace, 'gate.py'), source)
  const result = await run('python3', ['-I', '-B', path.join(root, 'server', 'verify_evalgate.py'), 'evalgate', workspace], workspace)
  assert.notEqual(result.code, 124, result.stderr)
  const parsed = JSON.parse(result.stdout.trim().split('\n').at(-1) ?? '') as { checks: Check[] }
  assert.ok(parsed.checks.length, JSON.stringify(result))
  return { ...result, checks: parsed.checks }
}
const solution = (name = 'functions') => readFile(path.join(root, 'tests', 'solutions', 'evalgate', `${name}.py`), 'utf8')
function rejected(result: Awaited<ReturnType<typeof candidate>>, check: string) {
  assert.equal(result.code, 1, JSON.stringify(result.checks))
  assert.ok(result.checks.some((item) => !item.passed && item.name.includes(check)), JSON.stringify(result.checks))
}

test('Evalgate: the starter is RED on every gate requirement', async (t) => {
  const result = await candidate(t)
  for (const name of ['seeded regression', 'declared tolerance', 'repeat policy', 'token cap', 'time cap', 'append-only', 'held-out split', 'only the model id']) rejected(result, name)
  const detail = (name: string) => result.checks.find((item) => item.name.includes(name))!.detail
  assert.match(detail('seeded regression'), /held-out cases never run/, 'the starter runs the whole manifest')
  assert.match(detail('declared tolerance'), /got blocked/, 'the starter blocks on its hardcoded 90')
  assert.match(detail('held-out split'), /ConfigError/)
  assert.match(detail('append-only'), /results\.json/, 'the starter overwrites one results.json')
  assert.equal(bonusPassed(result.checks), false)
  assert.ok(!result.checks.some((item) => item.name === 'Environment blocked'), 'Nothing in this mission depends on the environment')
})

for (const name of ['functions', 'dataclass']) {
  test(`Evalgate: the ${name} implementation is GREEN with the exact check count and earns the bonus`, async (t) => {
    const result = await candidate(t, await solution(name))
    assert.equal(result.code, 0, JSON.stringify(result.checks))
    assert.equal(result.checks.length, 9)
    assert.ok(result.checks.every((item) => item.passed), JSON.stringify(result.checks))
    assert.equal(bonusPassed(result.checks), true)
  })
}

const mutations: [string, string, string, string][] = [
  ['every dev case run instead of the configured subset', '    return [by_id[case_id] for case_id in subset], runs, pass_min', '    return [case for case in manifest["cases"] if case["split"] == "dev"], runs, pass_min', 'seeded regression'],
  ['the failing cases not named', '    decision["failing"] = sorted(case_id for case_id in decided if not outcomes[case_id])', '    decision["failing"] = []', 'seeded regression'],
  ['the baseline accuracy taken over the whole baseline instead of the subset', 'baseline_accuracy = 100.0 * sum(1 for case_id in decided if baseline[case_id]) / n', 'baseline_accuracy = 100.0 * sum(1 for value in baseline.values() if value) / len(baseline)', 'seeded regression'],
  ['a drop exactly at the tolerance blocked', '        elif drop > float(thresholds["max_drop"]) + TOLERANCE:', '        elif drop >= float(thresholds["max_drop"]) - TOLERANCE:', 'declared tolerance'],
  ['the first failure treated as final', '            elif fails >= runs - pass_min + 1:', '            elif fails >= 1:', 'repeat policy'],
  ['a failing case rerun to the full count instead of stopping at the deciding attempt', '            elif fails >= runs - pass_min + 1:', '            elif len(entry["attempts"]) >= runs:', 'repeat policy'],
  ['the token cap compared before adding the last result', '            if tokens > cap_tokens:', '            if tokens - int(result["tokens"]) > cap_tokens:', 'token cap'],
  ['the injected clock never consulted', '            elif clock() - started > cap_seconds:', '            elif 0.0 > cap_seconds:', 'time cap'],
  ['the archive file opened for writing instead of exclusive creation', 'with open(path, "x", encoding="utf-8") as file:', 'with open(path, "w", encoding="utf-8") as file:', 'append-only'],
  ['the config hash left unpinned', '"config_hash": config_hash(config)', '"config_hash": None', 'append-only'],
  ['held-out ids accepted in the subset', '        if case.get("split") != "dev":', '        if case.get("split") not in ("dev", "heldout"):', 'held-out split'],
  ['the model id missing from the archive name', 'f"{int(started * 1000)}-{candidate[\'prompt_version\']}-{candidate[\'model\']}.json"', 'f"{int(started * 1000)}-{candidate[\'prompt_version\']}.json"', 'only the model id'],
]
for (const [name, before, after, check] of mutations) {
  test(`Evalgate rejects ${name}`, async (t) => {
    const source = await solution()
    assert.ok(source.includes(before), `Mutation anchor missing: ${name}`)
    rejected(await candidate(t, source.replaceAll(before, after)), check)
  })
}

test('Evalgate: ignoring paired_z passes the contract but misses the hidden bonus; the bonus never fails the run', async (t) => {
  const source = (await solution()).replace('        z = thresholds.get("paired_z")', '        z = None')
  assert.notEqual(source, await solution())
  const result = await candidate(t, source)
  assert.equal(result.code, 0, JSON.stringify(result.checks))
  assert.equal(bonusChecks(result.checks).length, 1)
  assert.ok(bonusChecks(result.checks)[0]!.name.startsWith('bonus:'))
  assert.equal(bonusPassed(result.checks), false)
})

test('Evalgate: a gate that runs everything once, never caps and always passes is RED', async (t) => {
  const source = 'import json\nimport os\n\n\nclass ConfigError(Exception):\n    pass\n\n\ndef run_gate(config, *, candidate, baseline_results, run_case, clock):\n    started = clock()\n    results = [{"id": c["id"], "passed": True, "attempts": [run_case(c)]} for c in config["manifest"]["cases"] if c["id"] in config["subset"]]\n    decision = {"verdict": "pass", "reason": "ok", "failing": [], "regressions": [], "accuracy": 100.0, "baseline_accuracy": 100.0, "drop": 0.0, "cases_total": len(results), "cases_run": len(results), "calls": len(results), "tokens": sum(r["attempts"][0]["tokens"] for r in results), "seconds": clock() - started, "cap": dict(config["cap"], exceeded=None), "versions": {"prompt_version": candidate["prompt_version"], "model": candidate["model"], "config_hash": "", "set_version": config["manifest"]["version"]}, "results": results}\n    os.makedirs(config["archive"], exist_ok=True)\n    decision["archive"] = os.path.join(config["archive"], f"{int(started * 1000)}-{candidate[\'prompt_version\']}-{candidate[\'model\']}.json")\n    with open(decision["archive"], "w", encoding="utf-8") as f:\n        json.dump(decision, f)\n    return decision\n'
  const result = await candidate(t, source)
  for (const name of ['seeded regression', 'repeat policy', 'token cap', 'time cap', 'held-out split']) rejected(result, name)
})

test('Evalgate reports import failure as a failed check', async (t) => {
  rejected(await candidate(t, 'raise ValueError("Controlled import failure")\n'), 'Load release gate')
})
