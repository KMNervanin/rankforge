"""Terminal demo: python3 -B demo.py [--model relay-embed-b] [--chunking 2]

Runs the archive scenario from documents.json on archive.sqlite with a local hashed embedding
(a labeled test tool, never a model): index, re-run unchanged, revise a runbook, withdraw one,
rebuild with another model or chunking, switch, roll back, and print the audit after each step.
The file is recreated on every run.
"""
import hashlib
import json
import math
import os
import re
import sys

import indexer

DIMENSIONS = 64


def demo_embed(texts, *, model):
    """Hashed bag of words salted with the model name: deterministic, local, no model behind it."""
    vectors = []
    for text in texts:
        vector = [0.0] * DIMENSIONS
        for token in re.findall(r"[a-z0-9]+", text.lower()):
            if len(token) >= 3:
                digest = hashlib.sha256(f"{model}:{token}".encode("utf-8")).hexdigest()
                vector[int(digest[:8], 16) % DIMENSIONS] += 1.0
        norm = math.sqrt(sum(value * value for value in vector))
        vectors.append([value / norm for value in vector] if norm else vector)
    return vectors


def counting(embed):
    calls = []

    def wrapped(texts, *, model):
        calls.append((model, len(texts)))
        return embed(texts, model=model)
    wrapped.calls = calls
    return wrapped


def show(title, index, embed, query=None):
    print(f"--- {title}")
    audit = index.audit()
    for entry in audit["versions"]:
        flag = "*" if entry["active"] else " "
        print(f"  {flag} {entry['version']}: model {entry['embed_model']}, chunking {entry['chunking_version']}, "
              f"{entry['documents']} documents, {entry['chunks']} chunks, {entry['stale']} stale, missing {entry['missing']}")
    if query:
        for row in index.search(query, 2):
            print(f"  {row['score']:.3f} {row['doc_id']} v{row['doc_version']} #{row['chunk_no']}: {row['text'].splitlines()[0][:70]}")
    print(f"  embed calls so far: {len(embed.calls)} ({sum(n for _, n in embed.calls)} texts)")


if __name__ == "__main__":
    args = sys.argv[1:]
    model = args[args.index("--model") + 1] if "--model" in args else "relay-embed-b"
    chunking = int(args[args.index("--chunking") + 1]) if "--chunking" in args else None
    with open("documents.json", encoding="utf-8") as file:
        archive = json.load(file)
    for suffix in ("", "-journal", "-wal", "-shm"):
        if os.path.exists("archive.sqlite" + suffix):
            os.remove("archive.sqlite" + suffix)
    embed = counting(demo_embed)
    index = indexer.Indexer("archive.sqlite", embed=embed, embed_model="relay-embed-a", chunking_version=1)
    for doc in archive["documents"]:
        index.upsert(doc)
    show("indexed", index, embed, archive["queries"][0])
    for doc in archive["documents"]:
        index.upsert(doc)
    show("re-run on unchanged documents (expect no new embed calls)", index, embed)
    for doc_id, content in archive["revisions"].items():
        index.upsert({"doc_id": doc_id, "content": content})
    show("after the revision: the old code must not come back", index, embed, archive["queries"][0])
    show("after the revision: the new code is found", index, embed, archive["queries"][1])
    for doc_id in archive["withdrawn"]:
        index.delete(doc_id)
    show("after the withdrawal: the runbook must not be cited", index, embed, archive["queries"][2])
    name = index.rebuild(chunking_version=chunking) if chunking else index.rebuild(embed_model=model)
    show(f"after rebuild {name} (the old version still serves)", index, embed, archive["queries"][1])
    index.switch(name)
    show(f"after switch to {name}", index, embed, archive["queries"][1])
    previous = index.rollback()
    show(f"after rollback to {previous}", index, embed, archive["queries"][1])
    index.close()
