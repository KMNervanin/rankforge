"""Terminal demo: python3 -B demo.py [criterion id] | --pairwise | --probe

Reads llm.json (endpoint, model id and judge version, no secrets), criteria.json, items.json and
labels.json. Without arguments it prints the calibration report of cites_source against the human
labels; with a criterion id it reports that criterion (neutral_tone has no labels and must be
refused); --pairwise compares it-01 against it-02 with the order swap; --probe runs the length-bias
probe with it-07 as the short supported answer and it-09 as the padded one.
"""
import json
import sys

import judge

if __name__ == "__main__":
    arguments = sys.argv[1:]
    with open("llm.json", encoding="utf-8") as file:
        endpoint = json.load(file)
    with open("criteria.json", encoding="utf-8") as file:
        criteria = {criterion["id"]: criterion for criterion in json.load(file)}
    with open("items.json", encoding="utf-8") as file:
        items = {item["id"]: item for item in json.load(file)}
    with open("labels.json", encoding="utf-8") as file:
        labels = json.load(file)
    if not endpoint["model"]:
        sys.exit("Set the model id in llm.json first (for Ollama: the name shown by `ollama list`).")
    options = {"base_url": endpoint["base_url"], "model": endpoint["model"], "judge_version": endpoint.get("judge_version", "demo"), "max_tokens": int(endpoint.get("max_tokens", 8))}
    criterion = criteria["cites_source"]
    if "--pairwise" in arguments:
        result = judge.judge_pairwise(criterion, items["it-01"], items["it-02"], **options)
    elif "--probe" in arguments:
        result = judge.length_bias_probe(criterion, items["it-07"], items["it-09"], **options)
    else:
        criterion = criteria[arguments[0]] if arguments else criterion
        result = judge.calibration_report(criterion, list(items.values()), labels, **options)
    print(json.dumps(result, indent=2, ensure_ascii=False))
