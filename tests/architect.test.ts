import test from 'node:test'
import assert from 'node:assert/strict'
import { cp, mkdtemp, readFile, readdir, rm, writeFile } from 'node:fs/promises'
import path from 'node:path'
import os from 'node:os'
import { root, run } from '../server/labs.js'
import { architectMissions, architectFollowUps } from '../shared/architect.js'

type Report = { checks: { name: string; passed: boolean; detail: string }[] }
const python = process.env.RANKFORGE_TEST_PYTHON ?? 'python3'
const entries = { briefing: 'manifest.py', capacity: 'capacity.py', contract: 'probe.py' } as const
type Mission = keyof typeof entries
const solution = (name: string) => readFile(path.join(root, 'tests/solutions/architect', `${name}.py`), 'utf8')
async function snapshot(directory: string): Promise<Record<string, string>> {
  const files: Record<string, string> = {}
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const file = path.join(directory, entry.name)
    if (entry.isDirectory()) for (const [name, value] of Object.entries(await snapshot(file))) files[`${entry.name}/${name}`] = value
    else files[entry.name] = (await readFile(file)).toString('base64')
  }
  return files
}
async function workspace(t: test.TestContext, mission: Mission, source?: string, helpers: Record<string, string> = {}) {
  const temporary = await mkdtemp(path.join(os.tmpdir(), 'rankforge-guild-'))
  t.after(() => rm(temporary, { recursive: true, force: true }))
  const directory = path.join(temporary, 'workspace with spaces')
  await cp(path.join(root, 'labs', mission), directory, { recursive: true })
  if (source !== undefined) await writeFile(path.join(directory, entries[mission]), source)
  for (const [name, value] of Object.entries(helpers)) await writeFile(path.join(directory, name), value)
  await writeFile(path.join(directory, 'my-notes.txt'), 'An unrelated learner note.\n')
  return directory
}
async function verify(directory: string, mission: Mission, profile = false) {
  const before = await snapshot(directory)
  const profiler = `import json, resource, runpy, sys, threading, time\nsys.argv = sys.argv[1:]\nstart = time.monotonic()\ntry:\n    runpy.run_path(sys.argv[0], run_name='__main__')\nexcept SystemExit as error:\n    code = error.code\nusage = resource.getrusage(resource.RUSAGE_SELF)\nprint(json.dumps(dict(seconds=time.monotonic()-start, peak_rss_bytes=usage.ru_maxrss * (1 if sys.platform == 'darwin' else 1024), remaining_threads=threading.active_count())), file=sys.stderr)\nsys.exit(code)\n`
  const result = await run(python, ['-I', '-B', ...(profile ? ['-c', profiler] : []), path.join(root, 'server/verify_architect.py'), mission, directory], directory)
  assert.deepEqual(await snapshot(directory), before, 'Checking must preserve every workspace byte and create no pycache')
  const report: Report = JSON.parse(result.stdout.trim().split('\n').at(-1) ?? '')
  assert.ok(report.checks.length > 0, result.stdout + result.stderr)
  for (const check of report.checks) {
    assert.equal(typeof check.name, 'string')
    assert.equal(typeof check.passed, 'boolean')
    assert.equal(typeof check.detail, 'string')
  }
  assert.equal(result.code === 0, report.checks.every(check => check.passed), JSON.stringify(report))
  return { ...report, code: result.code, stderr: result.stderr }
}
async function candidate(t: test.TestContext, mission: Mission, source: string, helpers: Record<string, string> = {}) {
  return verify(await workspace(t, mission, source, helpers), mission)
}
function accepted(result: Awaited<ReturnType<typeof verify>>) { assert.equal(result.code, 0, JSON.stringify(result, null, 2)) }
function rejected(result: Awaited<ReturnType<typeof verify>>, name: string) {
  assert.notEqual(result.code, 0, JSON.stringify(result))
  assert.ok(result.checks.some(check => !check.passed && check.name.includes(name)), JSON.stringify(result, null, 2))
}

test('guild metadata exposes three bounded missions and independent D02/D03 prerequisites', () => {
  assert.deepEqual(architectMissions.map(m => [m.id, m.chapter, m.order, m.prerequisites]), [
    ['briefing', 'guild', 7, ['recovery']], ['capacity', 'guild', 8, ['briefing']], ['contract', 'guild', 9, ['briefing']],
  ])
  for (const mission of architectMissions) assert.ok(architectFollowUps[mission.id]!.length >= 2)
})

