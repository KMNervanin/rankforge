"""Terminal demo: python3 -B demo.py [--top-n N] [--budget MS] [--min-gain G]

Reads rankings.json (canned lexical and dense lists, scripted reranker scores and declared costs),
runs fusion.measure over the six questions with a simulated clock and prints the report and the
decision. The scorer and the clock are a simulation of the reranker's cost, not a model: the only
purpose is to see the whole pipeline before the real numbers arrive. Defaults: top-n 3, p95 budget
40 ms, minimum MRR gain 0.05. Try --budget 25 and watch the decision flip.
"""
import json
import sys

import fusion


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def advance_ms(self, milliseconds):
        self.now += milliseconds / 1000


def option(name, default, cast):
    if name in sys.argv:
        return cast(sys.argv[sys.argv.index(name) + 1])
    return default


if __name__ == "__main__":
    top_n = option("--top-n", 3, int)
    budget = {"min_mrr_gain": option("--min-gain", 0.05, float), "p95_ms": option("--budget", 40.0, float)}
    with open("rankings.json", encoding="utf-8") as file:
        data = json.load(file)
    by_text = {query["text"]: query["id"] for query in data["queries"]}
    clock = Clock()

    def retriever(kind):
        def retrieve(text):
            clock.advance_ms(data["costs_ms"][kind])
            return [tuple(pair) for pair in data[kind][by_text[text]]]
        return retrieve

    def scripted_scorer(text, doc_id):
        clock.advance_ms(data["costs_ms"]["per_pair"])
        return data["rerank_scores"][by_text[text]].get(doc_id, 0.0)

    report = fusion.measure(data["queries"], [retriever("lexical"), retriever("dense")], clock=clock, score_fn=scripted_scorer, top_n=top_n)
    for row in report["queries"]:
        print(f"{row['id']}: fused {row['fused'][:4]} hit {row['hit']['fused']} | reranked {row['reranked'][:4]} hit {row['hit']['reranked']} | {row['latency_ms']['fused']:.1f} → {row['latency_ms']['reranked']:.1f} ms")
    print("--- aggregates (simulated clock, scripted scorer)")
    for key in ("mrr", "p50_ms", "p95_ms"):
        print(f"{key}: fused {report[key]['fused']:.4f}  reranked {report[key]['reranked']:.4f}")
    print("--- decision")
    print(json.dumps(fusion.decide(report, budget), indent=2))
