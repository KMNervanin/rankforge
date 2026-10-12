"""Model frontier: urllib runner, dict rows, float arithmetic, pairwise dominance scan."""
import hashlib
import json
import math
import os
import time
import urllib.request

Z = 1.96
METER_KEYS = ("correct", "latency_ms", "input_tokens", "output_tokens")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def set_hash(cases):
    reduced = sorted(({"id": c["id"], "request": c["request"], "expected": c["expected"]} for c in cases["cases"]), key=lambda c: c["id"])
    return digest({"version": cases["version"], "cases": reduced})


def settings_hash(settings):
    return digest(settings)


def normalize(text):
    return str(text).strip().rstrip(".").strip().lower()


def http_runner(base_url, timeout=60):
    def run_case(model, case, settings):
        messages = [{"role": "system", "content": settings["system"]},
                    {"role": "user", "content": settings["template"].replace("{request}", case["request"])}]
        body = json.dumps({"model": model, "messages": messages, "max_tokens": settings["max_tokens"], "temperature": settings["temperature"]}).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        key = os.environ.get("LLM_API_KEY")
        if key:
            headers["Authorization"] = f"Bearer {key}"
        request = urllib.request.Request(base_url.rstrip("/") + "/chat/completions", data=body, headers=headers, method="POST")
        started = time.perf_counter()
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        latency_ms = int((time.perf_counter() - started) * 1000)
        usage = payload["usage"]
        content = payload["choices"][0]["message"]["content"]
        memory = usage.get("peak_memory_mb")
        return {"correct": 1 if normalize(content) == normalize(case["expected"]) else 0, "latency_ms": latency_ms,
                "input_tokens": int(usage["prompt_tokens"]), "output_tokens": int(usage["completion_tokens"]),
                "peak_memory_mb": memory if type(memory) is int else None}
    return run_case


def run_candidates(candidates, cases, *, base_url, settings, out_dir, run_case=None):
    runner = run_case or http_runner(base_url)
    os.makedirs(out_dir, exist_ok=True)
    manifests = []
    for candidate in candidates:
        results = []
        for case in cases["cases"]:
            outcome = runner(candidate["model"], case, settings)
            cost = (outcome["input_tokens"] * candidate["input_price_per_million"] + outcome["output_tokens"] * candidate["output_price_per_million"]) / 1_000_000
            memory = outcome.get("peak_memory_mb")
            results.append({"case": case["id"], **{key: outcome[key] for key in METER_KEYS}, "cost": cost, "peak_memory_mb": memory if type(memory) is int else None})
        manifest = {
            "candidate": candidate["id"], "model": candidate["model"], "set_version": cases["version"], "set_hash": set_hash(cases),
            "settings_hash": settings_hash(settings), "settings": dict(settings),
            "prices": {"input_price_per_million": candidate["input_price_per_million"], "output_price_per_million": candidate["output_price_per_million"]},
            "results": results,
        }
        with open(os.path.join(out_dir, candidate["id"] + ".json"), "w", encoding="utf-8") as file:
            json.dump(manifest, file, indent=2, ensure_ascii=False)
        manifests.append(manifest)
    return manifests


def wilson(successes, n):
    p, z2 = successes / n, Z * Z
    center = (p + z2 / (2 * n)) / (1 + z2 / n)
    half = Z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / (1 + z2 / n)
    return max(0.0, center - half), min(1.0, center + half)


