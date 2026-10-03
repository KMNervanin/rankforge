import test from 'node:test'
import assert from 'node:assert/strict'
import { ChatGPTProvider, ProviderError, parseGrade, readResponseStream } from '../server/provider.js'
import type { Credential, Credentials } from '../server/credentials.js'
import { createHash } from 'node:crypto'

class MemoryCredentials implements Credentials {
  writes = 0
  constructor(public value: Credential | null) {}
  has() { return !!this.value }
  async read() { return this.value }
  async write(value: Credential) { this.value = value; this.writes++ }
  async clear() { this.value = null }
}
const current = () => ({ access: 'test-access', refresh: 'test-refresh', expires: Date.now() + 100000, accountId: 'test-account' })
const stream = (events: unknown[]) => new Response(events.map((event) => `data: ${JSON.stringify(event)}\n\n`).join(''), { headers: { 'Content-Type': 'text/event-stream' } })
const success = () => stream([{ type: 'response.output_text.delta', delta: 'A clear answer.' }, { type: 'response.completed' }])

test('actual request adapter uses the subscription endpoint and access token, without API key fallback', async () => {
  let calls = 0
  const provider = new ChatGPTProvider(new MemoryCredentials(current()), 'gpt-6-astra', async (url, init) => {
    calls++
    assert.equal(url, 'https://chatgpt.com/backend-api/codex/responses')
    const headers = new Headers(init!.headers)
    assert.equal(headers.get('authorization'), 'Bearer test-access')
    assert.equal(headers.get('ChatGPT-Account-Id'), 'test-account')
    assert.equal(headers.get('originator'), 'rankforge')
    const body = JSON.parse(String(init!.body))
    assert.equal(body.store, false); assert.equal(body.stream, true)
    assert.equal(body.instructions, 'rubric'); assert.equal(body.input[0].content[0].text, 'answer')
    assert.equal('api_key' in body, false)
    return success()
  })
  assert.equal(await provider.complete('rubric', 'answer'), 'A clear answer.')
  assert.equal(calls, 1)
})

test('expired credentials refresh once even for concurrent consumers', async () => {
  const credentials = new MemoryCredentials({ ...current(), expires: 1 })
  let refreshes = 0
  const provider = new ChatGPTProvider(credentials, 'gpt-6-astra', async (url) => {
    if (String(url).endsWith('/oauth/token')) { refreshes++; await new Promise((resolve) => setTimeout(resolve, 20)); return Response.json({ access_token: 'new-test-access', refresh_token: 'new-test-refresh', expires_in: 3600 }) }
    return success()
  })
  await Promise.all([provider.complete('a', 'b'), provider.complete('a', 'b')])
  assert.equal(refreshes, 1); assert.equal(credentials.writes, 1)
})

for (const [status, kind] of [[429, 'quota'], [402, 'quota'], [401, 'auth'], [403, 'auth'], [503, 'unavailable']] as const) {
  test(`HTTP ${status} is classified without attempting another billing route`, async () => {
    let calls = 0
    const provider = new ChatGPTProvider(new MemoryCredentials(current()), 'test', async () => { calls++; return new Response('provider error', { status }) })
    await assert.rejects(provider.complete('a', 'b'), (error) => error instanceof ProviderError && error.kind === kind)
    assert.equal(calls, 1)
  })
}

test('disconnected account does not send a model request', async () => {
  const provider = new ChatGPTProvider(new MemoryCredentials(null), 'test', async () => { throw new Error('must not call') })
  await assert.rejects(provider.complete('a', 'b'), (error) => error instanceof ProviderError && error.kind === 'auth')
})

test('SSE decoder handles split UTF-8 chunks and requires a complete response', async () => {
  const bytes = new TextEncoder().encode('data: {"type":"response.output_text.delta","delta":"café"}\r\n\r\ndata: {"type":"response.completed"}')
  const body = new ReadableStream<Uint8Array>({ start(controller) { for (const byte of bytes) controller.enqueue(new Uint8Array([byte])); controller.close() } })
  assert.equal(await readResponseStream(body), 'café')
  await assert.rejects(readResponseStream(stream([{ type: 'response.output_text.delta', delta: 'partial' }]).body!), /before completion/)
  await assert.rejects(readResponseStream(stream([{ type: 'response.failed', response: { error: { code: 'usage_limit_reached' } } }]).body!), (error) => error instanceof ProviderError && error.kind === 'quota')
})

test('assessments need actual learner quotations and cannot silently fabricate evidence', () => {
  const grade = { communicativeGoal: 'met', clarity: 'clear', independence: 'independent', evidence: [{ quote: 'I fixed', observation: 'States an action.' }], corrections: [], reply: 'Well explained.', practice: 'Describe another cause.' }
  assert.equal(parseGrade(JSON.stringify(grade), 'I fixed the relay.').communicativeGoal, 'met')
  assert.throws(() => parseGrade(JSON.stringify(grade), 'Something else.'), /evidence/)
  assert.throws(() => parseGrade(JSON.stringify({ ...grade, corrections: [{ quote: 'invented', suggestion: 'x', explanation: 'x' }] }), 'I fixed the relay.'), /evidence/)
  assert.throws(() => parseGrade('This is an answer.', 'I fixed the relay.'), /unreadable/)
})

test('real loopback OAuth callback validates state, exchanges PKCE, stores only through credential adapter and closes', async () => {
  const credentials = new MemoryCredentials(null)
  let exchanges = 0
  let challenge = ''
  const provider = new ChatGPTProvider(credentials, 'test', async (url, init) => {
    exchanges++
    assert.equal(String(url), 'https://auth.openai.com/oauth/token')
    const body = new URLSearchParams(String(init!.body))
    assert.equal(createHash('sha256').update(body.get('code_verifier')!).digest('base64url'), challenge)
    assert.equal(body.get('code'), 'test-authorization-code')
    return Response.json({ access_token: 'test-only-access', refresh_token: 'test-only-refresh', expires_in: 3600 })
  }, 0)
  try {
    const authorize = new URL(await provider.beginLogin())
    challenge = authorize.searchParams.get('code_challenge')!
    assert.equal(authorize.searchParams.get('originator'), 'rankforge')
    const callback = new URL(authorize.searchParams.get('redirect_uri')!)
    callback.hostname = '127.0.0.1'
    callback.searchParams.set('state', 'é'.repeat(64))
    callback.searchParams.set('code', 'test-authorization-code')
    assert.equal((await fetch(callback)).status, 400)
    assert.equal(exchanges, 0)
    callback.searchParams.set('state', authorize.searchParams.get('state')!)
    const completed = await fetch(callback)
    assert.equal(completed.status, 200)
    assert.match(await completed.text(), /Connection established/)
    assert.equal(credentials.writes, 1)
    assert.equal(exchanges, 1)
    assert.equal(provider.hasAccount(), true)
  } finally { provider.close() }
})
