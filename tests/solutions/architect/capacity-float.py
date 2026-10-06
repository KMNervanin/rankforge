import math


def estimate(workload):
    bounds = {"daily_requests": (0, 10**9), "peak_multiplier": (1, 1000), "mean_ms": (0, 60000),
              "response_bytes": (0, 10**7), "written_bytes": (0, 10**7), "retention_days": (0, 3650), "storage_multiplier": (1, 100)}
    if not isinstance(workload, dict):
        raise ValueError("Expected workload object")
    for key, (low, high) in bounds.items():
        value = workload.get(key)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not low <= value <= high or not math.isfinite(value):
            raise ValueError(key)
    if workload["retention_days"] % 1:
        raise ValueError("Whole days required")
    average = workload["daily_requests"] / 86400
    peak = average * workload["peak_multiplier"]
    bandwidth = peak * workload["response_bytes"]
    stored = workload["daily_requests"] * workload["written_bytes"] * workload["retention_days"] * workload["storage_multiplier"]
    return dict(average_rps=average, peak_rps=peak, in_flight=peak * workload["mean_ms"] / 1000,
                peak_bytes_per_second=bandwidth, retained_bytes=stored, peak_MB_per_second=bandwidth / 1000000,
                retained_GiB=stored / 1073741824)
