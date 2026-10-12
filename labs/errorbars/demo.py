"""Terminal demo: python3 -B demo.py [run_a.json] [run_b.json]

Scores two runs of the extraction step against golden.json with metrics.report and
prints the comparison. Defaults: runs/prompt-v2.json against runs/prompt-v3.json.
Try the same run against itself, and a run against runs/prompt-v3-swapped.json.
"""
import json
import sys

import metrics


def load_run(path, references):
    with open(path, encoding="utf-8") as file:
        run = json.load(file)
    return {"name": run["name"], "predictions": run["predictions"], "references": references}


if __name__ == "__main__":
    path_a = sys.argv[1] if len(sys.argv) > 1 else "runs/prompt-v2.json"
    path_b = sys.argv[2] if len(sys.argv) > 2 else "runs/prompt-v3.json"
    with open("golden.json", encoding="utf-8") as file:
        references = json.load(file)["cases"]
    result = metrics.report(load_run(path_a, references), load_run(path_b, references))
    for key in ("a", "b"):
        side = result[key]
        acc = side["accuracy"]
        print(f"--- {side['name']}: {acc['correct']}/{acc['n']} exact, Wilson [{acc['low']:.3f}, {acc['high']:.3f}]")
        for field, entry in side["fields"].items():
            print(f"    {field:<9} P {entry['precision']:.3f}  R {entry['recall']:.3f}  F1 {entry['f1']:.3f}  (tp {entry['tp']}, fp {entry['fp']}, fn {entry['fn']})")
        abst = side["abstention"]
        print(f"    abstain   {abst['correct']}/{abst['n']}")
    paired = result["paired"]
    print(f"--- paired: mean diff {paired['mean_diff']:+.4f}, SE {paired['se']:.4f}, interval [{paired['low']:+.4f}, {paired['high']:+.4f}] -> {paired['verdict']}")
    print(f"--- needed_n for the observed effect: {result.get('needed_n')}")
