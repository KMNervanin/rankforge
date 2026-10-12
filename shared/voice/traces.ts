import type { Mission } from '../types.js'

export const mission: Mission = {
  id: 'traces', chapter: 'voice', order: 7, title: 'Read the traces first', subtitle: 'Derive the failure taxonomy from what you read', sector: 'Measuring room', icon: '⌕',
  block: 'Measuring the voice', files: ['taxonomy.py', 'annotations.jsonl', 'taxonomy.json', 'traces.jsonl'],
  nudge: 'Rumour says a definition nobody can point at a trace for is a definition nobody will apply the same way twice.',
  skills: ['Error analysis', 'Open coding', 'Reconciliation'], prerequisites: ['sampling', 'record'], xp: 240, duration: 'Self-paced', kind: 'build',
  briefs: {
    guided: 'Everyone has an opinion about what the assistant gets wrong and nobody has read the traces. Read at least a hundred, write what you see on the first thirty in your own words, then group your notes into categories that cite their traces and count. Hints are available; guided work earns the same rewards.',
    connected: 'Replace a taxonomy written before reading with one derived from annotations: one first-failure label per trace, categories that cite trace ids, counts that reconcile, and code that reports inconsistencies instead of hiding them. Then apply it to a fresh batch and see what recurs.',
    independent: 'Perform an error analysis in the Husain and Shankar manner on 120 recorded traces: open notes on the first thirty, axial coding into a counted taxonomy with trace references, a reconciliation that rejects every way the counts can lie, and a recurrence report on a fresh batch.',
  },
  objectives: [
    'Keep taxonomy.py importable with load_annotations(path) -> list[dict], build_taxonomy(annotations, definitions=None) -> dict, reconcile(annotations, taxonomy) -> list[str] and recurrence(taxonomy, new_annotations) -> dict. annotations.jsonl holds one object per line: trace_id (matching [a-z]{2}-[0-9]{4}), open_note and first_failure, which is "pass" or one category name.',
    'load_annotations returns the records in file order with trace_id, open_note ("" when absent) and first_failure as written, skipping blank lines, and raises ValueError naming the trace id for a missing or empty trace_id, a missing, empty or non-string first_failure (a list of two labels is not one first failure) or a trace id annotated twice.',
    'build_taxonomy derives {total, passes, categories} from the annotations alone: one category per distinct non-pass label, ordered by count descending then name, each with name, definition (from the definitions mapping, else ""), trace_ids in annotation order and count equal to len(trace_ids).',
    'reconcile returns [] for a consistent taxonomy and otherwise one string per inconsistency with a published prefix: coverage: (fewer than 100 annotations, or an empty open_note among the first 30, naming the id), empty: (a category with no trace ids), unknown: (a cited id with no annotation), label: (a cited trace annotated differently, including pass), count: (count differs from the distinct ids cited), missing: (an annotated failure no category of that name cites), total: (total, passes or counts plus passes do not add up).',
    'recurrence recomputes every number from the fresh batch: total, passes, recurring {name: count} for the taxonomy’s categories seen in the batch, absent (its categories with none, in taxonomy order) and new {label: count} for labels the taxonomy lacks. The taxonomy’s own counts never appear in the result.',
    'Your reading: annotations.jsonl covers at least 100 of the shipped tr- ids, each once and no other ids (fresh.jsonl is annotated in fresh-annotations.jsonl), with non-empty open notes on the first 30 lines and one label or pass per trace; at most 12 of your pass-or-failure decisions may disagree with the recorded outcome of the shipped traces. taxonomy.json reconciles with annotations.jsonl under the rules above and gives every category a non-empty definition. Verify parses both files itself and uses its own vx- fixtures for the code checks; nothing is live.',
  ],
  languageGoal: 'Define a category by an observable symptom and support it with a counted example.', prompt: 'Present your three largest failure categories to the operator. For each, give the definition in one sentence, the count, one trace id, and say what you would look at in that trace to recognise the category again.',
  hints: ['Run python3 -B demo.py next and read one trace top to bottom: request, passages, tool calls, answer. Write what you see before naming anything. Where does the exchange first go wrong, and could you have seen it from the answer alone?', 'A taxonomy is a function of the annotations, not a document next to them: group the labels, cite the ids, count the citations. Every number in taxonomy.json should be recomputable from annotations.jsonl, and reconcile is the function that checks exactly that.', 'For reconcile, index the annotations by trace id and walk the categories once: ids with no annotation, ids with another label, counts versus distinct citations, failures nobody cites, then the totals. Give each finding its prefix and name the id or category; demo.py report prints what you still owe.'],
  sources: [
    { title: 'Hamel Husain and Shreya Shankar, AI Evals FAQ: error analysis, open and axial coding, first failure per trace', url: 'https://hamel.dev/blog/posts/evals-faq/' },
    { title: 'Hamel Husain, Your AI product needs evals', url: 'https://hamel.dev/blog/posts/evals/' },
    { title: 'Hamel Husain and Shreya Shankar, A field guide to rapidly improving AI products', url: 'https://hamel.dev/blog/posts/field-guide/' },
    { title: 'Python json module', url: 'https://docs.python.org/3.10/library/json.html' },
  ],
  commands: ['python3 -B demo.py next', 'python3 -B demo.py show tr-0017', 'python3 -B demo.py report', 'python3 -B demo.py transfer'],
  lesson: 'The starter ships a taxonomy written before anyone read a trace: five categories with no trace references and counts invented to add up, a build_taxonomy that reads those counts back from taxonomy.json, a reconcile that only checks the taxonomy against itself, a recurrence that copies the old counts onto the new batch and a loader that accepts duplicates and lists of labels. LEARN.md gives the complete contract. Verify loads your module with fresh vx- annotation fixtures and hand-recomputed expectations, plants one inconsistency at a time, and then parses your own annotations.jsonl and taxonomy.json to confirm that at least 100 shipped traces were read once each with notes on the first 30, that your pass-or-failure decisions agree with the recorded outcomes within a tolerance of 12, and that the taxonomy reconciles. The category names and the grouping are yours; they are discussed in the debrief, not graded by code. Out of scope: a golden set, judges, statistics and anything live; no model is called.',
  artifact: 'Annotated traces and a counted taxonomy',
}

export const followUps: string[] = [
  'A colleague proposes adding a category "hallucination" that already has forty traces in it. Explain why one broad category hides more than it shows and how you would split it, with trace ids.',
  'The fresh batch shows a failure your taxonomy has no name for. Say what you do with the taxonomy, with the counts, and with the traces already annotated.',
]