for (const mission of Object.keys(entries) as Mission[]) {
  test(`${mission}: the shipped starter has a real RED verdict and preserves learner files`, async t => {
    rejected(await verify(await workspace(t, mission), mission), mission === 'briefing' ? 'Manifest' : mission === 'capacity' ? 'Capacity' : 'HTTP probe')
  })
}

for (const [mission, names] of Object.entries({ briefing: ['briefing-separated', 'briefing-grouped'], capacity: ['capacity-float', 'capacity-fraction'], contract: ['contract-http', 'contract-urllib'] }) as [Mission, string[]][]) {
  for (const name of names) test(`${mission}: ${name} passes fresh/repeat and negative scenarios`, async t => {
    accepted(await candidate(t, mission, await solution(name)))
  })
}

test('briefing accepts explicitly open questions and arbitrary review-only prose', async t => {
  const source = await solution('briefing-grouped')
  const opened = `${source}\noriginal = build_manifest\ndef build_manifest(ticket):\n    result = original(ticket)\n    result['assumptions'] = []\n    result['open_questions'] = [q['id'] for q in ticket['questions']]\n    result['cases'] = [c for c in result['cases'] if not c['assumptions']]\n    result['rationale'] = 'A different explanation, pending review.'\n    return result\n`
  accepted(await candidate(t, 'briefing', opened))
})

for (const [name, mutation] of [
  ['missing negative observation', `result['cases'] = [c for c in result['cases'] if c['kind'] != 'over_limit']`],
  ['assumption as fact', `result['assumptions'][0]['source'] = 'fact'`],
  ['unsupported choice', `result['assumptions'][0]['choice'] = 'magic'`],
  ['wrong units', `result['requirements'][0]['facts'][0]['unit'] = 'seconds'`],
  ['lost exclusion', `result['exclusions'] = []`],
  ['dangling reference', `result['cases'][0]['requirements'] = ['absent']`],
  ['input mutation', `ticket['revision'] += 1`],
] as const) test(`briefing rejects ${name}`, async t => {
  const source = `${await solution('briefing-separated')}\noriginal = build_manifest\ndef build_manifest(ticket):\n    result = original(ticket)\n    ${mutation}\n    return result\n`
  rejected(await candidate(t, 'briefing', source), 'Manifest')
})

test('briefing rejects a static manifest after the two changed tickets', async t => {
  const source = `${await solution('briefing-separated')}\noriginal = build_manifest\ncached = None\ndef build_manifest(ticket):\n    global cached\n    if cached is None: cached = original(ticket)\n    return cached\n`
  const report = await candidate(t, 'briefing', source)
  assert.equal(report.checks.find(c => c.name === 'Manifest: original')?.passed, true)
  rejected(report, 'changed limits')
  rejected(report, 'changed actor/payload/scope')
})

test('briefing rejects a mutable shared artifact that rewrites the prior ticket', async t => {
  const source = `${await solution('briefing-separated')}\noriginal = build_manifest\ncache = {}\ndef build_manifest(ticket):\n    cache.clear()\n    cache.update(original(ticket))\n    return cache\n`
  rejected(await candidate(t, 'briefing', source), 'changed limits')
})

test('capacity accepts Decimal outputs and isolated dataclass/helper imports', async t => {
  const source = `from __future__ import annotations\nfrom dataclasses import dataclass\nfrom helper import calculate\n@dataclass\nclass Estimate:\n    values: dict\ndef estimate(workload):\n    return Estimate(calculate(workload)).values\n`
  const helper = (await solution('capacity-fraction')).replace('def estimate(workload):', 'def rational_estimate(workload):') + `\nfrom decimal import Decimal, localcontext\ndef calculate(workload):\n    with localcontext() as context:\n        context.prec = 40\n        return {k: Decimal(v.numerator) / Decimal(v.denominator) for k, v in rational_estimate(workload).items()}\n`
  accepted(await candidate(t, 'capacity', source, { 'helper.py': helper }))
})

