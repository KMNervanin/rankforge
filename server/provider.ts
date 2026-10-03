import { randomBytes, createHash, timingSafeEqual } from 'node:crypto'
import { createServer, type Server } from 'node:http'
import type { Credentials, Credential } from './credentials.js'
import type { LanguageGrade } from '../shared/types.js'

// OAuth flow adapted from OpenCode. See THIRD_PARTY_NOTICES.md.
const clientId = 'app_EMoamEEZ73f0CkXaXp7hrann'
const issuer = 'https://auth.openai.com'
const endpoint = 'https://chatgpt.com/backend-api/codex/responses'
type Tokens = { access_token: string; refresh_token: string; expires_in?: number; id_token?: string }
export class ProviderError extends Error {
  constructor(message: string, public kind: 'quota' | 'auth' | 'network' | 'invalid' | 'unavailable') { super(message) }
}
export interface TutorProvider {
  hasAccount(): boolean
  model: string
  complete(instructions: string, input: string): Promise<string>
  beginLogin?(): Promise<string>
  logout?(): Promise<void>
  close?(): void
}

function credential(tokens: Tokens, previous?: Credential): Credential {
  if (!tokens.access_token || !(tokens.refresh_token || previous?.refresh)) throw new ProviderError('The account returned incomplete credentials.', 'auth')
  let accountId = previous?.accountId
  try {
    const token = tokens.id_token || tokens.access_token
    const claims = JSON.parse(Buffer.from(token.split('.')[1]!, 'base64url').toString())
    accountId = claims['https://api.openai.com/auth']?.chatgpt_account_id || claims.chatgpt_account_id || accountId
  } catch { /* Some token formats are opaque; keep the existing account binding. */ }
  return { access: tokens.access_token, refresh: tokens.refresh_token || previous!.refresh, expires: Date.now() + (tokens.expires_in ?? 3600) * 1000, ...(accountId ? { accountId } : {}) }
}

export class ChatGPTProvider implements TutorProvider {
  private callback: Server | undefined
  private loginTimer: ReturnType<typeof setTimeout> | undefined
  private refreshPromise: Promise<Credential> | undefined
  constructor(private credentials: Credentials, public model = 'gpt-6-astra', private transport: typeof fetch = fetch, private callbackPort = 1455) {}
  hasAccount() { return this.credentials.has() }
  close() { this.callback?.close(); this.callback = undefined; if (this.loginTimer) clearTimeout(this.loginTimer) }
  async logout() { this.close(); await this.credentials.clear() }
  async beginLogin(): Promise<string> {
    if (this.callback) throw new ProviderError('A sign-in is already waiting. Finish it or wait five minutes.', 'auth')
    const verifier = randomBytes(32).toString('base64url')
    const challenge = createHash('sha256').update(verifier).digest('base64url')
    const state = randomBytes(32).toString('hex')
    let redirect = ''
    let consumed = false
    const callback = createServer(async (req, res) => {
      const url = new URL(req.url ?? '/', 'http://localhost:1455')
      const received = url.searchParams.get('state') ?? ''
      if (url.pathname !== '/auth/callback' || !/^[a-f0-9]{64}$/.test(received) || !timingSafeEqual(Buffer.from(state), Buffer.from(received))) { res.writeHead(400); res.end('Invalid sign-in callback.'); return }
      if (consumed) { res.writeHead(409); res.end('This sign-in callback was already used.'); return }
      consumed = true
      const code = url.searchParams.get('code')
      if (!code) { res.writeHead(400); res.end('Sign-in was not completed. Return to Rankforge.'); this.close(); return }
      try {
        const response = await this.transport(`${issuer}/oauth/token`, { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body: new URLSearchParams({ grant_type: 'authorization_code', code, client_id: clientId, redirect_uri: redirect, code_verifier: verifier }), signal: AbortSignal.timeout(30000) })
        if (!response.ok) throw new ProviderError('Sign-in exchange failed.', 'auth')
        await this.credentials.write(credential(await response.json() as Tokens))
        res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'" })
        res.end('<!doctype html><html lang="en"><title>Rankforge connected</title><body style="background:#080e19;color:#d8e7ff;font:20px system-ui;padding:10vh"><h1>Connection established.</h1><p>Your account is stored in the system credential store. Return to Rankforge.</p></body></html>')
      } catch { res.writeHead(502); res.end('Unable to finish sign-in or store credentials. Check the system credential store, then try again in Rankforge.') }
      finally { this.close() }
    })
    this.callback = callback
    try {
      await new Promise<void>((resolve, reject) => { callback.once('error', reject); callback.listen(this.callbackPort, '127.0.0.1', resolve) })
    } catch { this.close(); throw new ProviderError('Sign-in callback port 1455 is busy. Complete any other login first.', 'unavailable') }
    const address = callback.address()
    redirect = `http://localhost:${typeof address === 'object' && address ? address.port : this.callbackPort}/auth/callback`
    this.loginTimer = setTimeout(() => this.close(), 5 * 60 * 1000)
    this.loginTimer.unref()
    const params = new URLSearchParams({ response_type: 'code', client_id: clientId, redirect_uri: redirect, scope: 'openid profile email offline_access', code_challenge: challenge, code_challenge_method: 'S256', id_token_add_organizations: 'true', codex_cli_simplified_flow: 'true', state, originator: 'rankforge' })
    return `${issuer}/oauth/authorize?${params}`
  }
  private async auth(): Promise<Credential> {
    let current: Credential | null
    try { current = await this.credentials.read() } catch { throw new ProviderError('Unlock your system credential store or reconnect ChatGPT. Your answer is saved.', 'auth') }
    if (!current) throw new ProviderError('Connect your ChatGPT subscription to continue. Your answer is saved.', 'auth')
    if (current.expires > Date.now() + 30000) return current
    if (!this.refreshPromise) this.refreshPromise = (async () => {
      const response = await this.transport(`${issuer}/oauth/token`, { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body: new URLSearchParams({ grant_type: 'refresh_token', refresh_token: current.refresh, client_id: clientId }), signal: AbortSignal.timeout(30000) })
      if (!response.ok) throw new ProviderError('Your sign-in expired. Reconnect to resume the saved answer.', 'auth')
      const updated = credential(await response.json() as Tokens, current)
      await this.credentials.write(updated)
      return updated
    })().finally(() => { this.refreshPromise = undefined })
    return this.refreshPromise
  }
  async complete(instructions: string, input: string): Promise<string> {
    try {
      const auth = await this.auth()
      const response = await this.transport(endpoint, {
        method: 'POST', signal: AbortSignal.timeout(120000),
        headers: { Authorization: `Bearer ${auth.access}`, 'Content-Type': 'application/json', Accept: 'text/event-stream', originator: 'rankforge', 'User-Agent': 'rankforge/0.1.0', ...(auth.accountId ? { 'ChatGPT-Account-Id': auth.accountId } : {}) },
        body: JSON.stringify({ model: this.model, instructions, input: [{ role: 'user', content: [{ type: 'input_text', text: input }] }], store: false, stream: true }),
      })
      if (response.status === 429 || response.status === 402) throw new ProviderError('Subscription capacity is unavailable. Training is paused; resume after your allowance recovers. No paid fallback is used.', 'quota')
      if (response.status === 401 || response.status === 403) throw new ProviderError('Your subscription session needs attention. Reconnect to resume; your answer is saved.', 'auth')
      if (!response.ok || !response.body) throw new ProviderError('The tutor service is temporarily unavailable. Your answer is saved.', 'unavailable')
      return await readResponseStream(response.body)
    } catch (error) {
      if (error instanceof ProviderError) throw error
      throw new ProviderError('The connection was interrupted. Your answer is saved and can be retried.', 'network')
    }
  }
}

