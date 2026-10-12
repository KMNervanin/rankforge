"""Terminal demo: python3 -B demo.py "Reply with the single word OK."

Reads llm.json (endpoint and model, no secrets) and models.json (price table),
makes one call through client.ask and prints the metered record.
"""
import json
import sys

import client

if __name__ == "__main__":
    prompt = " ".join(sys.argv[1:]) or "Reply with the single word OK."
    with open("llm.json", encoding="utf-8") as file:
        endpoint = json.load(file)
    with open("models.json", encoding="utf-8") as file:
        manifest = json.load(file)
    model = endpoint["model"]
    if not model:
        sys.exit("Set the model id in llm.json first (for Ollama: the name shown by `ollama list`).")
    manifest["models"].setdefault(model, {key: endpoint[key] for key in endpoint if key.endswith("_per_million") or key == "context_window"})
    record = client.ask(prompt, base_url=endpoint["base_url"], model=model, max_tokens=int(endpoint.get("max_tokens", 64)), manifest=manifest, log_path="usage.log")
    print(json.dumps(record, indent=2, ensure_ascii=False))
