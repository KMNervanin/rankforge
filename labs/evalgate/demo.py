"""Terminal demo: python3 -B demo.py [prompt_version] [model]

Assembles the gate config from gate.json and the manifest in cases.json, takes
the baseline from baseline.json and replays the recorded outcomes of replay.json
for the chosen model id through gate.run_gate. The replay is a fixture, not a
model; it stands in for the model-plus-judge runner of a real pipeline. Try
`v3 relay-small`, then `v3 relay-large`, then `v4 relay-small`, and read the
results directory afterwards.
"""
import json
import sys
import time
from collections import Counter

import gate

if __name__ == "__main__":
    prompt_version = sys.argv[1] if len(sys.argv) > 1 else "v3"
    model = sys.argv[2] if len(sys.argv) > 2 else "relay-small"
    with open("gate.json", encoding="utf-8") as file:
        config = json.load(file)
    with open("cases.json", encoding="utf-8") as file:
        config["manifest"] = json.load(file)
    with open("baseline.json", encoding="utf-8") as file:
        baseline = json.load(file)
    with open("replay.json", encoding="utf-8") as file:
        replay = json.load(file)
    if model not in replay:
        sys.exit(f"replay.json has no recorded outcomes for {model!r}; known: {sorted(key for key in replay if not key.startswith('_'))}")
    script, attempts = replay[model], Counter()

    def run_case(case):
        entry = script[case["id"]]
        index = attempts[case["id"]]
        attempts[case["id"]] += 1
        outcomes = entry["attempts"]
        passed = outcomes[min(index, len(outcomes) - 1)]
        time.sleep(0.01)  # a replay is instant; the gate's clock still moves
        return {"passed": passed, "tokens": entry["tokens"], "seconds": entry["seconds"], "output": f"replay {case['id']} attempt {index + 1}"}

    try:
        decision = gate.run_gate(config, candidate={"prompt_version": prompt_version, "model": model}, baseline_results=baseline, run_case=run_case, clock=time.time)
    except gate.ConfigError as error:
        sys.exit(f"ConfigError: {error}")
    print(json.dumps({key: value for key, value in decision.items() if key != "results"}, indent=2, ensure_ascii=False))
