import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtemp, rm, copyFile, readFile, writeFile } from 'node:fs/promises'
import { existsSync } from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { createApp } from '../server/app.js'
import { ProviderError, type TutorProvider } from '../server/provider.js'
import { root, type SavedCodeContext } from '../server/labs.js'
import { missionById } from '../shared/content.js'

class FakeProvider implements TutorProvider {
  model = 'test-only'; calls = 0; fail = false
  hasAccount() { return true }
  async complete(_instructions: string, input: string) {
    this.calls++
    if (this.fail) throw new ProviderError('Quota exhausted in deterministic test.', 'quota')
    const answer = JSON.parse(input).learnerAnswer as string
    return JSON.stringify({ communicativeGoal: 'met', clarity: 'clear', independence: 'independent', evidence: [{ quote: answer, observation: 'Test fixture evidence.' }], corrections: [], reply: 'Test feedback, not a live model assessment.', practice: 'Describe another action.' })
  }
}
async function fixture(t: test.TestContext) {
  const home = await mkdtemp(path.join(os.tmpdir(), 'rankforge-api-'))
  const provider = new FakeProvider(); const launches: string[] = []
  const setup = await createApp({ home, provider, launchEditor: async (workspace) => { launches.push(workspace) } })
  t.after(async () => { await setup.app.close(); await rm(home, { recursive: true, force: true }) })
  const post = (url: string, payload: object = {}) => setup.app.inject({ method: 'POST', url, headers: { 'x-rankforge-token': setup.browserToken }, payload })
  return { ...setup, home, provider, launches, post }
}

test('real local cycle: prepare, fail, edit, pass, advance and preserve prior workspace', async (t) => {
  const { post, labs, store, launches } = await fixture(t)
  assert.equal((await post('/api/missions/signal/start', { openEditor: true })).statusCode, 200)
  assert.equal(launches.length, 1)
  let checked = await post('/api/missions/signal/check')
  assert.equal(checked.json().missions[0].checks.passed, false)
  await copyFile(path.join(root, 'tests/solutions/signal.py'), path.join(labs.workspace('signal'), 'service.py'))
  checked = await post('/api/missions/signal/check')
  assert.equal(checked.json().missions[0].checks.passed, true)
  assert.equal(checked.json().xp, 180, 'The thorough solution earns ★1 (120) and ★3 (60) in one run')
  assert.deepEqual(Object.values(checked.json().missions[0].stars).map(Boolean), [true, false, true])
  await post('/api/missions/signal/check')
  assert.equal((await post('/api/missions/vault/start', { openEditor: false })).json().xp, 180)
  assert.equal(store.get('active'), 'vault')
  assert.ok(store.progress('signal').workspace)
})

test('quota preserves the answer while real labs continue; resume is idempotent and never re-awards', async (t) => {
  const { post, provider, store, labs, waitForJobs } = await fixture(t)
  provider.fail = true
  const body = { id: 'request-quota', text: 'I inspected the response.', mode: 'debrief' }
  assert.equal((await post('/api/missions/signal/answer', body)).statusCode, 202)
  await waitForJobs()
  assert.equal(store.exchange(body.id)?.status, 'paused')
  assert.equal(store.exchange(body.id)?.text, body.text)
  assert.ok(store.get('pause'))
  assert.equal((await post('/api/missions/signal/start', { openEditor: false })).statusCode, 200)
  assert.equal((await post('/api/missions/signal/hint')).statusCode, 200)
  await copyFile(path.join(root, 'tests/solutions/signal.py'), path.join(labs.workspace('signal'), 'service.py'))
  assert.equal((await post('/api/missions/signal/check')).json().xp, 180)
  assert.equal(store.exchange(body.id)?.status, 'paused')
  assert.equal(provider.calls, 1)
  assert.equal((await post('/api/missions/vault/start', { openEditor: false })).statusCode, 200)
  assert.equal((await post('/api/missions/signal/answer', { ...body, id: 'another-paused-message' })).statusCode, 409)
  provider.fail = false
  await post('/api/answers/resume', { id: body.id }); await waitForJobs()
  assert.equal(store.exchange(body.id)?.status, 'completed')
  assert.equal(store.get('pause'), '')
  await post('/api/answers/resume', { id: body.id }); await waitForJobs()
  assert.equal(provider.calls, 2)
  assert.equal((await post('/api/missions/signal/check')).json().xp, 240, 'The met debrief added ★2 (60) once; the resumed duplicate and the repeated check add nothing')
  assert.ok(store.stars('signal')[2])
  assert.equal(store.language().evidenceCount, 1)
})