export async function readResponseStream(body: ReadableStream<Uint8Array>): Promise<string> {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''; let output = ''; let completed = false
  const consume = (line: string) => {
    if (!line.startsWith('data:')) return
    const data = line.slice(5).trim()
    if (data === '[DONE]' || !data) return
    const event = JSON.parse(data)
    if (event.type === 'response.output_text.delta') output += event.delta ?? ''
    if (event.type === 'response.completed') {
      completed = true
      if (!output) output = (event.response?.output ?? []).flatMap((item: { content?: { text?: string }[] }) => item.content ?? []).map((part: { text?: string }) => part.text ?? '').join('')
    }
    if (event.type === 'error' || event.type === 'response.failed' || event.type === 'response.incomplete') {
      const code = event.error?.code ?? event.response?.error?.code ?? event.code ?? ''
      throw new ProviderError(code.includes('limit') || code.includes('quota') ? 'Subscription capacity is unavailable. Your answer is saved.' : 'The tutor could not complete the response. Your answer is saved.', code.includes('limit') || code.includes('quota') ? 'quota' : 'unavailable')
    }
    if (output.length > 50000) throw new ProviderError('The tutor response exceeded the lesson limit.', 'invalid')
  }
  try {
    for (;;) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      if (buffer.length > 1000000) throw new ProviderError('The tutor sent an oversized response.', 'invalid')
      let index: number
      while ((index = buffer.indexOf('\n')) !== -1) { consume(buffer.slice(0, index).trimEnd()); buffer = buffer.slice(index + 1) }
    }
    buffer += decoder.decode()
    if (buffer.trim()) consume(buffer.trimEnd())
    if (!completed || !output.trim()) throw new ProviderError('The response ended before completion. Retry the saved answer.', 'network')
    return output
  } finally { await reader.cancel().catch(() => {}); reader.releaseLock() }
}

export function parseGrade(text: string, answer: string): LanguageGrade {
  let value: LanguageGrade
  try { value = JSON.parse(text.replace(/^```(?:json)?\s*/, '').replace(/\s*```$/, '').trim()) } catch { throw new ProviderError('The tutor returned an unreadable assessment. No level change was applied.', 'invalid') }
  const valid = value && ['met', 'partial', 'not_met'].includes(value.communicativeGoal) && ['clear', 'mostly_clear', 'unclear'].includes(value.clarity) && ['independent', 'supported'].includes(value.independence)
    && typeof value.reply === 'string' && value.reply.length > 0 && value.reply.length <= 6000
    && typeof value.practice === 'string' && value.practice.length > 0 && value.practice.length <= 1000
    && Array.isArray(value.evidence) && value.evidence.length >= 1 && value.evidence.length <= 5
    && value.evidence.every((item) => typeof item.quote === 'string' && item.quote.length > 0 && answer.includes(item.quote) && typeof item.observation === 'string')
    && Array.isArray(value.corrections) && value.corrections.length <= 2
    && value.corrections.every((item) => typeof item.quote === 'string' && item.quote.length > 0 && answer.includes(item.quote) && typeof item.suggestion === 'string' && typeof item.explanation === 'string')
  if (!valid) throw new ProviderError('Assessment evidence did not match your answer. No level change was applied; you can retry.', 'invalid')
  return value
}