for (const [name, search, replacement, checkName] of [
  ['p95 used as mean', 'workload["mean_ms"] / 1000', 'workload.get("p95_ms", workload["mean_ms"]) / 1000', 'p95 is not mean'],
  ['ceil concurrency', 'peak * workload["mean_ms"] / 1000', 'math.ceil(peak * workload["mean_ms"] / 1000)', 'fractional concurrency'],
  ['peak used for storage', 'stored = workload["daily_requests"]', 'stored = workload["peak_multiplier"] * workload["daily_requests"]', 'published example'],
  ['MiB instead of MB', 'bandwidth / 1000000', 'bandwidth / 1048576', 'published example'],
  ['fractional days accepted', 'if workload["retention_days"] % 1:', 'if False:', 'fractional retention'],
  ['missing fields leak KeyError', 'value = workload.get(key)', 'value = workload[key]', 'missing'],
  ['invalid zero-traffic short circuit', '    for key, (low, high) in bounds.items():', '    if workload.get("daily_requests") == 0: return dict.fromkeys(("average_rps", "peak_rps", "in_flight", "peak_bytes_per_second", "retained_bytes", "peak_MB_per_second", "retained_GiB"), 0)\n    for key, (low, high) in bounds.items():', 'invalid despite zero traffic'],
] as const) test(`capacity rejects ${name}`, async t => {
  const source = await solution('capacity-float')
  assert.ok(source.includes(search))
  rejected(await candidate(t, 'capacity', source.replace(search, replacement)), checkName)
})

test('capacity rejects a sample-only calculator and mutation of rejected input', async t => {
  const source = await solution('capacity-float')
  rejected(await candidate(t, 'capacity', source + `\noriginal = estimate\ndef estimate(workload):\n    return original(dict(daily_requests=86400, peak_multiplier=4, mean_ms=250, response_bytes=2000, written_bytes=500, retention_days=7, storage_multiplier=2))\n`), 'fresh workload')
  rejected(await candidate(t, 'capacity', source.replace('raise ValueError(key)', 'workload.clear()\n            raise ValueError(key)')), 'Reject')
})

test('contract rejects a canned always-pass report without actual requests', async t => {
  const source = `def probe(base_url, scenario):\n    return {'status':'passed','checks':[{'name':n,'passed':True,'detail':'Looks fine'} for n in ('create','replay','conflict','read','query','missing','effects')]}\n`
  rejected(await candidate(t, 'contract', source), 'direct fresh')
})

for (const [name, search, replacement, checkName] of [
  ['status-only checker', 'checks.append(dict(name=name, passed=passed, detail=f"HTTP', 'checks.append(dict(name=name, passed=response.status == status, detail=f"HTTP', 'rejects header'],
  ['substring MIME check', '(response.getheader("Content-Type") or "").split(";", 1)[0].strip().lower() == "application/json"', '"application/json" in (response.getheader("Content-Type") or "").lower()', 'rejects media'],
  ['duplicate effect ignored', 'checks.append(dict(name=name, passed=passed, detail=f"HTTP', 'checks.append(dict(name=name, passed=passed or name == "effects", detail=f"HTTP', 'rejects duplicate'],
  ['exact serialization checker', 'passed = passed and isinstance(parsed, dict)', 'passed = passed and raw.decode() == json.dumps(expected) and isinstance(parsed, dict)', 'table fresh'],
  ['timeout reported as assertion failure', 'state = "timeout"', 'state = "failed"', 'distinguishes timeout'],
  ['unavailable reported as assertion failure', 'state = "unavailable"', 'state = "failed"', 'distinguishes unavailable'],
  ['Boolean quantity treated as one', 'type(parsed.get(key)) is type(value) and ', '', 'rejects boolean'],
] as const) test(`contract rejects ${name}`, async t => {
  const source = await solution('contract-http')
  assert.ok(source.includes(search))
  rejected(await candidate(t, 'contract', source.replace(search, replacement)), checkName)
})

test('contract rejects scenario mutation and extra requests, using server observations', async t => {
  const source = await solution('contract-http')
  rejected(await candidate(t, 'contract', source.replace('delivery = scenario["delivery"]', 'scenario["extra"] = "mutated"\n    delivery = scenario["delivery"]')), 'direct fresh')
  const extra = source.replace('target = urlsplit(base_url)', 'plan.append(("extra", "GET", "/stats", None, 200, {"effects": 1}))\n    target = urlsplit(base_url)').replace('checks=checks)', 'checks=[c for c in checks if c["name"] != "extra"])')
  rejected(await candidate(t, 'contract', extra), 'direct fresh')
})

