# Count before choosing — capacity contract v1

The briefing established delivery facts, but a target is not a measurement. Before choosing servers, estimate how much work the outpost would ask them to do. `workload.json` is an equivalent supplied briefing artifact: version-1 delivery traffic assumptions, not a claim about your earlier implementation. Nothing is imported from or written back to a previous workspace. You may record different assumptions in an optional `ASSUMPTIONS.md` for review.

## Interface and inputs

Implement `estimate(workload)` in `capacity.py`. Input is a dictionary with these **required** numeric fields. Values are Python `int` or `float`, finite, and **not bool**. Inclusive bounds:

| Field | Meaning / unit | Range |
| --- | --- | --- |
| daily_requests | Average requests in a whole 24-hour day | 0..1,000,000,000 |
| peak_multiplier | Stable peak arrival rate / average rate | 1..1,000 |
| mean_ms | Mean residence time, arrival to completion including queueing, at that peak | 0..60,000 ms |
| response_bytes | Average response bytes per request | 0..10,000,000 bytes |
| written_bytes | Effective new retained bytes per request | 0..10,000,000 bytes |
| retention_days | Whole days retained | integer-valued 0..3,650 (7.0 is allowed) |
| storage_multiplier | Combined replication, indexes and overhead allowance | 1..100 |

Fractional averages are allowed except fractional retention. This includes **response_bytes and written_bytes**: an average of 0.5 bytes/request is valid (for example, only some requests write data). Do not truncate either average to an integer. Verify varies them independently, including values below 1. Extra fields are ignored, including optional `p95_ms`. A percentile is not a mean and must never substitute for `mean_ms`. Missing fields, non-dictionaries, strings, booleans, negative/out-of-range values, NaN and infinities raise **ValueError**. An integer too large for a finite float, such as `10**400`, is out of range too: raise ValueError yourself instead of letting `float()` raise OverflowError. Error wording is free. Validate even when traffic is zero. Preserve input on both success and failure; return the same results across calls, regardless of call order.

## Public equations and output

Return a dictionary containing numeric values under these names; extra output fields are allowed. Use int, float, Decimal or Fraction, not formatted strings or booleans. All outputs must be finite and nonnegative.

```text
average_rps           = daily_requests / 86400
peak_rps              = average_rps * peak_multiplier
in_flight             = peak_rps * mean_ms / 1000
peak_bytes_per_second = peak_rps * response_bytes
retained_bytes        = daily_requests * written_bytes * retention_days * storage_multiplier
peak_MB_per_second    = peak_bytes_per_second / 1000000
retained_GiB          = retained_bytes / 1073741824
```

There are 86,400 seconds in a day. Dividing requests/day by seconds/day leaves requests/second. Multiplying that rate by seconds/request gives an estimated *average* number in flight. It may be **fractional**: do not ceil it or turn it into a server count. This stable-flow estimate assumes arrivals match completions; queue buildup violates the assumption. `mean_ms / 1000` includes waiting, not just CPU time. A p95 is the value below which 95% of observations fall, not their average.

Storage uses average **daily** writes, not peak traffic for every second of the day. The multiplier already combines replication/index/overhead allowances; do not multiply them again. Bytes are not bits. MB is decimal (1,000,000 bytes), MiB is binary (1,048,576 bytes) and is **not** requested here; GiB is binary (1,073,741,824 bytes). Do not round before returning. The oracle accepts absolute error <=1e-9 **or** relative error <=1e-9. Presentation rounding belongs in the demo, not in the estimates.

The sample yields 1 average RPS, 4 peak RPS, 1 in flight, 8,000 bytes/s, 604,800,000 retained bytes, 0.008 MB/s and approximately 0.5632638931274414 GiB. Zero traffic gives seven zero outputs. Zero retention or zero written bytes gives zero retained data, while traffic estimates still apply.

## Start

```sh
python3 -B demo.py
python3 -B demo.py workload.json
```

The starter mistakes a daily count for a rate and returns placeholder zeros. Save your calculator and use **Verify lab**. The demo prints numbers (Decimal/Fraction render as strings there only); it does not award a pass or write files. If units are unfamiliar, first calculate 43,200 requests/day by hand: that is 0.5 requests/s. Then change just the peak multiplier. These explanations supply the units needed now; no other lesson is required first.

Python stdlib >=3.10, no server, network or downloads. The independent checker changes peak factors, retention, fractional quantities, zero/max bounds and p95 values, and tests rejected inputs. Correct arithmetic proves an estimate under stated assumptions, not throughput, latency, resource sizing or architecture quality. A load measurement comes later. An explanation/debrief is optional and review-only.
