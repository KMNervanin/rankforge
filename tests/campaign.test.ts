import test from 'node:test'
import assert from 'node:assert/strict'
import { copyFile, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { createApp } from '../server/app.js'
import { root } from '../server/labs.js'
import { currentContractVersion } from '../shared/contracts.js'
import type { CheckResult, Snapshot } from '../shared/types.js'
import { llmConfig, startLlmStub } from './llm-stub.js'

test('registered guild and bonus labs execute through the API, preserve work, award once and equip owned rewards', async t => {
  const home = await mkdtemp(path.join(os.tmpdir(), 'rankforge-campaign-'))
  const { app, labs, store, browserToken } = await createApp({ home, provider: { model: 'not-used', hasAccount: () => false, complete: async () => { throw new Error('Technical completion must not call a model') } }, launchEditor: async () => { throw new Error('Acceptance must not open the editor') } })
  t.after(async () => { await app.close(); await rm(home, { recursive: true, force: true }) })
  const stub = await startLlmStub()
  t.after(() => stub.close())
  const post = (url: string, payload: object = {}) => app.inject({ method: 'POST', url, headers: { 'x-rankforge-token': browserToken }, payload })
  assert.equal((await post('/api/profile/equip', { id: 'relay-frame' })).statusCode, 409)
  assert.equal((await post('/api/missions/briefing/start', { openEditor: false })).statusCode, 409)
  assert.equal((await post('/api/missions/http-trial/start', { openEditor: false })).statusCode, 409)
  // Prerequisites are controlled state fixtures; all four new lab effects below run real checkers.
  const prerequisite: CheckResult = { passed: true, supported: true, contractVersion: currentContractVersion, checkedAt: new Date().toISOString(), checks: [{ name: 'Controlled prerequisite fixture', passed: true, detail: 'Not a live lab run' }], output: '' }
  for (const id of ['signal', 'vault', 'gateway', 'echo', 'ledger', 'recovery']) store.saveCheck(id, prerequisite)
  const artifacts = [
    ['briefing', 'manifest.py', 'architect/briefing-grouped.py'],
    ['capacity', 'capacity.py', 'architect/capacity-fraction.py'],
    ['contract', 'probe.py', 'architect/contract-http.py'],
    ['http-trial', 'service.py', 'http-trial/sorted.py'],
    ['price', 'client.py', 'price/urllib.py'],
  ]
  for (const [id, file, source] of artifacts) {
    const started = await post(`/api/missions/${id}/start`, { openEditor: false })
    assert.equal(started.statusCode, 200, started.body)
    if (id === 'price') await writeFile(path.join(labs.workspace(id), 'llm.json'), llmConfig(stub.baseUrl, stub.model))
    const failed = (await post(`/api/missions/${id}/check`)).json<Snapshot>().missions.find(m => m.id === id)!.checks!
    assert.equal(failed.supported, true, JSON.stringify(failed))
    assert.equal(failed.passed, false, JSON.stringify(failed))
    assert.equal(failed.contractVersion, currentContractVersion)
    const workspace = labs.workspace(id!)
    await copyFile(path.join(root, 'tests/solutions', source!), path.join(workspace, file!))
    const good = (await post(`/api/missions/${id}/check`)).json<Snapshot>()
    assert.equal(good.missions.find(m => m.id === id)!.checks!.passed, true, JSON.stringify(good.missions.find(m => m.id === id)!.checks))
    const repeated = (await post(`/api/missions/${id}/check`)).json<Snapshot>()
    assert.equal(repeated.xp, good.xp)
    assert.deepEqual(repeated.progression!.inventory, good.progression!.inventory)
    const saved = await readFile(path.join(workspace, file!), 'utf8')
    await post(`/api/missions/${id}/start`, { openEditor: false })
    assert.equal(await readFile(path.join(workspace, file!), 'utf8'), saved)
  }
  const equipped = await post('/api/profile/equip', { id: 'relay-frame' })
  assert.equal(equipped.statusCode, 200)
  assert.equal(equipped.json<Snapshot>().progression!.inventory.equippedCosmeticId, 'relay-frame')
  assert.equal((await post('/api/profile/equip', { id: 'starter-chip' })).statusCode, 409)
  assert.equal((await app.inject({ method: 'POST', url: '/api/profile/equip', payload: { id: 'relay-frame' } })).statusCode, 403)
  assert.equal(equipped.json<Snapshot>().exchanges.length, 0)
})
