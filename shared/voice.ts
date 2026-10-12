import type { Mission } from './types.js'
import { mission as window, followUps as windowFollowUps } from './voice/window.js'
import { mission as prompts, followUps as promptsFollowUps } from './voice/prompts.js'
import { mission as backoff, followUps as backoffFollowUps } from './voice/backoff.js'
import { mission as record, followUps as recordFollowUps } from './voice/record.js'
import { mission as sampling, followUps as samplingFollowUps } from './voice/sampling.js'

// Chapter IX of the roadmap: the operator assistant. Authored for the owner's personal route first; the
// endpoint is whatever OpenAI-compatible server the learner configures in llm.json (a local model by default).
const authored: Mission[] = [
  window,
  prompts,
  backoff,
  record,
  sampling,
  {
    id: 'price', chapter: 'voice', order: 1, title: 'Every word has a price', subtitle: 'Meter the assistant’s first call', sector: 'Operator’s desk', icon: '◎',
    block: 'Calling the model', files: ['client.py', 'llm.json'],
    nudge: 'Rumour says the relay charges less for words it has already read once.',
    skills: ['LLM calls', 'Token accounting', 'Cost measurement'], prerequisites: ['signal'], xp: 220, duration: 'Self-paced', kind: 'build',
    briefs: {
      guided: 'The outpost is getting an assistant, but nobody can say what one question costs. Make the client measure every call: tokens, latency, finish reason and price. Hints are available; guided work earns the same rewards.',
      connected: 'Turn a quick script into a metered client: refuse what cannot fit, send what you log, take the counts from the response and price them from the table. Prove it against a recording adapter and one real call.',
      independent: 'Build a metered LLM client whose every record traces to the parameters actually sent and the usage actually returned, with a byte-bound window guard and an append-only journal. Demonstrate it on two price tables and your own endpoint.',
    },
    objectives: [
      'Keep client.py importable with the class WindowError and the function ask(prompt, *, base_url, model, max_tokens, manifest, log_path, temperature=0.0). The manifest has the shape of models.json: overhead_tokens and models → {context_window, input_price_per_million, output_price_per_million, optional cached_input_price_per_million}. Read every number from the argument, not from a constant.',
      'Before sending, bound the prompt by len(prompt.encode("utf-8")) + overhead_tokens. If that bound plus max_tokens exceeds the model’s context_window, raise WindowError, send no request and write no log line. A prompt exactly at the bound is sent.',
      'POST {base_url}/chat/completions with JSON {model, messages: [{role: "user", content: prompt}], max_tokens, temperature}; do not send stream: true. The returned record carries the same model, max_tokens and temperature.',
      'Take the meter from the response: input_tokens = usage.prompt_tokens, output_tokens = usage.completion_tokens, finish_reason = choices[0].finish_reason verbatim, cached_tokens = usage.prompt_tokens_details.cached_tokens or 0, content = choices[0].message.content. Never estimate tokens from characters.',
      'cost = (input_tokens × input price + output_tokens × output price) / 1,000,000 for the model that was called, tolerance 1e-9. latency_ms is a non-negative integer measured around the request: not below the server’s time, not above the caller’s wait.',
      'Append exactly one line, json.dumps(record) plus a newline, to log_path per successful call; earlier lines stay unchanged. The record has at least the keys model, max_tokens, temperature, input_tokens, output_tokens, cached_tokens, latency_ms, finish_reason, cost, content; token counts and latency are integers.',
      'Verify runs a recording adapter (a labeled test tool with deterministic counts) and one live call to the endpoint in llm.json, reconciled with its own direct request. No model id in llm.json or no answer within 15 seconds is an environment-blocked result, not a failure. Keys stay in the LLM_API_KEY environment variable, never in a workspace file or the log.',
    ],
    languageGoal: 'Report a measurement with its unit and say what it does not prove.', prompt: 'Explain to the operator what one call to the assistant costs and how long it takes. Name one number in your log that is a measurement and one that is only an upper bound, and say why the difference matters.',
    hints: ['Open a response in the terminal and find usage and finish_reason. Which of the starter’s record fields come from there, and which are made up?', 'A token is never smaller than a byte of UTF-8. What does that give you before the request leaves, and what does it not give you?', 'Measure with a clock around the whole request, not around the JSON parsing. Then compare your latency with the time the demo took.'],
    sources: [
      { title: 'OpenAI chat completions reference: request body, finish_reason and usage', url: 'https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create' },
      { title: 'Ollama OpenAI compatibility', url: 'https://github.com/ollama/ollama/blob/main/docs/api/openai-compatibility.mdx' },
      { title: 'llama.cpp server README: the same contract on a local model', url: 'https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md' },
      { title: 'Python urllib.request', url: 'https://docs.python.org/3.10/library/urllib.request.html' },
    ],
    commands: ['python3 -B demo.py "Reply with the single word OK."', 'cat usage.log', 'curl -s http://127.0.0.1:11434/v1/models'],
    lesson: 'The starter reaches a model and prints its answer, but its record is guesswork: the cost comes from a character count, the finish reason is a constant, the latency is zero, nothing checks whether the prompt fits and every call overwrites the log. LEARN.md gives the complete contract. Verify talks to your ask() through a recording adapter whose token counts are deliberately unlike any character estimate, then makes one real call to the endpoint in llm.json and compares the prompt tokens with its own request. Configure llm.json with your local model first (Ollama answers on 127.0.0.1:11434 with no key) and warm it up with demo.py; a cold load of a large model can exceed the 15-second live limit, and that is reported as environment blocked, not as a failure. No model or English debrief is required for the technical result.',
    artifact: 'Metered client',
  },
]
export const voiceMissions: Mission[] = [...authored].sort((a, b) => a.order - b.order)

export const voiceFollowUps: Record<string, string[]> = {
  window: windowFollowUps,
  prompts: promptsFollowUps,
  backoff: backoffFollowUps,
  record: recordFollowUps,
  sampling: samplingFollowUps,
  price: ['The operator asks why two identical questions cost a different amount. Explain what can differ between two calls with the same prompt.', 'A colleague wants to estimate cost from the number of characters to save a request. Explain what breaks and when the estimate is still useful.'],
}
