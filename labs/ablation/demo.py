"""Terminal demo: python3 -B demo.py [leave-one-out|add-one-in] [relay-small|relay-large]

Reads harness.json (components and cases) and outcomes.json (scripted outcomes per
model: a fixture, never a model), runs ablation.ablate with a runner built from the
fixture, prints the table and the decision record. Defaults: leave-one-out, relay-small.
Run it twice with the same arguments and compare the numbers; then switch to relay-large.
"""
import json
import sys

import ablation


def scripted_runner(outcomes, model):
    truth = outcomes["models"][model]
    base = set(truth["base_correct"])

    def run(active, case):
        active = set(active)
        right = case["id"] in base or any(case["id"] in truth["helps"].get(name, []) for name in active)
        broken = any(case["id"] in truth["hurts"].get(name, []) for name in active)
        return {
            "correct": 1 if right and not broken else 0,
            "tokens": outcomes["case_tokens"][case["id"]] + sum(outcomes["component_tokens"][name] for name in active),
            "latency_ms": outcomes["case_latency_ms"][case["id"]] + sum(outcomes["component_latency_ms"][name] for name in active),
        }
    return run


if __name__ == "__main__":
    strategy = sys.argv[1] if len(sys.argv) > 1 else "leave-one-out"
    model = sys.argv[2] if len(sys.argv) > 2 else "relay-small"
    with open("harness.json", encoding="utf-8") as file:
        harness = json.load(file)
    with open("outcomes.json", encoding="utf-8") as file:
        outcomes = json.load(file)
    table = ablation.ablate(harness["components"], harness["cases"], scripted_runner(outcomes, model), strategy=strategy)
    print(f"--- {strategy} on {model} (scripted fixture), reference accuracy {table['reference'].get('accuracy', 0):.3f} on {table['reference'].get('n')} cases")
    for row in table["rows"]:
        low, high = row.get("low"), row.get("high")
        interval = f"[{low:+.3f}, {high:+.3f}]" if isinstance(low, (int, float)) and isinstance(high, (int, float)) else "[no interval]"
        print(f"{row['component']:<14} {row['kind']:<8} n={row.get('n')!s:<3} delta {row.get('mean_delta', 0):+.3f} {interval}  tokens {row.get('tokens_delta', 0):+.0f}  latency {row.get('latency_delta_ms', 0):+.0f} ms")
    print("--- decision record")
    print(json.dumps(ablation.decide(table, harness["components"]), indent=2))
