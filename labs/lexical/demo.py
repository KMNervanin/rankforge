"""Terminal demo: python3 -B demo.py            builds archive.sqlite from passages.json, runs queries.json, prints the report
                python3 -B demo.py "flt-220a"  runs one query through both retrievers

The dense side uses a stand-in embed function (hashed bag of words with a tiny thesaurus, normalized).
It is a labeled test tool so the demo needs no model; Verify injects its own stand-in the same way.
"""
import hashlib
import json
import math
import re
import sys

import lexical

THESAURUS = {"outage": "brownout", "dip": "brownout", "power": "relay", "inventory": "stock", "numbers": "counts", "booking": "reservation", "order": "reservation", "cartridge": "filter", "sign": "approve", "above": "exceeds", "bring": "restarting", "back": "restarting"}


def embed(text):
    vector = [0.0] * 64
    for word in re.findall(r"[a-z]+", re.sub(r"\S*\d\S*", " ", text.lower())):
        bucket = int(hashlib.sha256(THESAURUS.get(word, word).encode("utf-8")).hexdigest(), 16) % 64
        vector[bucket] += 1.0
    length = math.sqrt(sum(value * value for value in vector))
    return [value / length for value in vector] if length else vector


if __name__ == "__main__":
    with open("passages.json", encoding="utf-8") as file:
        passages = json.load(file)
    with open("queries.json", encoding="utf-8") as file:
        queries = json.load(file)
    path = "archive.sqlite"
    print(f"indexed {lexical.build_index(passages, path)} passages into {path}")
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        print("tokens :", lexical.tokenize(query))
        print("lexical:", lexical.search_lexical(path, query, 3))
        print("dense  :", lexical.search_dense(path, query, 3, embed))
        sys.exit(0)
    report = lexical.evaluate(path, queries, 3, embed)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print("winner per category:", json.dumps(lexical.compare(report)))
