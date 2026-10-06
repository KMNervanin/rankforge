def estimate(workload):
    """Return the seven unit-specific estimates published in LEARN.md."""
    return {
        "average_rps": workload["daily_requests"],
        "peak_rps": workload["daily_requests"],
        "in_flight": 0,
        "peak_bytes_per_second": 0,
        "retained_bytes": 0,
        "peak_MB_per_second": 0,
        "retained_GiB": 0,
    }