test('workspace fixture edits cannot turn a bad probe into a pass', async t => {
  const source = (await solution('contract-http')).replace('state = "timeout"', 'state = "failed"')
  rejected(await candidate(t, 'contract', source, { 'fixtures.py': 'raise RuntimeError("Not the trusted checker fixture")\n' }), 'distinguishes timeout')
})

test('contract rejects checking headers only on creation and missing POST media type', async t => {
  const source = await solution('contract-http')
  const creationOnly = source.replace('response.getheader("X-Contract") == "delivery-v1"', '(name != "create" or response.getheader("X-Contract") == "delivery-v1")')
  rejected(await candidate(t, 'contract', creationOnly), 'rejects header:replay')
  rejected(await candidate(t, 'contract', source.replace('{"Content-Type": "application/json"}', '{}')), 'direct fresh')
})

test('fixture bind errors are environment-blocked rather than learner assertion failures', async t => {
  const source = `import sys\nfixtures = sys.modules['architect_owned_fixtures']\ndef unavailable_bind(self):\n    raise OSError('Synthetic local port denial')\nfixtures.LocalServer.server_bind = unavailable_bind\ndef probe(base_url, scenario):\n    raise AssertionError('Must not call the probe without a fixture')\n`
  const result = await candidate(t, 'contract', source)
  assert.notEqual(result.code, 0)
  assert.ok(result.checks.every(check => check.name === 'Environment blocked' && !check.passed), JSON.stringify(result))
})

test('contract observes unsupported-method traffic and rejects unattempted checks marked passed', async t => {
  const source = await solution('contract-http')
  const extraHead = source + `\noriginal = probe\ndef probe(base_url, scenario):\n    endpoint = urlsplit(base_url)\n    c = http.client.HTTPConnection(endpoint.hostname, endpoint.port, timeout=scenario['timeout_s'])\n    try:\n        c.request('HEAD', '/stats')\n        c.getresponse().read(8192)\n    finally:\n        c.close()\n    return original(base_url, scenario)\n`
  rejected(await candidate(t, 'contract', extraHead), 'direct fresh')
  const premature = source + `\noriginal = probe\ndef probe(base_url, scenario):\n    result = original(base_url, scenario)\n    if result['status'] == 'unavailable':\n        result['checks'][-1]['passed'] = True\n    return result\n`
  rejected(await candidate(t, 'contract', premature), 'distinguishes unavailable')
})

test('documented demos work from copied workspaces, including -I -B', async t => {
  for (const [mission, name] of [['briefing', 'briefing-grouped'], ['capacity', 'capacity-fraction'], ['contract', 'contract-urllib']] as const) {
    const directory = await workspace(t, mission, await solution(name))
    const before = await snapshot(directory)
    const modes = mission === 'contract' ? ['direct', 'table', 'duplicate', 'timeout', 'unavailable', 'before-deadline', 'after-deadline'] : mission === 'briefing' ? ['', 'ticket.json', 'ticket-v2.json', 'ticket-v3.json'] : ['', 'workload.json']
    for (const mode of modes) {
      const result = await run(python, ['-I', '-B', path.join(directory, 'demo.py'), ...(mode ? [mode] : [])], directory)
      assert.equal(result.code, 0, result.stderr)
      const output = JSON.parse(result.stdout)
      if (mission === 'contract') assert.equal(output.status, ['direct', 'table', 'before-deadline'].includes(mode) ? 'passed' : mode === 'duplicate' ? 'failed' : mode === 'after-deadline' ? 'timeout' : mode)
    }
    assert.deepEqual(await snapshot(directory), before)
  }
})

test('syntax/import failures return a final JSON check report and nonzero exit', async t => {
  rejected(await candidate(t, 'briefing', 'def build_manifest(:\n'), 'Run the architect lab')
  rejected(await candidate(t, 'capacity', 'raise RuntimeError("import failed")\n'), 'Run the architect lab')
})

test('the process deadline produces a final failed report for an endless function', async t => {
  const source = `import signal\ndef build_manifest(ticket):\n    signal.setitimer(signal.ITIMER_REAL, 0.05)\n    while True: pass\n`
  const result = await candidate(t, 'briefing', source)
  rejected(result, 'Run the architect lab')
  assert.ok(result.checks.some(check => check.detail.includes('EvaluationDeadline')))
})

