import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtempSync, rmSync } from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { Store } from '../server/store.js'
import { currentContractVersion } from '../shared/contracts.js'
import { bonusChecks, bonusPassed, requiredChecks, requiredPassed } from '../shared/checks.js'
import type { Check, CheckResult } from '../shared/types.js'

// Controlled check shapes for the shared pass/bonus rules, not claims of a live lab run.
const required: Check = { name: 'Published contract', passed: true, detail: 'verified' }
const bonusMissed: Check = { name: 'bonus: hidden edge case', passed: false, detail: 'not yet', optional: true }
const bonusEarned: Check = { ...bonusMissed, passed: true, detail: 'verified' }
const connection = { signedIn: false, model: 'unused', paused: false, reason: null, editorConnected: false }

test('required and bonus checks are derived from the optional flag; the bonus needs every hidden check to pass', () => {
  const checks = [required, bonusMissed, { ...bonusEarned, name: 'bonus: second' }]
  assert.deepEqual(requiredChecks(checks), [required])
  assert.equal(bonusChecks(checks).length, 2)
  assert.equal(requiredPassed(checks), true)
  assert.equal(bonusPassed(checks), false, 'one missed hidden check means no bonus')
  assert.equal(bonusPassed([required, bonusEarned]), true)
  assert.equal(bonusPassed([required]), false, 'a run without hidden checks earns no bonus')
  assert.equal(requiredPassed([bonusEarned]), false, 'a run with only hidden checks proves nothing')
  assert.equal(requiredPassed([{ ...required, passed: false }, bonusEarned]), false)
})

test('a failing hidden check never fails the mission and never blocks completion, XP or skill evidence', (t) => {
  const home = mkdtempSync(path.join(os.tmpdir(), 'rankforge-bonus-'))
  const store = new Store(home)
  t.after(() => { store.close(); rmSync(home, { recursive: true, force: true }) })
  const result: CheckResult = { passed: requiredPassed([required, bonusMissed]), supported: true, contractVersion: currentContractVersion, checkedAt: '2026-10-08T00:00:00Z', checks: [required, bonusMissed], output: '' }
  assert.equal(result.passed, true)
  store.saveCheck('signal', result)
  const snapshot = store.snapshot(connection)
  assert.equal(snapshot.missions.find((item) => item.id === 'signal')!.status, 'completed')
  assert.equal(snapshot.xp, 120)
  assert.equal(snapshot.progression!.evidence.length, 1, 'skill evidence is recorded despite the missed bonus')
  assert.equal(bonusPassed(snapshot.missions.find((item) => item.id === 'signal')!.checks!.checks), false)
  const earned: CheckResult = { ...result, checks: [required, bonusEarned], checkedAt: '2026-10-08T00:01:00Z' }
  store.saveCheck('signal', earned)
  assert.equal(bonusPassed(store.snapshot(connection).missions.find((item) => item.id === 'signal')!.checks!.checks), true)
  assert.equal(store.snapshot(connection).xp, 180, 'the later bonus run earns ★3 and half the base XP on top of ★1')
  assert.ok(store.stars('signal')[3])
})
