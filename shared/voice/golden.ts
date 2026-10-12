import type { Mission } from '../types.js'

export const mission: Mission = {
  id: 'golden', chapter: 'voice', order: 8, title: 'A golden set you can trust', subtitle: 'Version the cases, freeze the held-out part', sector: 'Measuring room', icon: '◈',
  block: 'Measuring the voice', files: ['goldenset.py', 'cases.json', 'fewshot.json'],
  nudge: 'Rumour says two of the cases in the set are the same request wearing different capitals.',
  skills: ['Evaluation sets', 'Content hashing', 'Data provenance'], prerequisites: ['traces'], xp: 240, duration: 'Self-paced', kind: 'build',
  briefs: {
    guided: 'The trace reading left a taxonomy of failures; now the outpost needs a set of cases that covers every category, says where each case came from, and keeps a held-out part no prompt has seen. Build the manifest, split it by seeded hash, freeze the held-out digest and catch a few-shot example copied from it. Hints are available; guided work earns the same rewards.',
    connected: 'Turn a list of cases into a versioned evaluation set: a deterministic train/dev/test split, a per-category minimum, a hash per case and a digest over the held-out part. Then prove that a disguised copy of a held-out case is caught in a few-shot list and that adding a case appends a version instead of rewriting history.',
    independent: 'Build a golden-set manifest whose split is a pure function of seed and id, whose held-out digest changes when a test case changes, whose leakage check reads through case and whitespace, and whose history grows by one entry per added case without touching earlier versions. Demonstrate it on the workspace cases and the three few-shot examples.',
  },
  objectives: [
    'Keep goldenset.py importable with build_manifest(cases, *, minimum_per_category, split_ratios, seed, version=1), check_leakage(manifest, few_shot_examples), add_case(manifest, case, *, note="") and verify_manifest(manifest). A case has id, input, expected, category and provenance {kind: real|synthetic, source: non-empty note}; a case without valid provenance is a ValueError at build and add time and a "provenance:" finding at verify time.',
    'Hash every case: sha256 of the canonical JSON (sort_keys, ensure_ascii=False, separators (",", ":")) of id, input, expected and category, stored as hash. A fresh manifest passes verify_manifest with [].',
    'Split by seeded hash: u = int(sha256(f"{seed}:{id}").hexdigest()[:8], 16) / 2**32; train when u < train ratio, dev when u < train + dev, otherwise test. The same id lands in the same split whatever the list order; counts add up to the number of cases; split_ratios must be the three keys summing to 1.',
    'Enforce minimum_per_category at build time with a ValueError naming the category; a category exactly at the minimum builds. verify_manifest reports a category below the minimum with a "category:" finding.',
    'Freeze the held-out part: held_out_digest = sha256 of the test-split case hashes, sorted and joined with newlines. verify_manifest recomputes it from the recomputed hashes of the current test cases, never from the stored hash fields: an edited test case yields a "hash:" finding naming the id plus a "held_out:" finding; an edited train case yields only the "hash:" finding.',
    'check_leakage compares each few-shot example with every dev and test case after normalization (non-alphanumerics to spaces, whitespace collapsed, stripped, casefolded) and returns one string per leak naming the case id and split. A train example or an unrelated text is never reported.',
    'add_case returns a new manifest and leaves the given one untouched: existing cases keep split and hash, the new case is split by the same rule, version increases by one, counts and digest are recomputed, and history gains one entry {version, action: add_case, case_ids, held_out_digest, note} with every earlier entry unchanged. A duplicate id is a ValueError. Verify has no live part: every verdict is recomputed in code from fresh fixtures.',
  ],
  languageGoal: 'Explain a hygiene rule by naming what it prevents and the one number it protects.', prompt: 'Explain to the operator why the few-shot examples may only come from the train split, and what the held-out digest protects. Use one case from your own set and say what would silently go wrong without each rule.',
  hints: ['Build the manifest twice with the cases in a different order and compare the splits by id. Then edit one expected value in goldenset.json and run demo.py verify: what changes, and what should have?', 'A split that depends on the position in the list changes when a case is added. Make it a function of the seed and the id alone, and make the held-out digest a function of the test cases’ content, so that an edit moves a published number.', 'Normalize before comparing: letters and digits only, one space between words, casefold. Keep the old manifest untouched by copying it, append one history entry, and let verify_manifest recompute everything from the cases rather than trusting the stored summaries.'],
  sources: [
    { title: 'Hamel Husain: Creating a LLM-as-a-Judge that drives business results (train/dev/test, few-shot source, frozen test)', url: 'https://hamel.dev/blog/posts/llm-judge/' },
    { title: 'Hamel Husain and Shreya Shankar: AI Evals FAQ (reading traces, first failure, taxonomy)', url: 'https://hamel.dev/blog/posts/evals-faq/' },
    { title: 'Python hashlib', url: 'https://docs.python.org/3.10/library/hashlib.html' },
    { title: 'Python json.dumps: sort_keys and separators for a canonical form', url: 'https://docs.python.org/3.10/library/json.html#json.dumps' },
  ],
  commands: ['python3 -B demo.py', 'python3 -B demo.py leak', 'python3 -B demo.py add', 'python3 -B demo.py verify'],
  lesson: 'The starter splits by list order, so adding or reordering cases silently moves them between splits; it stores no hash and an empty digest, so an edited held-out expectation leaves no trace; its leakage check compares raw strings, so a copy with different capitals passes; add_case rebuilds the whole manifest and its history from scratch; and nothing requires provenance or the per-category minimum. LEARN.md gives the complete contract with the hash, split and digest rules spelled out. Verify builds fresh cases every run and recomputes every hash, split and digest with those published rules in its own code; there is no model and no live part. Out of scope: scoring the cases (the next mission) and the 30–50 pass/fail balance per split, which the workspace cases cannot reach.',
  artifact: 'Versioned golden-set manifest',
}

export const followUps: string[] = [
  'The operator wants to tune the prompt on the test split because dev is "too small". Explain what number is lost that way and what to do instead.',
  'A colleague adds twenty synthetic cases written from the taxonomy and asks whether the set is now representative. Say what provenance tells you and what it cannot.',
]
