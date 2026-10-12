"""Terminal demo: python3 -B demo.py [samples] [concurrency]

Reads llm.json (endpoint and model, no secrets), settings.json (the sampling settings) and prompt.txt
(the fixed classification prompt), runs experiment.run_experiment and prints the report. Raw outputs
land in raw.jsonl; `python3 -B -c "import experiment, json; print(json.dumps(experiment.report('raw.jsonl'), indent=2))"`
recomputes the report from that file alone.
"""
import json
import sys

import experiment

if __name__ == "__main__":
    samples = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    concurrency = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    with open("llm.json", encoding="utf-8") as file:
        endpoint = json.load(file)
    with open("settings.json", encoding="utf-8") as file:
        settings = json.load(file)
    with open("prompt.txt", encoding="utf-8") as file:
        prompt = file.read().strip()
    model = endpoint["model"]
    if not model:
        sys.exit("Set the model id in llm.json first (for Ollama: the name shown by `ollama list`).")
    result = experiment.run_experiment(settings, base_url=endpoint["base_url"], model=model, prompt=prompt, samples=samples,
                                       max_tokens=int(endpoint.get("max_tokens", 4)), out_path="raw.jsonl", concurrency=concurrency)
    print(json.dumps(result, indent=2, ensure_ascii=False))
