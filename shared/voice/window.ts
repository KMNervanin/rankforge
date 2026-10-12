import type { Mission } from '../types.js'

// G06 of chapter IX: a context builder with a published budget policy. No live call: fitting is decided before any request.
export const mission: Mission = {
  id: 'window', chapter: 'voice', order: 6, title: 'Fit the window', subtitle: 'Assemble context under a token budget', sector: 'Operator’s desk', icon: '▣',
  block: 'Calling the model', files: ['context.py', 'context.json', 'demo.py'],
  nudge: 'Rumour says the relay gets confused by an answer whose question was never asked.',
  skills: ['Context budgeting', 'Priority policy', 'Token bounds'], prerequisites: ['prompts', 'capacity'], xp: 240, duration: 'Self-paced', kind: 'build',
  briefs: {
    guided: 'The assistant now carries instructions, pinned facts, documents and a morning of chat into every call, and the model has one window for all of it plus its answer. Make the builder keep what matters, cut what is cheap and leave room for the reply. Hints are available; guided work earns the same rewards.',
    connected: 'Turn a stuff-everything-in builder into a budget policy: mandatory sections never cut, history dropped oldest-first, documents by priority and shortened only at passage boundaries with a visible marker, the reserve for the answer always free. Prove it with injected counters and probe facts.',
    independent: 'Build a context builder whose output never exceeds window minus the reserved output under any injected counter, whose policy is published and deterministic, and whose report accounts for every section. Demonstrate it on a model with half the window.',
  },
  objectives: [
    'Keep context.py importable with the class BudgetError, the function estimate(text) = len(text.encode("utf-8")) and build(sections, *, window, reserve_output, overhead, count=estimate) -> (messages, report). Sections carry id, kind (instructions, pinned, document with an integer priority where 1 is most important, history with role user or assistant, oldest first) and text. Compute every cost as count(content) + overhead with the injected counter.',
    'The budget is window - reserve_output. The total cost of the returned messages never exceeds it. Instructions, pinned facts and the newest history turn are mandatory and verbatim; if they alone exceed the budget, raise BudgetError and return nothing. With half the window the mandatory sections still fit or the call is refused.',
    'Messages are: instructions in input order, pinned facts in input order, included documents in ascending priority with ties in input order, kept history oldest to newest. Instructions, pinned facts and documents use role system; a history turn keeps its role and ends the messages.',
    'Documents are filled by priority after the mandatory sections. One that fits is kept whole. One that does not fit keeps a subset of whole passages (split at blank lines) in original order and ends with the line [shortened: kept K of N passages] after a blank line; at least one passage, or the document is dropped. Never cut inside a passage and never shorten silently.',
    'History is kept newest-first while the next older turn fits; once a turn does not fit, it and every older turn are dropped. The kept history is a contiguous run ending at the newest turn.',
    'The same inputs build the same messages and the same report, byte for byte. The report carries window, reserve_output, budget, overhead, method (the counter’s __name__), total (the recomputed sum, at most the budget) and sections: one entry per input section in input order with id, kind, status (kept, shortened, dropped), tokens (cost of the full text) and kept (cost of the emitted message, 0 when dropped), adding up to total.',
    'Verify builds fresh fixtures, derives every budget from its own counters (a word counter, bytes divided by three and your byte bound), probes a relay code and a bay name that must survive, and never calls a model. There is no live part.',
  ],
  languageGoal: 'Describe a policy as rules with their order and say what each rule protects.', prompt: 'Explain to the operator what the assistant forgets first when a conversation grows long, and why the instructions and the current question are never among the first things to go. Name one thing your report shows that the model’s answer alone could not.',
  hints: ['Run the demo at 1200, 700 and 350 tokens and read the report. Which section disappears first, and what does its priority field say about why?', 'A budget is the window minus what the answer needs, and every message pays its framing once. Which sections can you decide about before you look at any document, and which only after?', 'Split a document at blank lines, keep whole passages until the next one and the marker would not fit, then walk the history from the newest turn backwards and stop at the first one that does not fit.'],
  sources: [
    { title: 'OpenAI cookbook: counting tokens and fitting the context window', url: 'https://cookbook.openai.com/examples/how_to_count_tokens_with_tiktoken' },
    { title: 'Ollama server/prompt.go: old messages are dropped from the front, system and last message stay', url: 'https://github.com/ollama/ollama/blob/main/server/prompt.go' },
    { title: 'llama.cpp server README: a prompt over the context size is refused', url: 'https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md' },
    { title: 'Python re.split: passages at blank lines', url: 'https://docs.python.org/3.10/library/re.html#re.split' },
  ],
  commands: ['python3 -B demo.py 1200 128', 'python3 -B demo.py 700 128', 'python3 -B demo.py 350 64'],
  lesson: 'The starter sorts every section by a priority field that only documents have, so the instructions, pinned facts and chat sort last and are the first to be dropped; it compares against the whole window instead of window minus the reserve, cuts documents by characters without any marker, keeps the oldest turns and drops the newest, and its default counter divides characters by four. LEARN.md publishes the policy: mandatory sections, document priority with shortening at passage boundaries, history as a contiguous newest run, a report that adds up. Verify injects its own counters and derives every budget from them, so the only way through is to compute with the counter you were given. No model is called and no English debrief is required for the technical result.',
  artifact: 'Context builder with a per-call budget report',
}

export const followUps: string[] = [
  'The operator asks why the assistant answered yesterday’s question instead of today’s after a long chat. Explain which rule of your policy prevents that and what the report would have shown.',
  'A colleague proposes summarizing old history with the model to keep more of it. Explain what that changes in the budget, what it costs and what your builder would need to verify about the summary.',
]
