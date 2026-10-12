import type { Mission } from '../types.js'

// G13 of chapter IX: ablation of harness components with paired intervals. No live call: the runner is injected and Verify's runners are scripted.
export const mission: Mission = {
  id: 'ablation', chapter: 'voice', order: 13, title: 'Take the scaffolding away', subtitle: 'Measure each harness component by removing it', sector: 'Operator’s desk', icon: '⌫',
  block: 'Measuring the voice', files: ['ablation.py', 'harness.json', 'outcomes.json', 'demo.py'],
  nudge: 'Rumour says six questions asked at once will get one stray yes.',
  skills: ['Ablation study', 'Paired intervals', 'Guard labeling'], prerequisites: ['frontier', 'judge'], xp: 260, duration: 'Self-paced', kind: 'build',
  briefs: {
    guided: 'The assistant’s harness has six components and nobody remembers which ones matter. Remove each one, rerun the same cases, put an interval on the difference and keep only what earns its place, except the guards, which stay for reasons accuracy cannot see. Hints are available; guided work earns the same rewards.',
    connected: 'Turn a random-subset, two-means ablation into a paired study: both arms on the whole set, per-case differences with a sample standard error and a z interval, a keep rule that reads the interval and not the mean, guards kept and labeled with their non-quality reason, and an add-one-in strategy that reaches the same decision. Prove it on a scripted runner with a planted truth.',
    independent: 'Build an ablation table and decision record whose every number reproduces from the paired formula under leave-one-out and add-one-in, whose decisions follow the intervals, whose guards are never dropped, and whose verdicts change when a stronger model changes which components help.',
  },
  objectives: [
    'Keep ablation.py importable with ablate(components, cases, run, *, strategy="leave-one-out", z=1.96) -> table and decide(table, components) -> record. Components carry a distinct name, a kind of quality or guard and, for guards, a reason of permission, safety or cost; cases carry a distinct id; run(active, case) is injected and returns correct (0 or 1), tokens and latency_ms.',
    'An unknown strategy, a repeated or missing name, an unknown kind, a guard without a listed reason, a repeated case id or fewer than two cases raise ValueError before any call to run.',
    'One row per component in input order. Leave-one-out: without is every component but this one, with is every component. Add-one-in: without is every guard but this one, with is that set plus this one. Both arms run on every case; the row lists every case id in input order and n is their count. A row computed on a subset is rejected.',
    'Per case d = correct(with) − correct(without); mean_delta is the mean, se the sample standard deviation (n − 1) over sqrt(n), low and high are mean_delta ∓ z·se; tokens_delta and latency_delta_ms are the mean per-case differences; accuracy_with and accuracy_without are each arm’s mean. The table carries strategy, z, cases, reference (the base arm’s active list, n and means) and rows. Tolerance 1e-9.',
    'A quality component is kept when low > 0 and dropped otherwise: an interval that includes zero has not earned its place, one below zero hurts. A guard is always kept and its reason starts with kept for permission, kept for safety or kept for cost; accuracy rising without an authorization check never removes it.',
    'The record carries strategy, z, n, keep and drop partitioning the names, and decisions: one entry per component with component, kind, decision, reason and the row’s n, mean_delta, low, high, tokens_delta and latency_delta_ms; every reason cites the interval as [low, high] with three decimals. Add-one-in reaches the same keep list as leave-one-out on the same truth; a stronger model’s planted truth at z = 2.326 changes which components are kept.',
    'Verify plants fresh truths with fresh ids, set sizes and costs, drives your functions through a scripted runner that logs every call, recomputes every number with exact fractions and never calls a model. There is no live part.',
  ],
  languageGoal: 'Justify keeping or removing something with a measured interval, and separate a quality argument from a policy one.', prompt: 'Tell the operator which components of the assistant you removed and why. For one of them give the interval and say what it rules out. Then explain why the authorization check stays even though accuracy was higher without it, in words that do not use the word accuracy.',
  hints: ['Run the demo twice with the same arguments and compare the rows. Which numbers move between two runs of the same harness, and what does that say about the cases each row used?', 'A removal is a paired comparison: the same case with and without the component, one difference per case, a standard error from those differences. Which of the starter’s numbers could carry an interval and which cannot, and what does the kind field tell you that the interval does not?', 'For each component build the with and without lists from the strategy, run both on every case, compute d per case, then mean, sample standard deviation over sqrt(n) and mean ± z·se; keep a quality component only when low > 0, keep every guard and write kept for <reason> in front of its numbers.'],
  sources: [
    { title: 'Anthropic, Building effective agents', url: 'https://www.anthropic.com/research/building-effective-agents' },
    { title: 'Miller, Adding Error Bars to Evals (arXiv 2411.00640)', url: 'https://arxiv.org/abs/2411.00640' },
    { title: 'Python statistics: fmean, stdev and NormalDist', url: 'https://docs.python.org/3.10/library/statistics.html' },
    { title: 'Python fractions: exact arithmetic for an oracle', url: 'https://docs.python.org/3.10/library/fractions.html' },
  ],
  commands: ['python3 -B demo.py', 'python3 -B demo.py add-one-in relay-small', 'python3 -B demo.py leave-one-out relay-large'],
  lesson: 'The starter samples a different random half of the cases for the baseline and for every removal, so its deltas mix the component with the draw; it reports a difference of two means with no standard error and no interval; it treats the strategy argument as decoration; it validates nothing; and it drops anything whose absence raised accuracy, including the authorization check that refuses what the operator may not see. LEARN.md publishes the two strategies, the paired formula, the keep rule on the interval and the guard label. Verify plants fresh truths, logs every call of its scripted runner, recomputes every number from exact fractions and checks that the guard survives a rise in accuracy; the only way through is to run both arms on the whole set and read the interval. No model is called and no English debrief is required for the technical result.',
  artifact: 'Ablation table and harness decision record',
}

export const followUps: string[] = [
  'The operator points out that the assistant answers more questions correctly without the authorization check and asks you to remove it. Explain in two sentences what those extra right answers are and why they are not a win.',
  'A colleague proposes removing two components at once to save evaluation time. Explain what a leave-one-out table cannot tell you about the pair and how you would measure it.',
]
