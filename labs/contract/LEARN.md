# A contract you can execute — delivery probe v1

The briefing promises one delivery effect even when a sender retries. Write the **consumer's probe**, not the service. The supplied equivalent v1 briefing is the HTTP contract below; no prior workspace is copied or modified. `fixtures.py` provides short-lived real HTTP servers on owned loopback ports. Your probe must accept different valid response formatting and catch a plausible impostor.

## Entry point

Implement `probe(base_url, scenario)` in `probe.py`. It returns:

```text
{"status": "passed" | "failed" | "timeout" | "unavailable",
 "checks": [{"name": ..., "passed": true | false, "detail": nonempty string}, ...]}
```

Return exactly one result for each name: `create`, `replay`, `conflict`, `read`, `query`, `missing`, `effects`. Order is free. `passed` means all seven pass, `failed` means an HTTP contract assertion failed (including malformed JSON, a redirect or wrong MIME). Timeout while connecting/reading is `timeout`; refused connection or disconnect before a response is `unavailable`. These transport outcomes must have at least one failed check; mark unattempted checks false and explain. They are not proof that the service violated an HTTP assertion. Do not report HTTP 404/409/500 as unavailable. Close all client connections, do not retry, and stop on transport failure. Preserve `scenario`, including on errors. Fresh fixtures reset service state for each call; repeated calls on fresh fixtures must agree.

`base_url` is supplied, always `http://127.0.0.1:<owned-port>` without a path. `scenario` contains `delivery = {id, item, quantity}` and `timeout_s` (0.2..1 seconds). IDs use ASCII letters/digits/hyphens, length 1..40; item is a nonempty string up to 40 characters (including Unicode); quantity is an integer 1..100 excluding bool. Use this exact delivery, not sample literals. Set the provided timeout for every request. No extra endpoint/config input or authentication is needed. Invalid scenario handling is outside this lab.

## Seven observations

All seven responses require `X-Contract: delivery-v1` and a Content-Type whose media type is **application/json**, case-insensitively, ignoring parameters. `text/plain; note=application/json` is not JSON MIME. Header names are case-insensitive. Parse JSON: whitespace/key order and extra optional fields are harmless. Required strings and integer values must have the stated types (bool is not an integer quantity/effect). Every response must contain its required fields below with exactly the stated values; extra fields are tolerated. Do not compare JSON source strings.

| Check | Request | Required status and JSON fields |
| --- | --- | --- |
| create | POST /deliveries, scenario delivery | 201; the delivery's id, item and quantity with exact values; extra fields tolerated |
| replay | POST /deliveries, identical delivery | 200; the same required fields with exact values; extra fields tolerated |
| conflict | POST /deliveries, same id/item, quantity + 1 | 409; `error: "conflict"` |
| read | GET /deliveries/{id}?view=full | 200; original delivery fields plus `view: "full"` |
| query | GET /deliveries/{id}?view=summary | 200; original id/quantity plus `view: "summary"` |
| missing | GET /deliveries/{id}/missing?view=full | 404; `error: "not_found"` |
| effects | GET /stats | 200; `effects: 1` |

Request targets are byte-exact: `POST /deliveries`, `GET /deliveries/{id}?view=full`, `GET /deliveries/{id}?view=summary`, `GET /deliveries/{id}/missing?view=full` and `GET /stats`, with no trailing slash and no added or reordered query parameters. Send the three POSTs in the listed order; each body is the delivery as JSON encoded in UTF-8 with `Content-Type: application/json` (a charset parameter is fine). After them issue each listed GET once, in any order. Continue checking all seven after an HTTP mismatch; a bad body/header must not hide another observation. The only permitted side effect is one original delivery. Neither replay nor conflict may change it; the read plus stats expose both corruption and duplicate effects. The verifier observes actual requests and fixture state as well as your report, so returning a canned result cannot pass.

Advice: send the body as one UTF-8 `bytes` value so the client sets Content-Length; the fixture also accepts chunked bodies, but you do not need them.

