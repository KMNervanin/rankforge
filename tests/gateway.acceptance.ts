import assert from 'node:assert/strict'
import { mkdtemp, rm, writeFile, readFile } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { Labs, run } from '../server/labs.js'

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
  await writeFile(path.join(workspace, 'nginx.conf'), `events {}\nhttp { server { listen 8080; location /api/ { proxy_pass http://relay:8000/; } location / { return 404; } } }\n`)
  const reload = await run('docker', ['compose', 'exec', '-T', 'gateway', 'nginx', '-s', 'reload'], workspace)
  assert.equal(reload.code, 0, reload.stderr)
  let fixed = await labs.check('gateway')
  for (let attempt = 0; !fixed.passed && attempt < 10; attempt++) { await new Promise((resolve) => setTimeout(resolve, 500)); fixed = await labs.check('gateway') }
  assert.equal(fixed.passed, true, JSON.stringify(fixed, null, 2))
  console.log(JSON.stringify({ mission: 'gateway', broken: { passed: broken.passed, checks: broken.checks }, fixed, transport: 'real Docker Engine and nginx', workspace }, null, 2))
} finally {
  if (up) {
    const down = await run('docker', ['compose', 'down', '--volumes', '--remove-orphans'], workspace, 60000)
    if (down.code) console.error('Owned acceptance project cleanup failed:', down.stderr)
  }
  await rm(home, { recursive: true, force: true })
}
