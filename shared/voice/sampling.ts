import type { Mission } from '../types.js'

// G02: repeated sampling of one classification prompt; a seed is a measurement, not a promise.
export const mission: Mission = {
  id: 'sampling', chapter: 'voice', order: 2, title: 'Same question, different answers', subtitle: 'Measure the classifier’s variability under sampling settings', sector: 'Operator’s desk', icon: '⚄',
  block: 'Calling the model', files: ['experiment.py', 'settings.json', 'prompt.txt'],
  nudge: 'Rumour says the relay answers differently when several operators ask at the same moment.',
  skills: ['Sampling settings', 'Distribution reports', 'Reproducibility claims'], prerequisites: ['price'], xp: 240, duration: 'Self-paced', kind: 'build',
  briefs: {
    guided: 'The assistant classifies supply requests, but one answer is not a behavior. Ask the same question many times under each sampling setting, keep every raw answer, and compute the distribution from that file. Hints are available; guided work earns the same rewards.',
    connected: 'Turn a one-shot script into a repeated-sampling experiment: the declared number of samples per setting, a raw JSONL of every output, a report recomputed strictly from that file, and a reproducibility claim that comes from rerunning the seeded setting rather than from the seed itself.',
    independent: 'Build a repeated-sampling experiment whose report traces every number to a raw output file and whose reproducibility claims are earned by reruns, then run it against a server that honors the seed, one that ignores it, one that changes between runs and your own endpoint.',
  },
  objectives: [
    'Keep experiment.py importable with run_experiment(settings, *, base_url, model, prompt, samples, max_tokens, out_path, concurrency=1) and report(raw_path). A setting is {name, temperature, optional top_p, optional seed}; samples is 2–50. Read every value from the arguments, never from a constant.',
    'For every setting send exactly samples requests to POST {base_url}/chat/completions with {model, messages: [{role: "user", content: prompt}], max_tokens, temperature} plus top_p and seed when the setting has them, no stream: true. Record each as run "first" with index 0..samples−1. Then send samples identical requests for every seeded setting as run "rerun"; a setting without a seed is not rerun.',
    'out_path is created or truncated per run and holds one JSON line per output with setting, run, index, model, seed, temperature, top_p, content (verbatim), finish_reason, usage (the response object) and system_fingerprint (the response value or null). Any order; extra keys allowed.',
    'report(raw_path) recomputes everything from the file: per setting, over first-run answers (content.strip()), samples, seed, temperature, distinct, majority (ties to the lexicographically smallest), majority_share, agreement = Σ c(c−1) / (N(N−1)), entropy_bits = −Σ p log₂ p, reproducible and finish_reasons (counts). Tolerance 1e-9. run_experiment returns exactly report(out_path).',
    'reproducible is true only when the rerun’s answers equal the first run’s index by index, false when any position differs, null without a seed. First-run agreement and the presence of a seed are not evidence.',
    'report raises ValueError when a run’s indices are not exactly 0..n−1, when a seeded setting’s rerun count differs from its first run, or when the file is empty.',
    'Verify runs a scripted adapter that honors, ignores or outlives the seed (a labeled test tool), hand-built raw files, and one live experiment of 3 samples × 2 settings against the endpoint in llm.json whose numbers are reported as measurements. No model id or no answer within the time limits is environment blocked, not a failure. Keys stay in LLM_API_KEY, never in a workspace file.',
  ],
  languageGoal: 'State what a measurement supports and what it does not, with the number of samples behind it.', prompt: 'Tell the operator how stable the classifier is. Name the setting, the number of samples, the agreement you measured and whether the rerun matched, and say in one sentence what the seed did not guarantee.',
  hints: ['Run the demo twice with the same seed and diff raw.jsonl. Then look at what the starter writes per setting: how many lines, and where does its agreement of 1.0 come from?', 'A distribution needs N draws, and a claim that something repeats needs a second experiment. Which numbers in the report can be computed from the raw file alone, and which require another round of requests?', 'Group the raw records by setting and run, sort by index, strip each content, count with a dict or Counter, and compute agreement from the counts. Compare the sorted rerun answers with the first run element by element.'],
  sources: [
    { title: 'OpenAI chat completions reference: temperature, top_p, seed and system_fingerprint (deprecated, best-effort)', url: 'https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create' },
    { title: 'vLLM: reproducibility holds only for the same batch composition, hardware and version', url: 'https://docs.vllm.ai/en/stable/usage/reproducibility/' },
    { title: 'llama.cpp server README: seed and batching', url: 'https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md' },
    { title: 'Ollama OpenAI compatibility: supported request fields', url: 'https://github.com/ollama/ollama/blob/main/docs/api/openai-compatibility.mdx' },
    { title: 'Python concurrent.futures', url: 'https://docs.python.org/3.10/library/concurrent.futures.html' },
  ],
  commands: ['python3 -B demo.py 5', 'python3 -B demo.py 5 4', 'python3 -B -c "import experiment, json; print(json.dumps(experiment.report(\'raw.jsonl\'), indent=2))"', 'wc -l raw.jsonl'],
  lesson: 'The starter asks once per setting, copies that answer into a report that claims the declared sample count, agreement 1.0 and reproducibility wherever a seed is present, and its report() returns a cached dict instead of reading the file. LEARN.md gives the complete contract. Verify runs your run_experiment against a scripted adapter in three modes: one honors the seed, one ignores it, and one changes its answer and fingerprint after the first run, so a reproducibility claim derived from the seed or from first-run agreement fails while a rerun gets it right. It hand-builds raw files with ties, shuffled lines and broken indices, edits one line of your own file to see the report follow, and finally runs nine small requests against the endpoint in llm.json, reporting the measured agreement and entropy as numbers. Configure llm.json with your local model first and warm it up with the demo; a cold model is environment blocked, not a failure. No model or English debrief is required for the technical result.',
  artifact: 'Repeated-sampling experiment and distribution report',
}

export const followUps: string[] = [
  'The operator saw five identical answers and wants to call the assistant deterministic. Explain what those five samples support and what experiment would be needed before saying it again tomorrow.',
  'A colleague sets seed 42 on a hosted API and promises the relay crew identical answers forever. Explain what the server actually guarantees and what you would log to notice when it stops holding.',
]