Exactly these seven requests per responding fixture: Verify observes every request, so redirects, polling and additional requests fail. Use only the supplied base URL; never a production or arbitrary endpoint. Advice, not checked: read at most 8 KiB per response (fixture responses are <=4 KiB), ignore proxy environment settings, and do not sleep, spawn processes or write files. HTTP clients that follow redirects or apply proxy environment settings need explicit configuration. With urllib, HTTPError carries the HTTP response and must be inspected; it is not a transport outage. With http.client, inspect response.status and read/close each response.

## Terminal rehearsal

From your saved workspace:

```sh
python3 -B demo.py direct
python3 -B demo.py table
python3 -B demo.py duplicate
python3 -B demo.py timeout
python3 -B demo.py unavailable
python3 -B demo.py before-deadline
python3 -B demo.py after-deadline
```

Each command owns a temporary fixture and cleans it up, with no daemon to start/stop. The starter sends only one POST and checks only its status; its incomplete report should fail Verify. The demo prints your report, it is not the independent evaluator. Other fault modes: `status`, `http_error`, `redirect`, `header`, `media`, `body`, `quantity_type`, `boolean`, `path`, `query`, `error_body`, `json`, `conflict_effect`. To corrupt another observation, use `status:replay`, `header:read`, `media:conflict`, `body:effects` or `json:missing`: each of these five fault kinds supports each check name. Verify changes status/header/media/body/JSON at **every** response position, not just create. A robust probe should pass `direct`/`table`, fail contract faults, and label the two transport failures separately. Unknown demo modes are not part of the acceptance contract.

Every required field is also changed and omitted separately at each applicable response: `wrong:create:id`, `missing:replay:item`, `wrong:read:view`, `missing:effects:effects`, and the corresponding combinations in the table above. Check actual values and presence, not only their types. Extra optional fields remain valid.

### Timeout budget rehearsal

Use each scenario's `timeout_s`, not a fixed constant. Ordinary cases vary between 0.2, 0.6 and 1.0 seconds. For both the first create and later effects request, Verify also holds a real response behind an Event: release after 0.55 s with a 1.0 s budget must succeed; release scheduled after 0.8 s with a 0.2 s budget must time out. The timer starts only when that request reaches the fixture, not at process startup. Requests completed before a later timeout retain their passed checks; that request and all unattempted ones fail, without retries.

For the expired-budget cases, return within the supplied budget **plus 0.5 s scheduling/cleanup tolerance**, measured from request receipt. This generous physical bound catches ignored timeouts/late fabricated timeout labels; it is not permission to configure a longer socket timeout. A controller scheduling gap over 0.25 s or an in-budget gate released later than 0.8 s is environment-blocked: rerun when the machine is idle, with no technical pass awarded. These are bounded read-timeout observations, not precise timing certification for every OS/socket operation. Correctness uses request-arrival/release/cancellation events, not a blind startup sleep.

## Missing prerequisites and limits

A URL has a host, port, path and query. `/deliveries/x?view=summary` has the same path as the full view but asks for a different representation; `/deliveries/x/missing` has a different path. Status is the protocol outcome, headers describe interpretation, body carries data, and a later read observes state. If Signal was completed elsewhere, these definitions and fixtures replace its prerequisite artifacts. Read Python's [http.client](https://docs.python.org/3.10/library/http.client.html) or [urllib.request](https://docs.python.org/3.10/library/urllib.request.html) for request and exception semantics.

Python stdlib >=3.10, one temporary service at a time, up to seven requests and one tiny record per fixture. Timeout fixtures hold the response behind an event until the probe returns; no sleep-based correctness. Unavailable fixtures accept the request and close without sending any HTTP response, giving controlled EOF rather than relying on OS/firewall connection-refusal behavior. Every endpoint remains owned throughout the call; no close/rebind race. The game runner allows 30 seconds per complete verification (outer process timeout should be 45 seconds). A broken infinite probe is stopped; a fixture-bind problem is reported as environment-blocked, never a pass. This is trusted learner code running as your user, not an OS/network sandbox. It does not certify hostile-code containment, real authorization, durable storage, concurrent retries or production reliability. Only the specified consumer contract gets a technical verdict; optional prose and debrief remain review-only.
