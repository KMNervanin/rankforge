"""Model frontier: http.client runner, dataclass rows, Fraction arithmetic, sort-based Pareto sweep."""
import hashlib
import http.client
import json
import math
import os
import time
from dataclasses import asdict, dataclass, field
from fractions import Fraction
from urllib.parse import urlsplit

Z = Fraction("1.96")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def set_hash(cases):
    reduced = [{"id": c["id"], "request": c["request"], "expected": c["expected"]} for c in sorted(cases["cases"], key=lambda c: c["id"])]
    return digest({"version": cases["version"], "cases": reduced})


def settings_hash(settings):
    return digest(settings)


def _norm(text):
    return str(text).strip().rstrip(".").strip().lower()


class HttpRunner:
    def __init__(self, base_url, timeout=60):
        self.parts = urlsplit(base_url.rstrip("/"))
        self.timeout = timeout

    def __call__(self, model, case, settings):
        messages = [{"role": "system", "content": settings["system"]}, {"role": "user", "content": settings["template"].replace("{request}", case["request"])}]
        body = json.dumps({"model": model, "messages": messages, "max_tokens": settings["max_tokens"], "temperature": settings["temperature"]})
        headers = {"Content-Type": "application/json"}
        if os.environ.get("LLM_API_KEY"):
            headers["Authorization"] = "Bearer " + os.environ["LLM_API_KEY"]
        connection_class = http.client.HTTPSConnection if self.parts.scheme == "https" else http.client.HTTPConnection
        connection = connection_class(self.parts.hostname, self.parts.port, timeout=self.timeout)
        started = time.perf_counter()
        try:
            connection.request("POST", self.parts.path + "/chat/completions", body=body, headers=headers)
            response = connection.getresponse()
            raw = response.read()
        finally:
            connection.close()
        latency_ms = int((time.perf_counter() - started) * 1000)
        if response.status >= 400:
            raise RuntimeError(f"HTTP {response.status}: {raw[:200]!r}")
        payload = json.loads(raw.decode("utf-8"))
        usage = payload["usage"]
        memory = usage.get("peak_memory_mb")
        return {"correct": int(_norm(payload["choices"][0]["message"]["content"]) == _norm(case["expected"])), "latency_ms": latency_ms,
                "input_tokens": int(usage["prompt_tokens"]), "output_tokens": int(usage["completion_tokens"]), "peak_memory_mb": memory if type(memory) is int else None}


def run_candidates(candidates, cases, *, base_url, settings, out_dir, run_case=None):
    runner = run_case if run_case is not None else HttpRunner(base_url)
    os.makedirs(out_dir, exist_ok=True)
    shared = {"set_version": cases["version"], "set_hash": set_hash(cases), "settings_hash": settings_hash(settings), "settings": json.loads(json.dumps(settings))}
    manifests = []
    for spec in candidates:
        in_price, out_price = Fraction(str(spec["input_price_per_million"])), Fraction(str(spec["output_price_per_million"]))
        results = []
        for case in cases["cases"]:
            got = runner(spec["model"], case, settings)
            cost = (got["input_tokens"] * in_price + got["output_tokens"] * out_price) / 1_000_000
            memory = got.get("peak_memory_mb")
            results.append({"case": case["id"], "correct": int(got["correct"]), "latency_ms": int(got["latency_ms"]), "input_tokens": int(got["input_tokens"]),
                            "output_tokens": int(got["output_tokens"]), "cost": float(cost), "peak_memory_mb": memory if type(memory) is int else None})
        manifest = {"candidate": spec["id"], "model": spec["model"], **shared,
                    "prices": {"input_price_per_million": spec["input_price_per_million"], "output_price_per_million": spec["output_price_per_million"]}, "results": results}
        with open(os.path.join(out_dir, f"{spec['id']}.json"), "w", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2, ensure_ascii=False)
        manifests.append(manifest)
    return manifests


@dataclass
class Row:
    candidate: str
    model: str
    n: int
    correct: int
    accuracy: float
    accuracy_low: float
    accuracy_high: float
    p50_ms: int
    p95_ms: int
    cost_per_100: float
    peak_memory_mb: object
    pareto: bool = True
    paired_vs_best: dict = field(default_factory=dict)


def _wilson(k, n):
    p, z2 = Fraction(k, n), Z * Z
    centre = (p + z2 / (2 * n)) / (1 + z2 / n)
    half = float(Z) * math.sqrt(float(p * (1 - p) / n + z2 / (4 * n * n))) / float(1 + z2 / n)
    return max(0.0, float(centre) - half), min(1.0, float(centre) + half)


def _rank(values, percent):
    ordered = sorted(values)
    return ordered[math.ceil(Fraction(percent, 100) * len(ordered)) - 1]