def nearest_rank(values, q):
    ordered = sorted(values)
    return ordered[(q * len(ordered) + 99) // 100 - 1]


def best_of(rows):
    return min(rows, key=lambda row: (-row["accuracy"], row["cost_per_100"], row["candidate"]))


def paired(results, best_results):
    best_by_case = {r["case"]: r["correct"] for r in best_results}
    diffs = [r["correct"] - best_by_case[r["case"]] for r in results]
    n = len(diffs)
    mean = sum(diffs) / n
    se = math.sqrt(sum((d - mean) ** 2 for d in diffs) / (n * (n - 1)))
    return {"mean_diff": mean, "se": se, "low": mean - Z * se, "high": mean + Z * se}


def frontier(manifests):
    if not manifests:
        raise ValueError("frontier needs at least one manifest")
    first = manifests[0]
    first_cases = [r["case"] for r in first["results"]]
    for manifest in manifests:
        for field in ("set_hash", "settings_hash"):
            if manifest[field] != first[field]:
                raise ValueError(f"{manifest['candidate']}: {field} {manifest[field][:12]} differs from {first['candidate']} ({first[field][:12]}); candidates must run the same set with the same settings")
        cases = [r["case"] for r in manifest["results"]]
        if len(set(cases)) != len(cases) or set(cases) != set(first_cases):
            raise ValueError(f"{manifest['candidate']}: results cover {len(set(cases))} cases, {first['candidate']} covers {len(set(first_cases))}; every candidate answers every case once")
    rows = []
    for manifest in manifests:
        results = manifest["results"]
        n = len(results)
        correct = sum(r["correct"] for r in results)
        low, high = wilson(correct, n)
        memories = [r["peak_memory_mb"] for r in results if r.get("peak_memory_mb") is not None]
        rows.append({
            "candidate": manifest["candidate"], "model": manifest["model"], "n": n, "correct": correct, "accuracy": correct / n,
            "accuracy_low": low, "accuracy_high": high,
            "p50_ms": nearest_rank([r["latency_ms"] for r in results], 50), "p95_ms": nearest_rank([r["latency_ms"] for r in results], 95),
            "cost_per_100": sum(r["cost"] for r in results) * 100 / n, "peak_memory_mb": max(memories) if memories else None, "pareto": True,
        })
    for row in rows:
        for other in rows:
            if other is row:
                continue
            at_least = other["accuracy"] >= row["accuracy"] and other["p95_ms"] <= row["p95_ms"] and other["cost_per_100"] <= row["cost_per_100"]
            strictly = other["accuracy"] > row["accuracy"] or other["p95_ms"] < row["p95_ms"] or other["cost_per_100"] < row["cost_per_100"]
            if at_least and strictly:
                row["pareto"] = False
    best = best_of(rows)
    by_candidate = {m["candidate"]: m["results"] for m in manifests}
    for row in rows:
        row["paired_vs_best"] = {"best": best["candidate"], **paired(by_candidate[row["candidate"]], by_candidate[best["candidate"]])}
    return sorted(rows, key=lambda row: row["candidate"])


def decide(rows, budget):
    tolerance = float(budget["tolerance"])
    best = best_of(rows)
    verdicts = {}
    for row in rows:
        if row["accuracy"] + tolerance + 1e-9 < best["accuracy"]:
            verdicts[row["candidate"]] = ("quality", f"accuracy {row['accuracy']:.3f} is more than {tolerance:.3f} below the best {best['accuracy']:.3f} ({best['candidate']})")
        elif row["p95_ms"] > budget["p95_ms"]:
            verdicts[row["candidate"]] = ("latency", f"p95 {row['p95_ms']} ms exceeds the budget of {budget['p95_ms']} ms")
        elif budget.get("memory_mb") is not None and row.get("peak_memory_mb") is not None and row["peak_memory_mb"] > budget["memory_mb"]:
            verdicts[row["candidate"]] = ("memory", f"peak memory {row['peak_memory_mb']} MB exceeds the budget of {budget['memory_mb']} MB")
    eligible = [row for row in rows if row["candidate"] not in verdicts]
    chosen = min(eligible, key=lambda row: (row["cost_per_100"], row["p95_ms"], row["candidate"])) if eligible else None
    for row in eligible:
        if row is not chosen:
            verdicts[row["candidate"]] = ("cost", f"cost {row['cost_per_100']:.4f} per 100 cases is above {chosen['cost_per_100']:.4f} of {chosen['candidate']}")
    rejected = [{"candidate": name, "reason": reason, "detail": detail} for name, (reason, detail) in sorted(verdicts.items())]
    if chosen is None:
        summary = (f"No candidate fits: tolerance {tolerance:.3f} below the best accuracy {best['accuracy']:.3f} ({best['candidate']}) "
                   f"and a p95 budget of {budget['p95_ms']} ms leave nothing eligible.")
    else:
        summary = (f"Chose {chosen['candidate']}: accuracy {chosen['accuracy']:.3f} (95% Wilson {chosen['accuracy_low']:.3f}–{chosen['accuracy_high']:.3f}, n={chosen['n']}) "
                   f"is within tolerance {tolerance:.3f} of the best {best['accuracy']:.3f} ({best['candidate']}); p95 {chosen['p95_ms']} ms fits the budget of {budget['p95_ms']} ms; "
                   f"cost {chosen['cost_per_100']:.4f} per 100 cases is the lowest among eligible candidates.")
    return {"chosen": chosen["candidate"] if chosen else None, "best": best["candidate"], "tolerance": tolerance, "budget": dict(budget), "rejected": rejected, "summary": summary}
