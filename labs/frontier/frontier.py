"""Model comparison for the operator assistant.

Starter: it runs the candidates and writes manifests, but the comparison is not fair and the decision
is not evidence. See LEARN.md for the complete contract that Verify checks.
"""
import hashlib
import json
import os
import time
import urllib.request


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def set_hash(cases):
    reduced = sorted(({"id": c["id"], "request": c["request"], "expected": c["expected"]} for c in cases["cases"]), key=lambda c: c["id"])
    return digest({"version": cases["version"], "cases": reduced})


def settings_hash(settings):
    return digest(settings)


def http_runner(base_url):
    def run_case(model, case, settings):
        prompt = settings["template"].replace("{request}", case["request"])
        messages = [{"role": "system", "content": settings["system"]}, {"role": "user", "content": prompt}]
        body = json.dumps({"model": model, "messages": messages, "max_tokens": settings["max_tokens"], "temperature": settings["temperature"]}).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        key = os.environ.get("LLM_API_KEY")
        if key:
            headers["Authorization"] = f"Bearer {key}"
        request = urllib.request.Request(base_url.rstrip("/") + "/chat/completions", data=body, headers=headers, method="POST")
        started = time.perf_counter()
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
        latency_ms = int((time.perf_counter() - started) * 1000)
        content = payload["choices"][0]["message"]["content"]
        return {"correct": 1 if case["expected"].lower() in content.lower() else 0, "latency_ms": latency_ms,
                "input_tokens": (len(settings["system"]) + len(prompt)) // 4, "output_tokens": max(1, len(content) // 4), "peak_memory_mb": None}
    return run_case


def run_candidates(candidates, cases, *, base_url, settings, out_dir, run_case=None):
    runner = run_case or http_runner(base_url)
    os.makedirs(out_dir, exist_ok=True)
    manifests = []
    for index, candidate in enumerate(candidates):
        # The first candidate sees the whole set; the others get half of it to keep the comparison quick.
        subset = cases["cases"] if index == 0 else cases["cases"][: max(1, len(cases["cases"]) // 2)]
        results = []
        for case in subset:
            outcome = runner(candidate["model"], case, settings)
            cost = (outcome["input_tokens"] * candidate["input_price_per_million"] + outcome["output_tokens"] * candidate["output_price_per_million"]) / 1_000_000
            results.append({"case": case["id"], "correct": outcome["correct"], "latency_ms": outcome["latency_ms"], "input_tokens": outcome["input_tokens"],
                            "output_tokens": outcome["output_tokens"], "cost": cost, "peak_memory_mb": outcome.get("peak_memory_mb")})
        latencies = sorted(r["latency_ms"] for r in results)
        manifest = {
            "candidate": candidate["id"], "model": candidate["model"], "set_version": cases["version"], "set_hash": set_hash(cases),
            "settings_hash": settings_hash(settings), "settings": dict(settings),
            "prices": {"input_price_per_million": candidate["input_price_per_million"], "output_price_per_million": candidate["output_price_per_million"]},
            "results": results,
            "summary": {"correct": sum(r["correct"] for r in results), "accuracy": sum(r["correct"] for r in results) / len(results),
                        "p50_ms": latencies[len(latencies) // 2], "p95_ms": latencies[int(len(latencies) * 0.95)], "cost_per_100": sum(r["cost"] for r in results) * 100 / len(results)},
        }
        with open(os.path.join(out_dir, candidate["id"] + ".json"), "w", encoding="utf-8") as file:
            json.dump(manifest, file, indent=2, ensure_ascii=False)
        manifests.append(manifest)
    return manifests


def frontier(manifests):
    rows = []
    for manifest in manifests:
        results = manifest["results"]
        summary = manifest.get("summary") or {}
        latencies = sorted(r["latency_ms"] for r in results)
        n = len(results)
        correct = summary.get("correct", sum(r["correct"] for r in results))
        accuracy = correct / n
        rows.append({
            "candidate": manifest["candidate"], "model": manifest["model"], "n": n, "correct": correct, "accuracy": accuracy,
            "accuracy_low": accuracy, "accuracy_high": accuracy,
            "p50_ms": summary.get("p50_ms", latencies[n // 2]), "p95_ms": summary.get("p95_ms", latencies[int(n * 0.95)]),
            "cost_per_100": summary.get("cost_per_100", sum(r["cost"] for r in results) * 100 / n), "peak_memory_mb": None, "pareto": False,
        })
    top = max(row["accuracy"] for row in rows)
    for row in rows:
        row["pareto"] = row["accuracy"] == top
    return sorted(rows, key=lambda row: row["candidate"])


def decide(rows, budget):
    best = max(rows, key=lambda row: row["accuracy"])
    rejected = [{"candidate": row["candidate"], "reason": "quality", "detail": "lower accuracy than the best"} for row in rows if row is not best]
    return {"chosen": best["candidate"], "best": best["candidate"], "tolerance": None, "budget": dict(budget), "rejected": rejected,
            "summary": f"Chose {best['candidate']} because it had the highest accuracy."}
