import test from 'node:test'
import assert from 'node:assert/strict'
import { execFile } from 'node:child_process'
import { promisify } from 'node:util'
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { Store } from '../server/store.js'
import { currentContractVersion } from '../shared/contracts.js'
import { skillBranches } from '../shared/progression.js'
import type { CheckResult } from '../shared/types.js'

// Controlled store-boundary fixtures, not claims of a live lab or tutor evaluation.
const verified: CheckResult = { passed: true, supported: true, contractVersion: currentContractVersion, checkedAt: '2026-10-06T00:00:00Z', checks: [{ name: 'Controlled contract fixture', passed: true, detail: 'State-machine test only.' }], output: 'Controlled fixture' }
const connection = { signedIn: false, model: 'unused', paused: false, reason: null, editorConnected: false }
const snapshot = (store: Store) => store.snapshot(connection).progression!
const branch = (store: Store, id: string) => snapshot(store).branches.find((item) => item.id === id)!
function setup(t: test.TestContext) {
  const home = mkdtempSync(path.join(os.tmpdir(), 'rankforge-rewards-'))
  const store = new Store(home)
  t.after(() => { store.close(); rmSync(home, { recursive: true, force: true }) })
  return store
}

test('only a supported current-contract pass creates new evidence and inventory', (t) => {
  const store = setup(t)
  for (const result of [
    { ...verified, passed: false }, { ...verified, supported: false },
    { ...verified, contractVersion: undefined }, { ...verified, contractVersion: 'old' },
    { ...verified, contractVersion: 'future' }, { ...verified, checks: [] },
    { ...verified, checks: [{ name: 'Contradiction', passed: false, detail: 'Must not grant.' }] },
  ]) {
    store.saveCheck('signal', result)
    assert.equal(snapshot(store).evidence.length, 0)
    assert.equal(snapshot(store).inventory.bankedCharge, 0)
    assert.equal(branch(store, 'http').level, 0)
  }
  assert.equal(store.snapshot(connection).xp, 120, 'Legacy completion and XP remain compatible')
  store.saveCheck('signal', verified)
  assert.equal(snapshot(store).evidence.length, 1)
  assert.equal(branch(store, 'http').level, 1)
  assert.equal(snapshot(store).inventory.bankedCharge, 25)
})

test('one mission cannot farm checkpoints, chips or XP through repeats or changed timestamps', (t) => {
  const store = setup(t)
  store.saveCheck('signal', verified)
  const earned = snapshot(store)
  for (let i = 0; i < 12; i++) store.saveCheck('signal', { ...verified, checkedAt: new Date(1800000000000 + i).toISOString() })
  assert.deepEqual(snapshot(store), earned)
  assert.equal(store.snapshot(connection).xp, 120)
  assert.equal(branch(store, 'http').checkpoints[1]!.missingMissionIds.join(','), 'gateway')
  assert.equal(snapshot(store).unlockedMissionIds.length, 0)
})

test('old saves migrate idempotently without rewarding legacy checks or losing work', () => {
  const home = mkdtempSync(path.join(os.tmpdir(), 'rankforge-legacy-rewards-'))
  let store = new Store(home)
  try {
    const workspace = path.join(home, 'my-service.py')
    writeFileSync(workspace, '# unfinished learner code\n')
    store.select('signal', workspace)
    store.hint('signal')
    store.saveCheck('signal', { ...verified, contractVersion: undefined })
    store.submit('saved-answer', 'signal', 'Do not lose this explanation.', 'debrief')
    store.fail('saved-answer', 'Controlled quota pause', true)
    const before = store.progress('signal')
    const answer = store.exchange('saved-answer')
    store.db.exec('DROP TABLE reward_equipment; DROP TABLE reward_grants; DROP TABLE skill_milestones; DROP TABLE skill_evidence;')
    store.close()
    store = new Store(home)
    assert.deepEqual(store.progress('signal'), before)
    assert.equal(store.snapshot(connection).xp, 120)
    assert.equal(snapshot(store).evidence.length, 0)
    assert.equal(snapshot(store).inventory.bankedCharge, 0)
    assert.deepEqual(store.exchange('saved-answer'), answer)
    assert.equal(readFileSync(workspace, 'utf8'), '# unfinished learner code\n')
    store.saveCheck('signal', verified)
    const earned = snapshot(store)
    assert.equal(earned.evidence[0]!.mode, 'guided')
    assert.equal(earned.inventory.bankedCharge, 25)
    assert.deepEqual(store.exchange('saved-answer'), answer)
    assert.equal(store.get('pause'), 'Controlled quota pause')
    assert.equal(store.progress('signal').completed, before.completed)
    assert.equal(store.progress('signal').workspace, before.workspace)
    store.close()
    store = new Store(home)
    store.saveCheck('signal', verified)
    assert.deepEqual(snapshot(store), earned)
  } finally { store.close(); rmSync(home, { recursive: true, force: true }) }
})

