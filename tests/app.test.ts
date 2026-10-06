import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtemp, rm, copyFile } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { createApp } from '../server/app.js'
import { ProviderError, type TutorProvider } from '../server/provider.js'
import { root, type SavedCodeContext } from '../server/labs.js'

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
  assert.equal((await post('/api/missions/vault/start', { openEditor: false })).statusCode, 409)
  assert.equal((await post('/api/missions/signal/start', { openEditor: true })).statusCode, 200)
  assert.equal(launches.length, 1)
  let checked = await post('/api/missions/signal/check')
  assert.equal(checked.json().missions[0].checks.passed, false)
  await copyFile(path.join(root, 'tests/solutions/signal.py'), path.join(labs.workspace('signal'), 'service.py'))
  checked = await post('/api/missions/signal/check')
  assert.equal(checked.json().missions[0].checks.passed, true)
  assert.equal(checked.json().xp, 120)
  await post('/api/missions/signal/check')
  assert.equal((await post('/api/missions/vault/start', { openEditor: false })).json().xp, 120)
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
  assert.equal((await post('/api/missions/signal/check')).json().xp, 120)
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
  assert.equal((await post('/api/missions/signal/check')).json().xp, 120)
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