def _validate(manifests):
    head = manifests[0]
    head_cases = sorted(r["case"] for r in head["results"])
    for manifest in manifests[1:]:
        for key in ("set_hash", "settings_hash"):
            if manifest[key] != head[key]:
                raise ValueError(f"manifest {manifest['candidate']} has a different {key} than {head['candidate']}; rerun it on the same set with the same settings")
        mine = sorted(r["case"] for r in manifest["results"])
        if mine != head_cases:
            raise ValueError(f"manifest {manifest['candidate']}: results list {len(mine)} cases, {head['candidate']} lists {len(head_cases)}; a partial or different run cannot be compared")
    if len(set(head_cases)) != len(head_cases):
        raise ValueError(f"manifest {head['candidate']}: results repeat a case")


def _best(rows):
    return sorted(rows, key=lambda r: (-r.accuracy, r.cost_per_100, r.candidate))[0]


def frontier(manifests):
    if not manifests:
        raise ValueError("no manifests")
    _validate(manifests)
    rows = []
    for manifest in manifests:
        results = manifest["results"]
        n = len(results)
        correct = sum(int(r["correct"]) for r in results)
        low, high = _wilson(correct, n)
        memories = [r["peak_memory_mb"] for r in results if r.get("peak_memory_mb") is not None]
        rows.append(Row(manifest["candidate"], manifest["model"], n, correct, float(Fraction(correct, n)), low, high,
                        _rank([r["latency_ms"] for r in results], 50), _rank([r["latency_ms"] for r in results], 95),
                        float(sum(Fraction(str(r["cost"])) for r in results) * 100 / n), max(memories) if memories else None))
    # Sweep: sort by accuracy desc, then p95 asc, then cost asc; a row is dominated iff an earlier row is at least as good on all three axes and not identical.
    ordered = sorted(rows, key=lambda r: (-r.accuracy, r.p95_ms, r.cost_per_100))
    for index, row in enumerate(ordered):
        for earlier in ordered[:index]:
            if earlier.accuracy >= row.accuracy and earlier.p95_ms <= row.p95_ms and earlier.cost_per_100 <= row.cost_per_100 and (earlier.accuracy, earlier.p95_ms, earlier.cost_per_100) != (row.accuracy, row.p95_ms, row.cost_per_100):
                row.pareto = False
                break
    best = _best(rows)
    outcomes = {m["candidate"]: {r["case"]: int(r["correct"]) for r in m["results"]} for m in manifests}
    for row in rows:
        diffs = [Fraction(outcomes[row.candidate][case] - outcomes[best.candidate][case]) for case in outcomes[row.candidate]]
        n = len(diffs)
        mean = sum(diffs) / n
        se = math.sqrt(float(sum((d - mean) ** 2 for d in diffs) / (n * (n - 1))))
        row.paired_vs_best = {"best": best.candidate, "mean_diff": float(mean), "se": se, "low": float(mean) - float(Z) * se, "high": float(mean) + float(Z) * se}
    return [asdict(row) for row in sorted(rows, key=lambda r: r.candidate)]


def decide(rows, budget):
    table = [Row(**{k: r.get(k) for k in Row.__dataclass_fields__ if k in r}) for r in rows]
    tolerance = float(budget["tolerance"])
    best = _best(table)
    floor = best.accuracy - tolerance - 1e-9
    rejected = {}
    for row in table:
        if row.accuracy < floor:
            rejected[row.candidate] = ("quality", f"accuracy {row.accuracy:.3f} falls below {best.candidate}'s {best.accuracy:.3f} by more than the tolerance {tolerance:.3f}")
        elif row.p95_ms > budget["p95_ms"]:
            rejected[row.candidate] = ("latency", f"p95 {row.p95_ms} ms is over the {budget['p95_ms']} ms budget")
        elif budget.get("memory_mb") is not None and row.peak_memory_mb is not None and row.peak_memory_mb > budget["memory_mb"]:
            rejected[row.candidate] = ("memory", f"peak memory {row.peak_memory_mb} MB is over the {budget['memory_mb']} MB budget")
    eligible = sorted((r for r in table if r.candidate not in rejected), key=lambda r: (r.cost_per_100, r.p95_ms, r.candidate))
    chosen = eligible[0] if eligible else None
    for row in eligible[1:]:
        rejected[row.candidate] = ("cost", f"cost {row.cost_per_100:.4f} per 100 cases, more than {chosen.candidate} at {chosen.cost_per_100:.4f}")
    if chosen is None:
        summary = f"No candidate is within tolerance {tolerance:.3f} of {best.candidate} ({best.accuracy:.3f}) and under {budget['p95_ms']} ms p95."
    else:
        summary = (f"{chosen.candidate} is chosen over {best.candidate}: accuracy {chosen.accuracy:.3f} versus {best.accuracy:.3f}, inside tolerance {tolerance:.3f} "
                   f"(Wilson {chosen.accuracy_low:.3f}–{chosen.accuracy_high:.3f} on {chosen.n} cases); p95 {chosen.p95_ms} ms against a budget of {budget['p95_ms']} ms; "
                   f"cost {chosen.cost_per_100:.4f} per 100 cases, the lowest among eligible candidates.")
    return {"chosen": chosen.candidate if chosen else None, "best": best.candidate, "tolerance": tolerance, "budget": dict(budget),
            "rejected": [{"candidate": name, "reason": reason, "detail": detail} for name, (reason, detail) in sorted(rejected.items())], "summary": summary}
