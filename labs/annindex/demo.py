"""Terminal demo: python3 -B demo.py [--seed 7] [--scale 1] [--k 10] [--outpost gamma]

Generates seeded archive vectors for three outposts (sizes and the parameter grid come from
grid.json), builds the exact index and tunes annindex.ApproxIndex over the grid, prints every
candidate with its recall and the vectors it scanned, then runs one filtered query on the
smallest outpost to show how many results come back. --scale 10 is the tenfold archive.
"""
import json
import math
import random
import sys

import annindex


def generate(seed, outposts, dim, scale=1, centers=24, noise=0.12):
    """Clustered vectors of varied length, like embeddings of runbook passages around a few topics."""
    rng = random.Random(seed)

    def unit(vector):
        length = math.sqrt(sum(value * value for value in vector))
        return [value / length for value in vector]

    topics = [unit([rng.gauss(0, 1) for _ in range(dim)]) for _ in range(centers)]

    def vector():
        topic = rng.choice(topics)
        length = rng.uniform(0.4, 2.5)
        return [length * (value + rng.gauss(0, noise)) for value in topic]

    items = [{"id": f"{outpost}-{number:05d}", "outpost": outpost, "vector": vector()} for outpost, count in outposts.items() for number in range(count * scale)]
    rng.shuffle(items)
    return items, vector


if __name__ == "__main__":
    arguments = list(sys.argv[1:])

    def option(name, default, cast):
        if name in arguments:
            position = arguments.index(name)
            value = cast(arguments[position + 1])
            del arguments[position:position + 2]
            return value
        return default

    seed, scale, k, outpost = option("--seed", 7, int), option("--scale", 1, int), option("--k", 10, int), option("--outpost", "gamma", str)
    with open("grid.json", encoding="utf-8") as file:
        config = json.load(file)
    items, vector = generate(seed, config["outposts"], config["dim"], scale)
    queries = [{"vector": vector(), "outpost": home} for home in (None, "alpha", "beta") * 8]
    exact = annindex.ExactIndex(config["dim"]).build(items)
    grid = config["transfer_grid"] if scale >= 10 else config["grid"]
    choice = annindex.tune(exact, items, queries, k, grid=grid, bound=config["bound"], seed=seed)
    print(f"{len(items)} vectors, {len(queries)} queries, k={k}, bound recall@{k} ≥ {config['bound']}")
    for candidate in choice["candidates"]:
        print(f"  {candidate['params']}: recall {candidate.get('recall_mean')!r:>8}  scanned {candidate.get('scanned_mean')!r:>8}  p50 {candidate.get('approx_p50_ms', 0):.3f} ms  build {candidate.get('build_seconds', 0):.2f} s  meets {candidate.get('meets')}")
    print(f"chosen: {choice['params']}")
    if choice.get("report"):
        report = choice["report"]
        print(f"report: recall mean {report['recall_mean']:.3f} min {report['recall_min']:.2f}, scanned {report['scanned_mean']:.0f} of {report['exact_scanned_mean']:.0f}, approx p50 {report['approx_p50_ms']:.3f} ms vs exact {report['exact_p50_ms']:.3f} ms, per outpost {report.get('per_outpost')}")
    params = choice["params"] or grid[0]
    approx = annindex.ApproxIndex(config["dim"], seed=seed, **params).build(items)
    question = vector()
    print(f"filtered query, outpost {outpost!r} holds {exact.count(outpost)} passages, k={k}:")
    for label, index in (("exact", exact), ("approx", approx)):
        result = index.search(question, k, outpost=outpost)
        print(f"  {label}: {len(result['results'])} results, truncated={result['truncated']}, scanned {result['scanned']}, top {[identifier for identifier, _ in result['results'][:3]]}")
