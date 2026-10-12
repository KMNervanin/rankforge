"""Terminal demo: python3 -B demo.py [--schema] ["free text of a supply request"]

Reads llm.json (endpoint and model, no secrets) and catalog.json, runs extract on the given text
or on every fixture in requests.json, and prints each result with its attempt log. --schema sends
the published schema as response_format json_schema; without it the request is prompt-only.
"""
import json
import sys

import extract

if __name__ == "__main__":
    arguments = [argument for argument in sys.argv[1:] if argument != "--schema"]
    enforced = "--schema" in sys.argv[1:]
    with open("llm.json", encoding="utf-8") as file:
        endpoint = json.load(file)
    with open("catalog.json", encoding="utf-8") as file:
        catalog = json.load(file)
    if not endpoint["model"]:
        sys.exit("Set the model id in llm.json first (for Ollama: the name shown by `ollama list`).")
    if arguments:
        texts = [" ".join(arguments)]
    else:
        with open("requests.json", encoding="utf-8") as file:
            texts = [fixture["text"] for fixture in json.load(file)]
    for text in texts:
        result = extract.extract(text, base_url=endpoint["base_url"], model=endpoint["model"], catalog=catalog, schema_enforced=enforced, max_tokens=int(endpoint.get("max_tokens", 256)))
        print(f"--- {text}")
        print(json.dumps(result, indent=2, ensure_ascii=False))
