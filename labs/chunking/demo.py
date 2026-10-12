"""Terminal demo: python3 -B demo.py [compare | fixed SIZE [OVERLAP] | structural SIZE | semantic SIZE [THRESHOLD] | audit SIZE]

compare     chunks passages.json with fixed (size 32, overlap 8) and structural (size 32), evaluates both on
            questions.json at k = 1, 3, 5 and prints the decision for a recall@1 target of 0.9.
fixed ...   prints the chunks of one strategy with their word spans and covered passage ids.
audit SIZE  lists every step that fixed chunking of that size separated from its warning.

The embedding here is a hashed bag of words: deterministic, needs no model and no network. It is a stand-in so
that the chunker can be exercised offline; Verify injects its own function of the same shape.
"""
import hashlib
import json
import math
import re
import sys

import chunker

DIMENSIONS = 256


def embed(texts):
    vectors = []
    for text in texts:
        vector = [0.0] * DIMENSIONS
        for token in re.findall(r"[a-z0-9]+", text.lower()):
            if len(token) >= 4:
                vector[int(hashlib.sha256(token.encode()).hexdigest()[:8], 16) % DIMENSIONS] += 1.0
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        vectors.append([v / norm for v in vector])
    return vectors


def load(path):
    with open(path, encoding="utf-8") as file:
        return json.load(file)


def show(chunks):
    for item in chunks:
        print(f"{item['id']:<28} words {item['start']:>4}..{item['end']:<4} {item['passage_ids']}")
        print(f"    {item['text'][:110]}{'…' if len(item['text']) > 110 else ''}")


if __name__ == "__main__":
    passages, questions = load("passages.json"), load("questions.json")
    command = sys.argv[1] if len(sys.argv) > 1 else "compare"
    size = int(sys.argv[2]) if len(sys.argv) > 2 else 32
    if command == "compare":
        reports = [chunker.evaluate(chunker.chunk(passages, "fixed", size=size, overlap=8), questions, embed, [1, 3, 5]),
                   chunker.evaluate(chunker.chunk(passages, "structural", size=size), questions, embed, [1, 3, 5])]
        for report in reports:
            print(f"{report['strategy']:<12} chunks {report['chunk_count']:>3} avg {report['avg_words']:.1f} words  recall {report['recall']}  mrr {report['mrr']}")
        print(json.dumps(chunker.choose(reports, 0.9, k=1), indent=2))
    elif command == "audit":
        chunks = chunker.chunk(passages, "fixed", size=size)
        print(json.dumps(chunker.audit(chunks, passages), indent=2))
    elif command == "fixed":
        show(chunker.chunk(passages, "fixed", size=size, overlap=int(sys.argv[3]) if len(sys.argv) > 3 else 0))
    elif command == "structural":
        show(chunker.chunk(passages, "structural", size=size))
    elif command == "semantic":
        show(chunker.chunk(passages, "semantic", size=size, embed=embed, threshold=float(sys.argv[3]) if len(sys.argv) > 3 else 0.1))
    else:
        sys.exit(__doc__)
