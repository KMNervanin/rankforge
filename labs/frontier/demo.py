"""Terminal demo.

python3 -B demo.py            replay the five sample candidates from replay.json, print the frontier and the decision
python3 -B demo.py 800        same, with a p95 budget of 800 ms instead of budget.json
python3 -B demo.py --live     run the model from llm.json on the first three cases and write runs/live.json

Replay results are a fixture for the terminal, not a measurement; only --live reaches an endpoint.
"""
import json
import sys

import frontier


def load(name):
    with open(name, encoding="utf-8") as file:
        return json.load(file)


def replay_runner(table):
    def run_case(model, case, settings):
        return dict(table[model][case["id"]])
    return run_case


if __name__ == "__main__":
    cases, settings, budget = load("cases.json"), load("settings.json"), load("budget.json")
    if "--live" in sys.argv:
        endpoint = load("llm.json")
        if not endpoint.get("model"):
            sys.exit("Set the model id in llm.json first (for Ollama: the name shown by `ollama list`).")
        candidate = {"id": "live", "model": endpoint["model"], "input_price_per_million": endpoint.get("input_price_per_million", 0), "output_price_per_million": endpoint.get("output_price_per_million", 0)}
        subset = {"version": cases["version"] + "-first3", "cases": cases["cases"][:3]}
        manifests = frontier.run_candidates([candidate], subset, base_url=endpoint["base_url"], settings=settings, out_dir="runs")
        print(json.dumps(frontier.frontier(manifests), indent=2))
        sys.exit(0)
    if len(sys.argv) > 1:
        budget["p95_ms"] = int(sys.argv[1])
    manifests = frontier.run_candidates(load("candidates.json"), cases, base_url="replay://", settings=settings, out_dir="runs", run_case=replay_runner(load("replay.json")))
    rows = frontier.frontier(manifests)
    print(f"{'candidate':12} {'acc':>6} {'low':>6} {'high':>6} {'p50':>6} {'p95':>6} {'cost/100':>9} {'mem MB':>7} pareto")
    for row in rows:
        memory = "-" if row["peak_memory_mb"] is None else str(row["peak_memory_mb"])
        print(f"{row['candidate']:12} {row['accuracy']:6.3f} {row['accuracy_low']:6.3f} {row['accuracy_high']:6.3f} {row['p50_ms']:6d} {row['p95_ms']:6d} {row['cost_per_100']:9.4f} {memory:>7} {'yes' if row['pareto'] else 'no'}")
    print(json.dumps(frontier.decide(rows, budget), indent=2))
