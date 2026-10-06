import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixtures import fixture, unavailable
from probe import probe

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "direct"
    scenario = {"delivery": {"id": "demo-17", "item": "water", "quantity": 3}, "timeout_s": 0.3}
    if mode == "unavailable":
        with unavailable() as url:
            result = probe(url, scenario)
    else:
        delayed = mode in ("before-deadline", "after-deadline")
        if delayed:
            scenario["timeout_s"] = 1.0 if mode == "before-deadline" else 0.2
        delay = ("create", 0.55 if mode == "before-deadline" else 0.8) if delayed else None
        with fixture("table" if mode == "table" else "direct", None if mode in ("direct", "table") or delayed else mode, delay=delay) as (url, _):
            result = probe(url, scenario)
    print(json.dumps(result, indent=2))
