import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtempSync, rmSync } from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { Store } from '../server/store.js'
import type { CheckResult, LanguageGrade } from '../shared/types.js'

const passed: CheckResult = { passed: true, supported: true, checkedAt: '2026-10-03T00:00:00Z', checks: [{ name: 'Real outcome', passed: true, detail: 'verified' }], output: '' }
const grade: LanguageGrade = { communicativeGoal: 'met', clarity: 'clear', independence: 'independent', evidence: [{ quote: 'I fixed the relay.', observation: 'States an action.' }], corrections: [], reply: 'Clear explanation.', practice: 'Explain a different cause using because.' }

function setup(t: test.TestContext, now?: () => string) {
  const home = mkdtempSync(path.join(os.tmpdir(), 'rankforge-store-'))
  const store = new Store(home, now)
  t.after(() => { store.close(); rmSync(home, { recursive: true, force: true }) })
  return store
}

test('prerequisites, hint support and one-time rewards survive repeated checks', (t) => {
  const store = setup(t)
  assert.throws(() => store.select('vault', '/tmp/vault'), /prerequisite/)
  store.select('signal', '/tmp/signal')
  store.hint('signal')
  store.saveCheck('signal', passed)
  store.saveCheck('signal', passed)
  store.select('vault', '/tmp/vault')
  const snapshot = store.snapshot({ signedIn: false, model: 'test', paused: false, reason: null, editorConnected: false })
  assert.equal(snapshot.xp, 120)
  assert.equal(snapshot.missions[0]!.independent, false)
  assert.equal(snapshot.missions[1]!.status, 'active')
  assert.equal(snapshot.journal.filter((item) => item.kind === 'victory').length, 1)
})

test('failed/unavailable checks never award; an old success is not revoked', (t) => {
  const store = setup(t)
  store.saveCheck('signal', { ...passed, passed: false })
  assert.equal(store.progress('signal').completed, null)
  store.saveCheck('signal', { ...passed, supported: false })
  assert.equal(store.progress('signal').completed, null)
  store.saveCheck('signal', passed)
  store.saveCheck('signal', { ...passed, passed: false })
  assert.ok(store.progress('signal').completed)
})

test('restart preserves submitted answers and pauses interrupted evaluations', () => {
  const home = mkdtempSync(path.join(os.tmpdir(), 'rankforge-restart-'))
  let store = new Store(home)
  try {
    store.submit('request-01', 'signal', 'I fixed the relay.', 'debrief')
    store.processing('request-01')
    store.close()
    store = new Store(home)
    assert.equal(store.exchange('request-01')!.text, 'I fixed the relay.')
    assert.equal(store.exchange('request-01')!.status, 'paused')
    assert.ok(store.get('pause'))
    store.select('signal', '/tmp/anything')
    assert.equal(store.get('active'), 'signal')
    assert.throws(() => store.submit('new-paused-answer', 'signal', 'Another answer', 'coach'), /paused/)
    store.finish('request-01', grade.reply, structuredClone(grade))
    assert.equal(store.get('pause'), '')
  } finally { store.close(); rmSync(home, { recursive: true, force: true }) }
})

test('request IDs are idempotent but cannot be reused with a different answer', (t) => {
  const store = setup(t)
  const one = store.submit('request-02', 'signal', 'I fixed the relay.', 'debrief')
  assert.deepEqual(store.submit('request-02', 'signal', 'I fixed the relay.', 'debrief'), one)
  assert.throws(() => store.submit('request-02', 'signal', 'Different answer', 'debrief'), /different answer/)
})

test('language advancement requires cross-mission evidence on separate days; repeated answers and help do not inflate it', (t) => {
  let now = '2026-10-03T08:00:00Z'
  const store = setup(t, () => now)
  for (const id of ['signal', 'vault', 'echo', 'ledger']) store.saveCheck(id, passed)
  const submit = (id: string, mission: string, text = 'I fixed the relay.') => { store.submit(id, mission, text, 'debrief'); store.finish(id, grade.reply, structuredClone(grade)) }
  submit('request-10', 'signal'); submit('request-11', 'signal'); submit('request-12', 'vault'); submit('request-13', 'echo')
  assert.equal(store.language().evidenceCount, 3)
  assert.equal(store.language().band, 'guided')
  now = '2026-10-04T10:00:00Z'
  store.submit('request-help', 'ledger', 'Help me phrase this explanation.', 'coach')
  store.finish('request-help', 'Try describing the cause.', null)
  submit('request-14', 'ledger')
  assert.equal(store.language().band, 'guided')
  assert.equal(store.exchange('request-14')!.grade!.independence, 'supported')
  submit('request-15', 'echo', 'The retry was safe because its identity persisted.')
  assert.equal(store.language().band, 'connected')
  assert.ok(store.language().due.length)
})

test('coaching is explicitly supported practice and does not fabricate language evidence', (t) => {
  const store = setup(t)
  store.submit('request-30', 'signal', 'Please help me.', 'coach')
  store.finish('request-30', 'What do you observe?', null)
  assert.equal(store.progress('signal').hints, 1)
  assert.equal(store.language().evidenceCount, 0)
})

test('technical hints do not lower English evidence; coaching does not permanently block later independent work', (t) => {
  let now = '2026-10-03T08:00:00Z'
  const store = setup(t, () => now)
  store.hint('signal')
  store.submit('request-static-hint', 'signal', 'I fixed the relay.', 'debrief')
  store.finish('request-static-hint', grade.reply, structuredClone(grade))
  assert.equal(store.exchange('request-static-hint')!.grade!.independence, 'independent')
  const firstQuestion = store.exchange('request-static-hint')!.question
  store.submit('request-tutor-help', 'signal', 'How can I explain this?', 'coach')
  store.finish('request-tutor-help', 'Describe a cause.', null)
  now = '2026-10-05T08:00:00Z'
  store.submit('request-later', 'signal', 'A running process can still return an incorrect status.', 'debrief')
  store.finish('request-later', grade.reply, structuredClone(grade))
  assert.equal(store.exchange('request-later')!.grade!.independence, 'independent')
  assert.notEqual(store.exchange('request-later')!.question, firstQuestion)
  assert.equal(store.language().evidenceCount, 2)
  now = '2026-10-06T08:00:00Z'
  store.submit('request-same-again', 'signal', 'I fixed the relay.', 'debrief')
  store.finish('request-same-again', grade.reply, structuredClone(grade))
  assert.equal(store.language().evidenceCount, 2)
})
