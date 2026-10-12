import http from 'node:http'

// A test-only OpenAI-compatible endpoint for the Price mission's live check. Its model id says so; it is never a model.
export type StubBody = { model?: string; messages?: { content?: string }[]; max_tokens?: number; response_format?: { type?: string } }
// An added handler decides the answer text per request (the Record mission's live measurement); without one the stub answers 'OK' as before.
export async function startLlmStub(options: { reply?: (body: StubBody) => { content: string; finish_reason?: string } } = {}): Promise<{ baseUrl: string; model: string; requests: unknown[]; close: () => Promise<void> }> {
  const requests: unknown[] = []
  const server = http.createServer((request, response) => {
    let raw = ''
    request.on('data', (chunk) => { raw += chunk })
    request.on('end', () => {
      if (request.method !== 'POST' || !request.url?.endsWith('/chat/completions')) { response.writeHead(404, { 'content-type': 'application/json' }); response.end(JSON.stringify({ error: { message: 'unknown route' } })); return }
      let body: StubBody
      try { body = JSON.parse(raw) } catch { response.writeHead(400, { 'content-type': 'application/json' }); response.end(JSON.stringify({ error: { message: 'invalid json' } })); return }
      requests.push(body)
      const words = (body.messages ?? []).reduce((sum, message) => sum + String(message.content ?? '').split(/\s+/).filter(Boolean).length, 0)
      const prompt_tokens = words + 7
      const completion_tokens = Math.min(typeof body.max_tokens === 'number' ? body.max_tokens : 3, 3)
      response.writeHead(200, { 'content-type': 'application/json' })
      const answer = options.reply ? options.reply(body) : { content: 'OK' }
      response.end(JSON.stringify({ id: 'chatcmpl-stub', object: 'chat.completion', created: 0, model: body.model, choices: [{ index: 0, message: { role: 'assistant', content: answer.content }, finish_reason: answer.finish_reason ?? (completion_tokens < 3 ? 'length' : 'stop') }], usage: { prompt_tokens, completion_tokens, total_tokens: prompt_tokens + completion_tokens, prompt_tokens_details: { cached_tokens: 0 } } }))
    })
  })
  await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve))
  const address = server.address() as { port: number }
  return { baseUrl: `http://127.0.0.1:${address.port}/v1`, model: 'test-only', requests, close: () => new Promise((resolve) => server.close(() => resolve())) }
}

export const llmConfig = (baseUrl: string, model: string) => JSON.stringify({ base_url: baseUrl, model, context_window: 4096, input_price_per_million: 0.5, output_price_per_million: 1.5, cached_input_price_per_million: 0.25, max_tokens: 8 })