test('HTTP bonus requires durable Applied evidence as well as legacy prerequisites', (t) => {
  const store = setup(t)
  assert.throws(() => store.assertAvailable('http-trial'), /prerequisite/)
  for (const id of ['signal', 'gateway']) store.saveCheck(id, { ...verified, contractVersion: undefined })
  store.set('active', 'http-trial')
  assert.equal(store.views().find((item) => item.id === 'http-trial')!.status, 'locked')
  assert.throws(() => store.assertAvailable('http-trial'), /HTTP Applied/)
  assert.throws(() => store.saveCheck('http-trial', verified), /HTTP Applied/)
  assert.equal(store.progress('http-trial').checks, null)
  store.saveCheck('signal', verified)
  assert.throws(() => store.assertAvailable('http-trial'), /HTTP Applied/)
  store.saveCheck('gateway', verified)
  assert.equal(branch(store, 'http').level, 2)
  assert.deepEqual(snapshot(store).unlockedMissionIds, ['http-trial'])
  store.assertAvailable('http-trial')
  assert.equal(store.progress('recovery').completed, null, 'Guild progress is not a bonus prerequisite')
  store.db.prepare('UPDATE progress SET completed=NULL WHERE id=?').run('gateway')
  assert.throws(() => store.assertAvailable('http-trial'), /prerequisite/, 'Durable unlock alone does not replace prerequisites')
})

test('guided practice earns identical rewards; transfer mode belongs to the trial evidence', (t) => {
  const guided = setup(t), independent = setup(t)
  for (const store of [guided, independent]) {
    store.hint('signal')
    store.saveCheck('signal', verified)
    store.saveCheck('gateway', verified)
  }
  guided.hint('http-trial')
  for (const store of [guided, independent]) store.saveCheck('http-trial', verified)
  const transfer = (store: Store) => branch(store, 'http').checkpoints[2]!.evidence.find((item) => item.missionId === 'http-trial')!
  assert.equal(transfer(guided).mode, 'guided')
  assert.equal(transfer(guided).hintsUsed, 1)
  assert.equal(transfer(independent).mode, 'independent')
  assert.equal(branch(guided, 'http').level, 3)
  assert.equal(branch(independent, 'http').level, 3)
  assert.equal(snapshot(guided).inventory.bankedCharge, snapshot(independent).inventory.bankedCharge)
  assert.equal(guided.snapshot(connection).xp, independent.snapshot(connection).xp)
  assert.equal(guided.language().evidenceCount, 0, 'English/model evaluation is not a reward gate')
})

test('coaching records supported practice but earns nothing before technical verification', (t) => {
  const store = setup(t)
  store.submit('help', 'signal', 'Controlled request for help.', 'coach')
  store.finish('help', 'Controlled coaching fixture.', null)
  assert.equal(snapshot(store).inventory.chips.length, 0)
  store.saveCheck('signal', verified)
  assert.equal(snapshot(store).evidence[0]!.mode, 'guided')
  assert.equal(snapshot(store).inventory.bankedCharge, 25)
})

test('failed later checks and restarts retain milestone evidence, rewards and equipped frame', () => {
  const home = mkdtempSync(path.join(os.tmpdir(), 'rankforge-reward-restart-'))
  let store = new Store(home)
  try {
    store.saveCheck('signal', verified)
    assert.throws(() => store.equipCosmetic('relay-frame'), /Earn this cosmetic/)
    assert.throws(() => store.equipCosmetic('starter-chip'), /Earn this cosmetic/)
    assert.throws(() => store.equipCosmetic('unknown'), /Earn this cosmetic/)
    store.saveCheck('gateway', verified)
    store.equipCosmetic('relay-frame')
    store.equipCosmetic('relay-frame')
    const earned = snapshot(store)
    store.hint('gateway')
    store.saveCheck('gateway', { ...verified, passed: false })
    store.saveCheck('signal', { ...verified, supported: false })
    assert.deepEqual(snapshot(store), earned)
    store.close()
    store = new Store(home)
    assert.deepEqual(snapshot(store), earned)
    assert.equal(snapshot(store).inventory.equippedCosmeticId, 'relay-frame')
    store.assertAvailable('http-trial')
    store.equipCosmetic('default')
    assert.equal(snapshot(store).inventory.equippedCosmeticId, null)
    assert.deepEqual(snapshot(store).inventory.cosmetics, earned.inventory.cosmetics)
    assert.deepEqual(snapshot(store).inventory.chips, earned.inventory.chips)
    store.close()
    store = new Store(home)
    assert.equal(snapshot(store).inventory.equippedCosmeticId, null)
  } finally { store.close(); rmSync(home, { recursive: true, force: true }) }
})