test('origin, host, CSRF, editor credential and schema boundaries reject hostile requests', async (t) => {
  const { app, post, browserToken } = await fixture(t)
  assert.equal((await app.inject({ url: '/api/bootstrap', headers: { host: 'attacker.example' } })).statusCode, 403)
  assert.equal((await app.inject({ url: '/api/bootstrap', headers: { origin: 'https://attacker.example' } })).statusCode, 403)
  assert.equal((await app.inject({ url: '/api/bootstrap', headers: { 'sec-fetch-site': 'cross-site' } })).statusCode, 403)
  assert.equal((await app.inject({ method: 'POST', url: '/api/missions/signal/start', payload: {} })).statusCode, 403)
  assert.equal((await app.inject({ url: '/api/editor/poll' })).statusCode, 401)
  assert.equal((await post('/api/missions/../../etc/start')).statusCode >= 400, true)
  assert.equal((await post('/api/missions/signal/start', { openEditor: false, command: 'arbitrary' })).statusCode, 400)
  assert.equal((await post('/api/missions/signal/answer', { id: 'valid-id', text: '', mode: 'debrief' })).statusCode, 400)
  assert.equal((await post('/api/missions/signal/answer', { id: 'valid-id', text: '   ', mode: 'debrief' })).statusCode, 400)
  const data = (await app.inject({ url: '/api/bootstrap' })).json()
  assert.equal(data.token, browserToken)
  assert.equal(JSON.stringify(data).includes('refresh_token'), false)
})

test('dedicated editor polls only owned commands and acknowledges after reaching a workspace', async (t) => {
  const { post, app, bridgeToken, store } = await fixture(t)
  await post('/api/missions/signal/start', { openEditor: true })
  const command = (await app.inject({ url: '/api/editor/poll', headers: { 'x-rankforge-bridge': bridgeToken } })).json().command
  assert.equal(command.workspace, store.progress('signal').workspace)
  await app.inject({ method: 'POST', url: '/api/editor/ack', headers: { 'x-rankforge-bridge': bridgeToken }, payload: { id: command.id } })
  assert.equal(store.editorCommand(), undefined)
})

test('coaching distinguishes saved code from a pasted editor snippet and old checks from live terminal output', async (t) => {
  const { post, provider, waitForJobs, labs } = await fixture(t)
  await post('/api/missions/signal/start', { openEditor: false })
  let captured: { learnerAnswer: string; question: string; studentCode: SavedCodeContext; labEvidenceContext: { isLiveTerminal: boolean } } | undefined
  provider.complete = async (_instructions, input) => { captured = JSON.parse(input); return 'The pasted snippet and saved file differ. Check the editor path and save the buffer.' }
  const snippet = 'My editor has print("Requested path:", self.path, flush=True), but I do not see the output.'
  await post('/api/missions/signal/answer', { id: 'saved-code-context', mode: 'coach', text: snippet })
  await waitForJobs()
  assert.ok(captured)
  assert.equal(captured.learnerAnswer, snippet)
  assert.equal(captured.question, snippet)
  assert.equal(captured.studentCode.source, 'saved-files-on-disk')
  assert.equal(captured.studentCode.workspace, labs.workspace('signal'))
  assert.equal(captured.studentCode.files['service.py'].content.includes('print("Requested path:"'), false)
  assert.ok(Number.isFinite(Date.parse(captured.studentCode.files['service.py'].lastModifiedAt)))
  assert.equal(captured.studentCode.files['service.py'].truncated, false)
  assert.deepEqual(captured.studentCode.visibility, { unsavedEditorBuffers: false, runningProcessState: false, terminalOutput: false })
  assert.equal(captured.labEvidenceContext.isLiveTerminal, false)
})

