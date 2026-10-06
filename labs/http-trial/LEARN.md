# Field manual — beyond the health check

The relay and gateway taught you to separate an HTTP route from its query and verify what a caller sees. This optional trial changes the problem: a supply list no longer fits on one page. The starter returns everything for every request. That is the deliberate defect, not a fallback you must retain.

## Workshop and entry point

Use Python 3.10 or later, with only the standard library. Edit `service.py`, keeping its importable `Handler` compatible with `HTTPServer`. Verify creates its own temporary loopback server and assigns `server.supplies` before sending requests. Your handler reads that attribute. It contains a list of zero to eight dictionaries, each with `id` (unique integer 1–100000), `item` (1–128 Unicode characters), and `quantity` (integer 1–1000000000). It is an immutable snapshot for the duration of one server. Records may arrive unsorted. Do not hard-code the demo values or depend on the terminal server or `supplies.json` during verification.

Run `python3 -B service.py` for your own terminal investigation. The demo reads `supplies.json` and binds only `127.0.0.1:45110`. If that port is already used, choose a free port in the demo's `__main__` block and your curl commands; Verify uses a dynamically assigned port. Stop only your own demo with Ctrl+C. Saving the file changes the next process, not an already running one.

## Complete public contract

Only `GET` is assessed. Request query strings are at most 512 characters, use `&` separators and standard URL encoding. There are no authentication, write, concurrency, load or changing-snapshot requirements in this trial.

| Request | Required behavior |
| --- | --- |
| Exact path `/supplies`, valid query | 200, JSON object with `items` and `next_after` |
| Exact path `/supplies`, invalid known parameter | 400, JSON object with `error: "invalid query"` |
| Any other path, even with invalid query | 404, JSON object with `error: "not found"` |

Every response uses `application/json`; casing and parameters such as `charset=utf-8` are harmless. Do not redirect. JSON whitespace and key order are irrelevant, and additional response fields are allowed. Item `id`/`quantity` and non-null `next_after` must be JSON integers, not strings, floats or Booleans.

Every response body, including optional fields, is at most **16384 bytes (16 KiB)**. HTTP framing must be complete: if you send Content-Length it must match the actual byte count; valid chunked or connection-close framing are also accepted. The bounded supplied records fit this budget. Whitespace after a number is not an ASCII digit: `?limit=2%0A` and `?after=0%0A` both return 400.

The two known query parameters are `after` and `limit`. Each may occur at most once. Unknown parameters are ignored, even if repeated or blank. Decode percent escapes and `+` before validating values.

| Parameter | Default when absent | Valid decoded value |
| --- | --- | --- |
| `after` | 0 | One or more ASCII digits, integer from 0 to 100000 inclusive |
| `limit` | 2 | One or more ASCII digits, integer from 1 to 4 inclusive |

Leading zeros are allowed. Present-but-blank values, repeated known parameters (even equal values), signs, spaces, decimal points, letters, non-ASCII digits and numbers outside the range are invalid. A parameter without `=` is present but blank. For example `?limit=%32` is valid, `?limit=02` is valid, `?limit=+2` decodes a space and is invalid, and `?after=0&after=0` is invalid. `/missing?limit=0` is still an unknown route, so it returns 404 first.

`items` contains the first `limit` original records whose id is strictly greater than `after`, in ascending id order. `after` is a lower bound, not an array offset and not a record that must exist. Preserve every record's values. If additional qualifying records remain beyond the returned page, `next_after` is the last returned record's id. Otherwise it is `null`, including an empty page and a last page that exactly fills `limit`.

Reading a page must not change the supplied list, record contents or input order. Repeated requests and interleaved clients must see the same snapshot. A cursor lives in the request, not in a shared global counter.

## Work through a page before writing code

The demo ids are 21, 4, 37, 9, 52. The default request returns ids `[4, 9]` and `next_after: 9`. Following `?after=9` returns `[21, 37]` and `next_after: 37`; following `?after=37` returns `[52]` and `null`. With `?after=10&limit=4`, id 10 need not exist: return `[21, 37, 52]` and `null`.

Try an unknown path, a blank limit and an empty final page as well as the happy path:

```sh
curl -i 'http://127.0.0.1:45110/supplies?limit=2'
curl -i 'http://127.0.0.1:45110/supplies?after=9&limit=2'
curl -i 'http://127.0.0.1:45110/supplies?after=100000'
curl -i 'http://127.0.0.1:45110/supplies?limit='
curl -i 'http://127.0.0.1:45110/supplies/extra?limit=0'
```

## Tools, not an imposed algorithm

`BaseHTTPRequestHandler.path` contains the path and query. `urllib.parse.urlsplit` can separate them; `parse_qs` returns a list for each name so duplicates are visible. It drops blank values by default, so study `keep_blank_values` if you choose it. Other correct parsing strategies are accepted.

HTTP sends a status line, headers, an empty line, then body bytes. `send_response`, `send_header`, `end_headers` and `wfile.write` implement those steps. Encode JSON as UTF-8. A matching `Content-Length` or a properly closed response lets a client know when it is complete. Copying before sorting is one way to protect the supplied snapshot; a different non-mutating selection is equally valid.

Verify sends bounded real HTTP requests across different snapshots: default and explicit pages, absent cursor ids, empty/end pages, encoded values, invalid queries, unknown paths, repeats and interleaved cursors. It also inspects the original snapshot for changes. Hidden examples introduce no new parameters or requirements. These checks establish this read-only pagination contract, not a production API or general HTTP mastery.

Hints and coaching are welcome and do not reduce completion, XP or charge. Transfer records whether this trial used in-game assistance; assistance on Signal or Gateway alone does not label the trial guided. An optional English debrief is practice, never a technical gate.

References: [HTTP server](https://docs.python.org/3.10/library/http.server.html), [URL parsing](https://docs.python.org/3.10/library/urllib.parse.html).
