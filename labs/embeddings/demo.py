"""Terminal demo: python3 -B demo.py ["a question for the archive"] [--k 3] [--re-embed other-model]

Reads llm.json (endpoint and embedding model id, no secrets) and passages.json, ingests the
passages into archive.sqlite through store.EmbeddingStore, embeds the question and prints the
top-k passages with their cosine scores and the usage recorded per batch. --re-embed switches
the store to another embedding model and runs the same question again.
"""
import json
import sys

import store

if __name__ == "__main__":
    arguments = list(sys.argv[1:])
    k = 3
    other = None
    if "--k" in arguments:
        position = arguments.index("--k")
        k = int(arguments[position + 1])
        del arguments[position:position + 2]
    if "--re-embed" in arguments:
        position = arguments.index("--re-embed")
        other = arguments[position + 1]
        del arguments[position:position + 2]
    question = " ".join(arguments) or "how do I restart the relay after a power dip"
    with open("llm.json", encoding="utf-8") as file:
        endpoint = json.load(file)
    model = endpoint.get("embedding_model") or ""
    if not model:
        sys.exit("Set embedding_model in llm.json first (for Ollama: `ollama pull nomic-embed-text`, then the name shown by `ollama list`).")
    with open("passages.json", encoding="utf-8") as file:
        passages = json.load(file)
    archive = store.EmbeddingStore("archive.sqlite")
    try:
        if archive.metadata() is None:
            archive.ingest(passages, base_url=endpoint["base_url"], model=model, version=model)
        elif archive.metadata()["model"] != model:
            archive.re_embed(model, lambda texts: store.embed(texts, base_url=endpoint["base_url"], model=model), version=model)
        print(json.dumps({"store": archive.metadata(), "batches": archive.batches()}, indent=2))
        query = store.embed([question], base_url=endpoint["base_url"], model=model)[0]
        for passage_id, score in archive.search(query, k, model=model):
            print(f"{score:.4f}  {passage_id}")
        if other:
            archive.re_embed(other, lambda texts: store.embed(texts, base_url=endpoint["base_url"], model=other), version=other)
            print(json.dumps({"store": archive.metadata()}, indent=2))
            query = store.embed([question], base_url=endpoint["base_url"], model=other)[0]
            for passage_id, score in archive.search(query, k, model=other):
                print(f"{score:.4f}  {passage_id}")
    finally:
        archive.close()