test('all four paths require distinct current evidence and have a finite total reserve', (t) => {
  const store = setup(t)
  const ids = ['signal', 'vault', 'gateway', 'echo', 'ledger', 'recovery', 'briefing', 'capacity', 'contract', 'http-trial']
  for (const id of ids) store.saveCheck(id, verified)
  for (const definition of skillBranches) {
    const path = branch(store, definition.id)
    assert.equal(path.level, 3)
    for (const checkpoint of path.checkpoints) {
      assert.equal(new Set(checkpoint.evidence.map((item) => item.missionId)).size, checkpoint.missionIds.length)
      assert.ok(checkpoint.evidence.every((item) => item.contractVersion === currentContractVersion))
    }
  }
  const earned = snapshot(store)
  assert.equal(earned.inventory.chips.length, 13)
  assert.equal(earned.inventory.bankedCharge, 140)
  assert.deepEqual(earned.inventory.cosmetics.map((item) => item.id).sort(), ['archive-frame', 'relay-frame'])
  for (const id of ids) store.saveCheck(id, verified)
  assert.deepEqual(snapshot(store), earned)
  store.equipCosmetic('archive-frame')
  assert.equal(snapshot(store).inventory.equippedCosmeticId, 'archive-frame')
  store.equipCosmetic('relay-frame')
  assert.equal(snapshot(store).inventory.equippedCosmeticId, 'relay-frame')
  assert.equal(snapshot(store).inventory.bankedCharge, 140)
})

test('historic evidence does not satisfy a new checkpoint but prior levels remain earned', (t) => {
  const store = setup(t)
  store.saveCheck('signal', verified)
  store.db.prepare('UPDATE skill_evidence SET contract_version=?,evidence=? WHERE mission_id=?').run('old', JSON.stringify({ ...snapshot(store).evidence[0], contractVersion: 'old' }), 'signal')
  store.saveCheck('gateway', verified)
  assert.equal(branch(store, 'http').level, 1)
  assert.deepEqual(branch(store, 'http').checkpoints[1]!.missingMissionIds, ['signal'])
  store.saveCheck('signal', verified)
  assert.equal(branch(store, 'http').level, 2)
  assert.equal(snapshot(store).inventory.bankedCharge, 35, 'Earlier checkpoint/starter must not pay twice')
})

test('a grant failure rolls back check, completion, XP, evidence, milestones and inventory together', (t) => {
  const store = setup(t)
  store.submit('pending', 'signal', 'A preserved answer.', 'debrief')
  const before = store.snapshot(connection)
  store.db.exec("CREATE TRIGGER reject_reward BEFORE INSERT ON reward_grants WHEN NEW.id='http-1-chip' BEGIN SELECT RAISE(ABORT, 'Controlled reward failure'); END;")
  assert.throws(() => store.saveCheck('signal', verified), /Controlled reward failure/)
  assert.deepEqual(store.snapshot(connection), before)
  store.db.exec('DROP TRIGGER reject_reward')
  store.saveCheck('signal', verified)
  assert.equal(snapshot(store).inventory.bankedCharge, 25)
  assert.equal(store.exchange('pending')!.status, 'pending')
})

test('concurrent processes serialize repeated grants and remain idempotent after reopen', async () => {
  const home = mkdtempSync(path.join(os.tmpdir(), 'rankforge-reward-concurrent-'))
  const initial = new Store(home)
  initial.close()
  try {
    const source = `import {Store} from ${JSON.stringify(new URL('../server/store.ts', import.meta.url).href)}; const store=new Store(${JSON.stringify(home)}); try {for(let i=0;i<8;i++) for(const id of ['signal','gateway']) store.saveCheck(id,${JSON.stringify(verified)});} finally {store.close();}`
    await Promise.all(Array.from({ length: 4 }, () => promisify(execFile)(process.execPath, ['--import', 'tsx', '--input-type=module', '-e', source], { timeout: 20000 })))
    const store = new Store(home)
    try {
      assert.equal(store.snapshot(connection).xp, 320)
      assert.equal(snapshot(store).evidence.length, 2)
      assert.equal(branch(store, 'http').level, 2)
      assert.equal(snapshot(store).inventory.chips.length, 3)
      assert.equal(snapshot(store).inventory.bankedCharge, 35)
      assert.equal(snapshot(store).inventory.cosmetics.length, 1)
    } finally { store.close() }
  } finally { rmSync(home, { recursive: true, force: true }) }
})