test('profile successful verifiers and confirm all owned server threads are joined', async t => {
  for (const [mission, name] of [['briefing', 'briefing-grouped'], ['capacity', 'capacity-fraction'], ['contract', 'contract-http']] as const) {
    const directory = await workspace(t, mission, await solution(name))
    const report = await verify(directory, mission, true)
    accepted(report)
    const profile = JSON.parse(report.stderr.trim().split('\n').at(-1)!)
    assert.equal(profile.remaining_threads, 1, 'No owned server thread may survive verification')
    const bytes = Object.values(await snapshot(directory)).reduce((sum, value) => sum + Buffer.from(value, 'base64').length, 0)
    t.diagnostic(JSON.stringify({ mission, checks: report.checks.length, workspace_bytes: bytes, ...profile }))
  }
})

test('P2 review: ignoring delivery id and item must be rejected', async t => {
  const source = (await solution('contract-http')).replace('for key, value in expected.items()', 'for key, value in expected.items() if key not in ("id", "item")')
  const result = await candidate(t, 'contract', source)
  t.diagnostic(`identity-blind probe: ${result.checks.filter(c => c.passed).length}/${result.checks.length} checks passed`)
  assert.notEqual(result.code, 0, 'Identity-blind probe incorrectly accepted')
  assert.ok(result.checks.some(c => !c.passed && c.name.includes('wrong:create:id')))
})

test('P2 review: truncating fractional response and written bytes must be rejected', async t => {
  const source = (await solution('capacity-float')).replace('peak * workload["response_bytes"]', 'peak * int(workload["response_bytes"])').replace('* workload["written_bytes"]', '* int(workload["written_bytes"])')
  const result = await candidate(t, 'capacity', source)
  t.diagnostic(`byte-truncating calculator: ${result.checks.filter(c => c.passed).length}/${result.checks.length} checks passed`)
  assert.notEqual(result.code, 0, 'Fractional byte averages were truncated without rejection')
  assert.ok(result.checks.some(c => !c.passed && c.name.includes('fractional response bytes')))
  assert.ok(result.checks.some(c => !c.passed && c.name.includes('fractional written bytes')))
})

test('P2 review: iterable UTF-8 request bodies with chunked framing must pass', async t => {
  const source = (await solution('contract-http')).replace('json.dumps(body).encode("utf-8")', 'iter(bytes([octet]) for octet in json.dumps(body, ensure_ascii=False).encode("utf-8"))')
  const result = await candidate(t, 'contract', source)
  t.diagnostic(`chunked probe: ${result.checks.filter(c => c.passed).length}/${result.checks.length} checks passed; first failure: ${result.checks.find(c => !c.passed)?.detail ?? 'none'}`)
  assert.equal(result.code, 0, 'A valid iterable/chunked client was rejected')
})

test('P2 review: ignoring timeout_s with a fixed one-second timeout must be rejected', async t => {
  const source = (await solution('contract-http')).replace('timeout=scenario["timeout_s"]', 'timeout=1.0')
  const result = await candidate(t, 'contract', source)
  t.diagnostic(`fixed-one-second probe: ${result.checks.filter(c => c.passed).length}/${result.checks.length} checks passed`)
  assert.notEqual(result.code, 0, 'Probe ignoring the supplied deadline incorrectly accepted')
  assert.ok(result.checks.some(c => !c.passed && c.name.includes('budget')))
})

test('P2 review: every required response field needs presence and value checks', async t => {
  const source = await solution('contract-http')
  const required: Record<string, string[]> = { create: ['id', 'item', 'quantity'], replay: ['id', 'item', 'quantity'], conflict: ['error'], read: ['id', 'item', 'quantity', 'view'], query: ['id', 'quantity', 'view'], missing: ['error'], effects: ['effects'] }
  const defaultMissing = source.replace('parsed.get(key)', 'parsed.get(key, value)').replace('parsed[key] == value', 'parsed.get(key, value) == value')
  const typeOnly = source.replace(' and parsed[key] == value', '')
  for (const [fault, mutant] of [['missing', defaultMissing], ['wrong', typeOnly]]) {
    const result = await candidate(t, 'contract', mutant!)
    for (const [target, fields] of Object.entries(required)) for (const field of fields) {
      const name = `HTTP probe rejects ${fault}:${target}:${field}`
      assert.equal(result.checks.find(c => c.name === name)?.passed, false, `${name} must catch this mutant`)
    }
  }
})

test('P2 review: a fixed short timeout rejects an in-budget delayed response', async t => {
  const source = (await solution('contract-http')).replace('timeout=scenario["timeout_s"]', 'timeout=0.3')
  const result = await candidate(t, 'contract', source)
  rejected(result, 'HTTP budget: create before deadline')
  rejected(result, 'HTTP budget: effects before deadline')
})

