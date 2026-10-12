import type { Mission } from '../types.js'

// G09 of chapter IX: code-based metrics with uncertainty. No live call: every number comes from the learner's code on fixed outcomes.
export const mission: Mission = {
  id: 'errorbars', chapter: 'voice', order: 9, title: 'Numbers with error bars', subtitle: 'Report uncertainty before claiming a win', sector: 'Operator’s desk', icon: '±',
  block: 'Measuring the voice', files: ['metrics.py', 'golden.json', 'runs/prompt-v2.json', 'runs/prompt-v3.json'],
  nudge: 'Rumour says the relay’s mistakes come in families: cases cut from the same report fail together.',
  skills: ['Precision and recall', 'Wilson interval', 'Paired comparison'], prerequisites: ['golden', 'capacity'], xp: 240, duration: 'Self-paced', kind: 'build',
  briefs: {
    guided: 'Two prompt versions ran over the golden set and one got three more cases right. Make the calculator say what that is worth: per-field precision and recall, abstention accuracy, an interval around every proportion and a paired rule that decides better, worse or inconclusive. Hints are available; guided work earns the same rewards.',
    connected: 'Turn a bigger-number-wins script into a metric calculator: normalized field matching, Wilson intervals that stay inside [0, 1], per-case paired differences with a standard error, and a report that says how many cases the observed effect would need. Prove it on hand-computed fixtures.',
    independent: 'Build a metric calculator and comparison report whose every number reproduces from exact fractions, whose verdict follows the published paired rule and never two overlapping intervals, and whose conclusion changes with the set size and not with the effect. Demonstrate it on two runs with the same count and different pairings.',
  },
  objectives: [
    'Keep metrics.py importable with field_scores, abstention_accuracy, case_scores, wilson, paired_comparison and report. Every function that takes two mappings requires the same case ids on both sides and at least one case; otherwise ValueError. Tolerance on every number is 1e-9.',
    'field_scores(predictions, references) returns, for exactly item, quantity, unit and urgency, tp, fp, fn, precision, recall and f1. A predicted field equals the reference only after normalization: integral numbers as their digits, everything else as text, trimmed, whitespace collapsed, casefolded. A missing or null field, an abstain or a null outcome predicts nothing; a mismatch is one false positive and one false negative; a zero denominator gives 0.0.',
    'abstention_accuracy(predictions, references) counts only the cases whose reference is "abstain": n, correct, accuracy and the Wilson bounds low and high at z = 1.96; with no such case accuracy, low and high are null. case_scores gives each case 1.0 for an exact match (both abstain, or all four fields equal after normalization) and 0.0 otherwise.',
    'wilson(successes, n, z=1.96) returns (low, high) from the closed-form Wilson score interval; both bounds stay inside [0, 1] for 0 of 5 and 30 of 30 and never overshoot; n = 0 raises ValueError.',
    'paired_comparison(scores_a, scores_b, z=1.96, clusters=None) returns n, mean_diff, se, low, high and verdict from the per-case differences b − a: se is the sample standard deviation (n − 1) over sqrt(n), the interval is mean_diff ± z·se, the verdict is "better" only when low > 0, "worse" only when high < 0, otherwise "inconclusive". Fewer than two cases raise ValueError.',
    'The rule is paired, never two overlapping intervals and never two means: +2 points on 30 cases is inconclusive, the same +2 points on 1000 cases with twenty single-case gains is better and worse when reversed, and overlapping unpaired intervals with consistent paired differences decide better while a run with the same mean and disagreeing differences does not.',
    'report(run_a, run_b, z=1.96, clusters=None) requires equal references, composes fields, abstention and the exact-match accuracy with its Wilson bounds per run, the paired comparison and needed_n = ceil((z + 0.8416)² · variance / mean_diff²) for the observed effect (null when the mean difference is 0, accepted within 1). Verify recomputes every expected value with fractions.Fraction on its own fixtures and never calls a model.',
  ],
  languageGoal: 'State a result with its uncertainty and say what would be needed to make it conclusive.', prompt: 'Tell the operator whether prompt v3 is better than v2. Give the paired interval, say why three more right answers on thirty cases do not decide it, and name the number of cases at which the same difference would.',
  hints: ['Run the demo on v2 against v3 and on v2 against v3-swapped: the exact-match counts are equal. Which cases changed sides in each, and what does the starter say about both?', 'Precision needs false positives, a proportion needs an interval that respects 0 and 1, and a comparison needs the per-case differences, not two summaries. Which of the three does the starter skip entirely, and which does it fake?', 'For each case compute b − a, then the mean, the sample standard deviation over sqrt(n) and mean ± 1.96·se; the sign of the interval’s far end is the verdict. Build the Wilson bounds from the closed form with p, n and z; the needed set size is (1.96 + 0.8416)² times the variance over the squared mean.'],
  sources: [
    { title: 'Miller, Adding Error Bars to Evals (arXiv 2411.00640)', url: 'https://arxiv.org/abs/2411.00640' },
    { title: 'Wilson score interval (binomial proportion confidence interval)', url: 'https://en.wikipedia.org/wiki/Binomial_proportion_confidence_interval#Wilson_score_interval' },
    { title: 'Python statistics: fmean, variance and NormalDist', url: 'https://docs.python.org/3.10/library/statistics.html' },
    { title: 'Python fractions: exact arithmetic for an oracle', url: 'https://docs.python.org/3.10/library/fractions.html' },
  ],
  commands: ['python3 -B demo.py', 'python3 -B demo.py runs/prompt-v2.json runs/prompt-v3-swapped.json', 'python3 -B demo.py runs/prompt-v2.json runs/prompt-v2.json', 'python3 -c "import metrics; print(metrics.wilson(0, 5), metrics.wilson(30, 30))"'],
  lesson: 'The starter compares raw values so a shouted item name or a quantity written as a string counts as wrong, never records a false positive so precision is always 1.0, divides abstention hits by every case, computes the naive p ± z·sqrt(p(1−p)/n) that collapses to [0, 0] and crosses 1 at the edges, declares a win whenever the second mean is larger and reports two overlapping intervals as if they were a test. LEARN.md publishes the normalization, the counting rule, the closed-form Wilson interval, the paired rule with a sample standard error and the needed-n formula. Verify recomputes every expected number from exact fractions on tiny fixtures with fresh names and counts; the only way through is to compute what is published. No model is called and no English debrief is required for the technical result.',
  artifact: 'Metric calculator and comparison report',
}

export const followUps: string[] = [
  'The operator saw v3 win on the demo and wants to ship it today. Explain in two sentences what the interval says, and what you would need to run to be sure by Friday.',
  'A colleague proposes running the eval at temperature 0 so the numbers stop moving between runs. Explain what that changes about the measurement and what it hides.',
]
