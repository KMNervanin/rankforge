import test from 'node:test'
import assert from 'node:assert/strict'
import { spawn, type ChildProcess } from 'node:child_process'
import { createServer } from 'node:net'
import { once } from 'node:events'
import { mkdtemp, rm, readFile } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { createHash } from 'node:crypto'
import { root } from '../server/labs.js'

test('the documented server entry point preserves saves across restart and rejects another owner before rotating the bridge', async () => {
  const home = await mkdtemp(path.join(os.tmpdir(), 'rankforge-runtime-'))
  const reserve = createServer()
  reserve.listen(0, '127.0.0.1'); await once(reserve, 'listening')
  const address = reserve.address()
  assert.ok(address && typeof address === 'object')
  const port = address.port
  await new Promise<void>((resolve) => reserve.close(() => resolve()))
  const children: ChildProcess[] = []
  const launch = () => {
    const child = spawn(process.execPath, ['--import', 'tsx', 'server/main.ts'], { cwd: root, env: { ...process.env, RANKFORGE_HOME: home, RANKFORGE_PORT: String(port) }, stdio: ['ignore', 'pipe', 'pipe'] })
    children.push(child)
    let output = ''
    child.stdout!.on('data', (data: Buffer) => { output += data.toString() })
    child.stderr!.on('data', (data: Buffer) => { output += data.toString() })
    return { child, output: () => output }
  }
  const wait = async (condition: () => boolean) => {
    for (let attempt = 0; attempt < 100; attempt++) { if (condition()) return; await new Promise((resolve) => setTimeout(resolve, 30)) }
    throw new Error('Service lifecycle did not reach the expected state.')
  }
  const stop = async (child: ChildProcess) => {
    if (child.exitCode !== null || child.signalCode !== null) return
    const exited = once(child, 'exit'); child.kill('SIGTERM'); await exited
  }
  try {
    const first = launch()
    await wait(() => first.output().includes('Rankforge is ready'))
    const origin = `http://127.0.0.1:${port}`
    const initial = await fetch(`${origin}/api/bootstrap`).then((response) => response.json())
    const response = await fetch(`${origin}/api/missions/signal/start`, { method: 'POST', headers: { 'Content-Type': 'application/json', 'x-rankforge-token': initial.token }, body: JSON.stringify({ openEditor: false }) })
    assert.equal(response.status, 200)
    const oldBridge = createHash('sha256').update(await readFile(path.join(home, 'bridge.json'))).digest('hex')
    const competing = launch()
    await wait(() => competing.child.exitCode !== null)
    assert.notEqual(competing.child.exitCode, 0)
    assert.match(competing.output(), /already owns/)
    assert.equal(createHash('sha256').update(await readFile(path.join(home, 'bridge.json'))).digest('hex'), oldBridge)
    await stop(first.child)
    const second = launch()
    await wait(() => second.output().includes('Rankforge is ready'))
    const resumed = await fetch(`${origin}/api/bootstrap`).then((res) => res.json())
    assert.equal(resumed.snapshot.activeMissionId, 'signal')
    assert.ok(resumed.snapshot.missions[0].workspace)
    assert.notEqual(resumed.token, initial.token)
    await stop(second.child)
  } finally { await Promise.all(children.map(stop)); await rm(home, { recursive: true, force: true }) }
})