test('reset moves the workspace into a backup, restores the starter and the current texts, and keeps progress', async (t) => {
  const { post, labs, store, home } = await fixture(t)
  assert.equal((await post('/api/missions/signal/reset')).statusCode, 409, 'No workspace yet: nothing to reset')
  await post('/api/missions/signal/start', { openEditor: false })
  await post('/api/missions/signal/hint')
  const workspace = labs.workspace('signal')
  const starter = await readFile(path.join(root, 'labs', 'signal', 'service.py'), 'utf8')
  await writeFile(path.join(workspace, 'service.py'), `${starter}\n# learner edit\n`)
  await writeFile(path.join(workspace, 'notes.txt'), 'my own notes')
  await writeFile(path.join(workspace, 'MISSION.md'), '# frozen old wording\n')
  const before = store.progress('signal')
  const response = await post('/api/missions/signal/reset')
  assert.equal(response.statusCode, 200, response.body)
  const { backup, workspace: returned, note } = response.json()
  assert.equal(returned, workspace)
  assert.equal(note, null)
  assert.equal(path.dirname(backup), path.join(home, 'workspaces', '.backups'))
  assert.match(path.basename(backup), /^signal-\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}\.\d{3}Z$/)
  assert.equal(await readFile(path.join(backup, 'notes.txt'), 'utf8'), 'my own notes')
  assert.equal(await readFile(path.join(backup, 'service.py'), 'utf8'), `${starter}\n# learner edit\n`)
  assert.equal(await readFile(path.join(backup, 'MISSION.md'), 'utf8'), '# frozen old wording\n')
  assert.equal(existsSync(path.join(workspace, 'notes.txt')), false)
  assert.equal(await readFile(path.join(workspace, 'service.py'), 'utf8'), starter)
  const mission = await readFile(path.join(workspace, 'MISSION.md'), 'utf8')
  assert.ok(mission.includes(missionById('signal').lesson), 'MISSION.md is regenerated from the current lesson text')
  assert.equal(existsSync(path.join(workspace, 'LEARN.md')), true)
  assert.deepEqual(JSON.parse(await readFile(path.join(workspace, '.rankforge-mission.json'), 'utf8')), { mission: 'signal', version: 1 })
  assert.deepEqual(JSON.parse(await readFile(path.join(workspace, '.rankforge-connection.json'), 'utf8')), { bridgeFile: path.join(home, 'bridge.json') })
  const after = store.progress('signal')
  assert.equal(after.workspace, before.workspace)
  assert.equal(after.hints, 1)
  const journal = store.snapshot({ signedIn: false, model: 'x', paused: false, reason: null, editorConnected: false }).journal
  assert.ok(journal.some((entry) => entry.kind === 'reset' && entry.missionId === 'signal' && entry.text.includes(backup)))
  assert.equal(labs.workspace('signal'), workspace, 'The compose project name derives from the path, which is unchanged')
})

test('reset keeps stars and XP; a repeat pass earns nothing new, a repeat that clears the bonus earns ★3 once', async (t) => {
  const { post, labs, store } = await fixture(t)
  await post('/api/missions/signal/start', { openEditor: false })
  const thorough = await readFile(path.join(root, 'tests/solutions/signal.py'), 'utf8')
  const minimal = thorough.replace('        self.send_header("Content-Length", str(len(body)))\n', '')
  assert.notEqual(minimal, thorough)
  await writeFile(path.join(labs.workspace('signal'), 'service.py'), minimal)
  let checked = (await post('/api/missions/signal/check')).json()
  assert.equal(checked.xp, 120, 'A minimal pass earns ★1 only')
  assert.deepEqual(Object.values(checked.missions[0].stars).map(Boolean), [true, false, false])
  const storedCheck = store.progress('signal').checks
  const starsBefore = store.stars('signal')
  assert.equal((await post('/api/missions/signal/reset')).statusCode, 200)
  assert.deepEqual(store.stars('signal'), starsBefore)
  assert.equal(store.progress('signal').checks, storedCheck, 'The last check result is historical and stays until a fresh Verify')
  assert.ok(store.progress('signal').completed)
  let state = (await post('/api/missions/signal/check')).json()
  assert.equal(state.xp, 120, 'The restored starter fails; nothing is revoked')
  assert.equal(state.missions[0].status, 'completed')
  await writeFile(path.join(labs.workspace('signal'), 'service.py'), minimal)
  state = (await post('/api/missions/signal/check')).json()
  assert.equal(state.xp, 120, 'A repeat pass after reset grants no new ★1 XP')
  assert.equal((await post('/api/missions/signal/reset')).statusCode, 200)
  await writeFile(path.join(labs.workspace('signal'), 'service.py'), thorough)
  state = (await post('/api/missions/signal/check')).json()
  assert.equal(state.xp, 180, 'The repeat that also clears the bonus earns ★3')
  assert.deepEqual(Object.values(state.missions[0].stars).map(Boolean), [true, false, true])
  state = (await post('/api/missions/signal/check')).json()
  assert.equal(state.xp, 180, '★3 is granted once')
  assert.equal(store.starAwards().filter((award) => award.missionId === 'signal').length, 2)
})
