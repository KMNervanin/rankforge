import assert from 'node:assert/strict'
import { mkdtemp, rm, writeFile, readFile } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { Labs, run, root } from '../server/labs.js'
import { bonusPassed } from '../shared/checks.js'

const daemon = await run('docker', ['info', '--format', '{{.ServerVersion}}'], root, 15000)
assert.equal(daemon.code, 0, 'Docker daemon must already be accessible; this check never starts or reconfigures it.')
const home = await mkdtemp(path.join(os.tmpdir(), 'rankforge-gateway-acceptance-'))
const labs = new Labs(home)
let workspace = ''
let up = false
try {
  workspace = await labs.prepare('gateway', 'guided')
  const file = path.join(workspace, 'compose.yaml')
  const compose = await readFile(file, 'utf8')
  await writeFile(file, compose.replace('127.0.0.1:${GATEWAY_PORT:-45103}:8080', '127.0.0.1::8080'))
  const started = await run('docker', ['compose', 'up', '-d', '--wait', '--wait-timeout', '60'], workspace, 120000)
  up = true
  assert.equal(started.code, 0, started.stderr)
  const broken = await labs.check('gateway')
  assert.equal(broken.supported, true, JSON.stringify(broken))
  assert.equal(broken.passed, false, 'The broken gateway must fail')
  assert.equal(bonusPassed(broken.checks), false, 'The broken gateway must not earn the hidden bonus')
  const port = await run('docker', ['compose', 'port', 'gateway', '8080'], workspace)
  assert.equal(port.code, 0, port.stderr)
  const address = port.stdout.trim()
  assert.match(address, /^127\.0\.0\.1:\d+$/)
  const scenarios = [
    { name: 'prefix-uri', passed: true, bonus: true, routes: 'location /api/ { proxy_pass http://relay:8000/; }' },
    { name: 'rewrite-named-upstream', passed: true, bonus: true, upstream: 'upstream backend { server relay:8000; }', routes: 'location /api/ { rewrite ^/api/(.*)$ /$1 break; proxy_pass http://backend; }' },
    // Passes the contract but forwards the bare /api/ unchanged: the hidden bonus stays RED while the mission passes.
    { name: 'rewrite-nonempty-rest', passed: true, bonus: false, routes: 'location /api/ { rewrite ^/api/(.+)$ /$1 break; proxy_pass http://relay:8000; }' },
    { name: 'lost-query', passed: false, failedCheck: 'queries preserved', routes: 'location /api/ { rewrite ^/api/(.*)$ /$1? break; proxy_pass http://relay:8000; }' },
    { name: 'health-only', passed: false, failedCheck: 'queries preserved', routes: 'location = /api/health { proxy_pass http://relay:8000/health; }' },
    { name: 'redirect', passed: false, failedCheck: 'GET /api/health', routes: 'location /api/ { return 302 /health; }' },
    { name: 'wrong-media-type', passed: false, failedCheck: 'GET /api/health', routes: 'location /api/ { proxy_pass http://relay:8000/; proxy_hide_header Content-Type; add_header Content-Type "text/plain; note=application/json" always; add_header X-Rankforge-Scenario "wrong-media-type" always; }' },
  ]
  const results = []
  for (const scenario of scenarios) {
    await writeFile(path.join(workspace, 'nginx.conf'), `events {}\nhttp { ${scenario.upstream ?? ''} server { listen 8080; add_header X-Rankforge-Scenario "${scenario.name}" always; ${scenario.routes} location / { return 404; } } }\n`)
    const syntax = await run('docker', ['compose', 'exec', '-T', 'gateway', 'nginx', '-t'], workspace)
    assert.equal(syntax.code, 0, syntax.stderr)
    const reload = await run('docker', ['compose', 'exec', '-T', 'gateway', 'nginx', '-s', 'reload'], workspace)
    assert.equal(reload.code, 0, reload.stderr)
    // A negative verdict must belong to the new config, not an old worker during reload.
    let applied = false
    for (let attempt = 0; !applied && attempt < 20; attempt++) {
      const response = await fetch(`http://${address}/api/health`, { redirect: 'manual', signal: AbortSignal.timeout(5000), headers: { connection: 'close' } })
      applied = response.headers.get('x-rankforge-scenario') === scenario.name
      await response.text()
      if (!applied) await new Promise((resolve) => setTimeout(resolve, 100))
    }
    assert.equal(applied, true, `New nginx config was not observed: ${scenario.name}`)
    const result = await labs.check('gateway')
    assert.equal(result.supported, true, JSON.stringify(result))
    assert.equal(result.passed, scenario.passed, `${scenario.name}: ${JSON.stringify(result)}`)
    if (scenario.failedCheck) assert.ok(result.checks.some((item) => !item.passed && item.name.includes(scenario.failedCheck!)), JSON.stringify(result))
    if ('bonus' in scenario) assert.equal(bonusPassed(result.checks), scenario.bonus, `${scenario.name} bonus: ${JSON.stringify(result.checks.filter((item) => item.optional))}`)
    results.push({ scenario: scenario.name, expectedPass: scenario.passed, result })
  }
  console.log(JSON.stringify({ mission: 'gateway', broken: { passed: broken.passed, checks: broken.checks }, results, transport: 'real Docker Engine and nginx', workspace }, null, 2))
} finally {
  if (up) {
    const down = await run('docker', ['compose', 'down', '--volumes', '--remove-orphans'], workspace, 60000)
    assert.equal(down.code, 0, `Owned acceptance project cleanup failed: ${down.stderr}`)
    const remaining = await run('docker', ['compose', 'ps', '-a', '-q'], workspace)
    assert.equal(remaining.code, 0, remaining.stderr)
    assert.equal(remaining.stdout.trim(), '', 'Owned acceptance containers still exist')
  }
  await rm(home, { recursive: true, force: true })
}
