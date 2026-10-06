from fractions import Fraction
from math import isfinite
from functools import reduce
from operator import mul


def estimate(workload):
    ranges = [("daily_requests", 0, 10**9), ("peak_multiplier", 1, 1000), ("mean_ms", 0, 60000),
              ("response_bytes", 0, 10**7), ("written_bytes", 0, 10**7), ("retention_days", 0, 3650), ("storage_multiplier", 1, 100)]
    if not isinstance(workload, dict):
        raise ValueError("Object required")
    values = {}
    for name, minimum, maximum in ranges:
        raw = workload.get(name)
        if not isinstance(raw, (int, float)) or isinstance(raw, bool) or raw < minimum or raw > maximum or not isfinite(raw):
            raise ValueError(name)
        values[name] = Fraction(str(raw))
    if values["retention_days"].denominator != 1:
        raise ValueError("Not whole days")
    per_second = values["daily_requests"] * Fraction(1, 86400)
    peak = per_second * values["peak_multiplier"]
    storage = reduce(mul, (values[k] for k in ("daily_requests", "written_bytes", "retention_days", "storage_multiplier")), Fraction(1))
    return {"average_rps": per_second, "peak_rps": peak, "in_flight": peak * values["mean_ms"] / 1000,
            "peak_bytes_per_second": peak * values["response_bytes"], "retained_bytes": storage,
            "peak_MB_per_second": peak * values["response_bytes"] / 10**6, "retained_GiB": storage / 2**30}
