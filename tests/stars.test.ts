import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtempSync, rmSync } from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { Store } from '../server/store.js'
import { currentContractVersion } from '../shared/contracts.js'
import { skillLevel, skillLevels, skillSnapshots, starXp } from '../shared/progression.js'
import type { CheckResult, LanguageGrade } from '../shared/types.js'

// Store-boundary fixtures only; no lab or tutor is evaluated here.
const required = { name: 'Required contract check', passed: true, detail: 'fixture' }
const bonus = { name: 'bonus: hidden edge case', passed: true, detail: 'fixture', optional: true }
const plain: CheckResult = { passed: true, supported: true, contractVersion: currentContractVersion, checkedAt: '2026-10-08T00:00:00Z', checks: [required], output: '' }
const thorough: CheckResult = { ...plain, checks: [required, bonus] }
const grade = (communicativeGoal: LanguageGrade['communicativeGoal']): LanguageGrade => ({ communicativeGoal, clarity: 'clear', independence: 'independent', evidence: [], corrections: [], reply: 'fixture', practice: 'fixture' })
const connection = { signedIn: false, model: 'unused', paused: false, reason: null, editorConnected: false }
const xp = (store: Store) => store.snapshot(connection).xp
const debrief = (store: Store, id: string, mission: string, verdict: LanguageGrade['communicativeGoal']) => { store.submit(id, mission, `Answer ${id}`, 'debrief'); store.finish(id, 'reply', grade(verdict)) }

function setup(t: test.TestContext) {
  const home = mkdtempSync(path.join(os.tmpdir(), 'rankforge-stars-'))
  const store = new Store(home)
  t.after(() => { store.close(); rmSync(home, { recursive: true, force: true }) })
  return store
}

test('★1 and ★3 come from one passing run with the bonus; replays change neither the ledger nor the XP', (t) => {
  const store = setup(t)
  store.saveCheck('signal', thorough)
  const first = store.stars('signal')
  assert.ok(first[1] && first[3] && !first[2])
  assert.deepEqual(store.starAwards(), [{ missionId: 'signal', star: 1, xp: 120 }, { missionId: 'signal', star: 3, xp: 60 }])
  assert.equal(xp(store), 180)
  for (let i = 0; i < 5; i++) store.saveCheck('signal', { ...thorough, checkedAt: new Date(1800000000000 + i).toISOString() })
  assert.deepEqual(store.stars('signal'), first)
  assert.deepEqual(store.starAwards(), [{ missionId: 'signal', star: 1, xp: 120 }, { missionId: 'signal', star: 3, xp: 60 }])
  assert.equal(xp(store), 180)
})

test('a passing bonus never grants ★3 while a required check fails or the check is unavailable', (t) => {
  const store = setup(t)
  store.saveCheck('signal', { ...thorough, passed: false, checks: [{ ...required, passed: false }, bonus] })
  store.saveCheck('signal', { ...thorough, supported: false })
  assert.deepEqual(store.stars('signal'), { 1: null, 2: null, 3: null })
  assert.equal(xp(store), 0)
  store.saveCheck('signal', { ...plain, checks: [required, { ...bonus, passed: false }] })
  assert.deepEqual(Object.values(store.stars('signal')).map(Boolean), [true, false, false])
  assert.equal(xp(store), 120)
})

test('★2 is granted on met and partial, never on not_met, and a duplicate debrief pays nothing extra', (t) => {
  const store = setup(t)
  debrief(store, 'd-not-met', 'signal', 'not_met')
  assert.equal(store.stars('signal')[2], null)
  assert.equal(xp(store), 0)
  debrief(store, 'd-partial', 'signal', 'partial')
  assert.ok(store.stars('signal')[2])
  assert.equal(xp(store), 60, 'Half of Signal\'s 120 XP, independent of ★1')
  debrief(store, 'd-met', 'signal', 'met')
  store.finish('d-met', 'reply again', grade('met'))
  assert.equal(xp(store), 60)
  assert.equal(store.starAwards().length, 1)
  store.saveCheck('signal', plain)
  debrief(store, 'd-vault', 'vault', 'met')
  assert.equal(xp(store), 60 + 120 + 80, 'Vault ★2 pays half of its 160 XP before Vault is completed')
  store.submit('c-1', 'signal', 'Help', 'coach'); store.finish('c-1', 'reply', null)
  assert.equal(xp(store), 260, 'Coaching grants no star')
})

test('stars never decrease after a failing check, a weaker debrief or a contract bump', (t) => {
  const store = setup(t)
  store.saveCheck('signal', thorough)
  debrief(store, 'd-1', 'signal', 'met')
  const earned = store.stars('signal')
  assert.deepEqual(Object.values(earned).map(Boolean), [true, true, true])
  store.saveCheck('signal', { ...thorough, passed: false, checks: [{ ...required, passed: false }, { ...bonus, passed: false }] })
  debrief(store, 'd-2', 'signal', 'not_met')
  store.saveCheck('signal', { ...thorough, contractVersion: 'legacy-contract' })
  assert.deepEqual(store.stars('signal'), earned)
  assert.equal(xp(store), 240)
})