test('P2 review: a late timeout label cannot hide an exceeded physical return budget', async t => {
  const source = 'import time\n' + (await solution('contract-http'))
    .replace('timeout=scenario["timeout_s"]', 'timeout=1.0')
    .replace('            connection.request(', '            started = time.monotonic()\n            connection.request(')
    .replace('            raw = response.read(8192)', '            raw = response.read(8192)\n            if time.monotonic() - started > 0.7:\n                raise TimeoutError("Late synthetic classification")')
  const result = await candidate(t, 'contract', source)
  const failures = result.checks.filter(c => !c.passed && c.detail.includes('Return budget exceeded'))
  assert.equal(failures.length, 2, JSON.stringify(result))
  for (const check of failures) t.diagnostic(`${check.name}: ${check.detail}`)
})

test('P2 review: actual HTTP chunk framing preserves payloads and rejects bounded malformed input', async t => {
  const directory = await workspace(t, 'contract')
  const code = `import http.client, importlib.util, json, socket, sys
spec = importlib.util.spec_from_file_location('owned_fixtures', sys.argv[1])
fixtures = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = fixtures
spec.loader.exec_module(fixtures)
delivery = {'id': 'frame-1', 'item': '雪 supply', 'quantity': 3}
raw = json.dumps(delivery, ensure_ascii=False).encode('utf-8')
def frame(data, width=17, extensions=False):
    parts = []
    for index in range(0, len(data), width):
        chunk = data[index:index+width]
        suffix = b';unknown="ignored"' if extensions else b''
        parts.append(('%x' % len(chunk)).encode() + suffix + b'\\r\\n' + chunk + b'\\r\\n')
    return b''.join(parts) + b'0\\r\\n' + (b'X-Note: ignored\\r\\nContent-Type: text/plain\\r\\n' if extensions else b'') + b'\\r\\n'
padded = raw + b' ' * (4096 - len(raw))
cases = [
    ('content-length boundary', padded, False, {}, 201),
    ('chunked Unicode/extensions/trailers', frame(raw, 1, True), True, {}, 201),
    ('chunked payload boundary', frame(padded), True, {}, 201),
    ('oversized chunk', b'1001\\r\\n', True, {}, 413),
    ('oversized aggregate', frame(padded + b' ', 2048), True, {}, 413),
    ('invalid hex', b'Z\\r\\n', True, {}, 400),
    ('missing chunk CRLF', b'1\\r\\nxZZ0\\r\\n\\r\\n', True, {}, 400),
    ('truncated payload', b'5\\r\\nxx', True, {}, 400),
    ('truncated trailers', b'0\\r\\nX-Note: incomplete\\r\\n', True, {}, 400),
    ('metadata line bound', b'1;' + b'x' * 4096 + b'\\r\\nx\\r\\n0\\r\\n\\r\\n', True, {}, 413),
    ('ambiguous framing', frame(raw), True, {'Content-Length': str(len(raw))}, 400),
]
completed = 0
for style in ('direct', 'table'):
    for label, body, chunked, extra, expected in cases:
        with fixtures.fixture(style) as (url, server):
            c = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=2)
            try:
                headers = {'Content-Type': 'application/json', **extra}
                if chunked: headers['Transfer-Encoding'] = 'chunked'
                c.request('POST', '/deliveries', body, headers)
                c.sock.shutdown(socket.SHUT_WR)
                response = c.getresponse()
                content = response.read(8192)
                assert response.status == expected, (style, label, response.status, content)
                if expected == 201:
                    parsed = json.loads(content)
                    assert all(parsed[k] == v for k, v in delivery.items())
                    assert server.records == {delivery['id']: delivery} and server.effects == 1
                    assert server.request_media == ['application/json']
                else:
                    assert server.records == {} and server.effects == 0
                completed += 1
            finally:
                c.close()
print(json.dumps({'real_framing_cases': completed}))
`
  const before = await snapshot(directory)
  const result = await run(python, ['-I', '-B', '-c', code, path.join(root, 'labs/contract/fixtures.py')], directory)
  assert.equal(result.code, 0, result.stderr)
  assert.deepEqual(JSON.parse(result.stdout), { real_framing_cases: 22 })
  assert.deepEqual(await snapshot(directory), before)
})