test('startup backfill maps a legacy award to ★1, a graded debrief to ★2 and a stored bonus run to ★3, idempotently', () => {
  const home = mkdtempSync(path.join(os.tmpdir(), 'rankforge-stars-legacy-'))
  let store = new Store(home)
  try {
    // A pre-star save: completion plus the single legacy awards row, a graded debrief, and a stored thorough result.
    store.db.prepare("UPDATE progress SET completed='2026-10-04T00:23:21.356Z', checks=? WHERE id='signal'").run(JSON.stringify({ ...plain, contractVersion: undefined }))
    store.db.prepare('INSERT INTO awards VALUES (?,?)').run('signal', 120)
    store.db.prepare("UPDATE progress SET completed='2026-10-05T00:00:00Z', checks=? WHERE id='vault'").run(JSON.stringify(thorough))
    store.db.prepare("INSERT INTO exchanges(id,mission_id,mode,text,status,grade,created) VALUES ('old-debrief','signal','debrief','I fixed the relay.','completed',?,'2026-10-04T01:00:00Z')").run(JSON.stringify(grade('partial')))
    store.db.prepare("INSERT INTO exchanges(id,mission_id,mode,text,status,grade,created) VALUES ('old-coach','vault','coach','Help','completed',NULL,'2026-10-04T01:00:00Z')").run()
    store.db.exec('DROP TABLE mission_stars; DROP TABLE star_awards')
    store.close()
    store = new Store(home)
    assert.deepEqual(store.stars('signal'), { 1: '2026-10-04T00:23:21.356Z', 2: '2026-10-04T01:00:00Z', 3: null })
    assert.deepEqual(store.stars('vault'), { 1: '2026-10-05T00:00:00Z', 2: null, 3: thorough.checkedAt })
    assert.deepEqual(store.starAwards(), [
      { missionId: 'signal', star: 1, xp: 120 }, { missionId: 'signal', star: 2, xp: 60 },
      { missionId: 'vault', star: 1, xp: 160 }, { missionId: 'vault', star: 3, xp: 80 },
    ])
    assert.equal(xp(store), 420)
    const ledger = store.db.prepare('SELECT * FROM mission_stars ORDER BY mission_id,star').all()
    store.close(); store = new Store(home); store.close(); store = new Store(home)
    assert.deepEqual(store.db.prepare('SELECT * FROM mission_stars ORDER BY mission_id,star').all(), ledger)
    assert.equal(xp(store), 420)
    assert.equal(store.db.prepare('SELECT COUNT(*) AS n FROM awards').get()!.n, 1, 'The legacy table is kept, not rewritten')
  } finally { store.close(); rmSync(home, { recursive: true, force: true }) }
})

test('skill XP sums the star awards of every mission listing the skill; levels follow the thresholds', (t) => {
  assert.equal(starXp(120, 1), 120); assert.equal(starXp(120, 2), 60); assert.equal(starXp(220, 3), 110)
  assert.deepEqual(skillLevels.map((item) => item.threshold), [0, 150, 400, 800, 1400])
  assert.deepEqual(skillLevel(0), { level: 1, levelName: 'Novice', nextThreshold: 150 })
  assert.deepEqual(skillLevel(150), { level: 2, levelName: 'Apprentice', nextThreshold: 400 })
  assert.deepEqual(skillLevel(1400), { level: 5, levelName: 'Expert', nextThreshold: null })
  const catalog = [{ id: 'a', skills: ['Transactions', 'Other'] }, { id: 'b', skills: ['Transactions'] }, { id: 'c', skills: ['Unused'] }]
  const skills = skillSnapshots(catalog, [{ missionId: 'a', star: 1, xp: 100 }, { missionId: 'a', star: 2, xp: 50 }, { missionId: 'b', star: 1, xp: 300 }])
  assert.deepEqual(skills.map((skill) => [skill.name, skill.xp, skill.levelName, skill.missions]), [['Transactions', 450, 'Practitioner', ['a', 'b']], ['Other', 150, 'Apprentice', ['a']], ['Unused', 0, 'Novice', []]])

  const store = setup(t)
  store.saveCheck('vault', thorough)
  store.saveCheck('echo', plain)
  const live = store.snapshot(connection).skills
  const transactions = live.find((skill) => skill.name === 'Transactions')!
  assert.equal(transactions.xp, 160 + 80 + 220, 'Vault ★1+★3 and Echo ★1 both list Transactions')
  assert.equal(transactions.levelName, 'Practitioner')
  assert.deepEqual(transactions.missions, ['vault', 'echo'])
  assert.equal(live.find((skill) => skill.name === 'Idempotency')!.xp, 220)
  assert.equal(live[0]!.name, 'Transactions', 'Sorted by XP descending')
  assert.equal(store.snapshot(connection).xp, 460)
})
