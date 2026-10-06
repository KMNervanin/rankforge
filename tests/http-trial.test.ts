import test from 'node:test'
import assert from 'node:assert/strict'
import { cp, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { run, root } from '../server/labs.js'
import type { Check } from '../shared/types.js'

async function candidate(t: test.TestContext, source?: string, python = 'python3') {
  const workspace = await mkdtemp(path.join(os.tmpdir(), 'rankforge-http-trial-'))
  t.after(() => rm(workspace, { recursive: true, force: true }))
  await cp(path.join(root, 'labs', 'http-trial'), workspace, { recursive: true })
  if (source !== undefined) await writeFile(path.join(workspace, 'service.py'), source)
  const result = await run(python, ['-I', '-B', path.join(root, 'server', 'verify_http_trial.py'), 'http-trial', workspace], workspace)
  assert.notEqual(result.code, 124, result.stderr)
  const parsed = JSON.parse(result.stdout.trim().split('\n').at(-1) ?? '') as { checks: Check[] }
  assert.ok(parsed.checks.length, JSON.stringify(result))
  return { ...result, checks: parsed.checks }
}
const solution = (name = 'sorted') => readFile(path.join(root, 'tests', 'solutions', 'http-trial', `${name}.py`), 'utf8')
function rejected(result: Awaited<ReturnType<typeof candidate>>, check: string) {
  assert.equal(result.code, 1, JSON.stringify(result))
  assert.ok(result.checks.some((item) => !item.passed && item.name.includes(check)), JSON.stringify(result))
}

test('HTTP trial: starter is RED through actual HTTP, not a source-code assertion', async (t) => {
  const result = await candidate(t)
  rejected(result, 'defaults, stable pages')
  rejected(result, 'Invalid query')
  rejected(result, 'Exact route')
})

for (const name of ['sorted', 'selection']) {
  test(`HTTP trial: distinct ${name} implementation is GREEN on real loopback fixtures`, async (t) => {
    const result = await candidate(t, await solution(name))
    assert.equal(result.code, 0, JSON.stringify(result))
    assert.equal(result.checks.length, 7)
    assert.ok(result.checks.every((item) => item.passed))
  })
}

const mutations: [string, string, string, string][] = [
  ['blank query silently treated as absent', 'keep_blank_values=True', 'keep_blank_values=False', 'Invalid query'],
  ['known query repeats silently accepted', 'len(values) != 1 or ', '', 'Invalid query'],
  ['Unicode digit accepted outside contract', 'r"[0-9]+"', 'r"\\d+"', 'Invalid query'],
  ['limit upper bound ignored', 'not minimum <= value <= maximum', 'value < minimum', 'Invalid query'],
  ['cursor confused with an offset', 'row["id"] > after', 'getattr(self.server, "supplies").index(row) >= after', 'Cursor bounds'],
  ['cursor boundary is inclusive', 'row["id"] > after', 'row["id"] >= after', 'defaults, stable pages'],
  ['last full page gets a false continuation', 'len(rows) > limit', 'len(rows) >= limit', 'defaults, stable pages'],
  ['unknown cursor produces a missing-record error', 'after, limit = numbers["after"], numbers["limit"]', 'after, limit = numbers["after"], numbers["limit"]\n        if after and not any(row["id"] == after for row in getattr(self.server, "supplies")):\n            self.reply(404, {"error": "not found"})\n            return', 'Cursor bounds'],
  ['prefix routing exposes a child path', 'url.path != "/supplies"', 'not url.path.startswith("/supplies")', 'Exact route'],
  ['JSON substring is not a media type', 'application/json; charset=utf-8', 'text/plain; note=application/json', 'defaults, stable pages'],
  ['wrong error classification', 'self.reply(400, {"error": "invalid query"})', 'self.reply(404, {"error": "not found"})', 'Invalid query'],
  ['mutation of snapshot order', 'after, limit = numbers["after"], numbers["limit"]', 'after, limit = numbers["after"], numbers["limit"]\n        getattr(self.server, "supplies").sort(key=lambda row: row["id"])', 'Read-only snapshot'],
  ['Boolean cursor masquerades as integer', '"next_after": cursor', '"next_after": True if cursor == 1 else cursor', 'defaults, stable pages'],
  ['global cursor steals another client page', 'after, limit = numbers["after"], numbers["limit"]', 'after, limit = numbers["after"], numbers["limit"]\n        if after == 0:\n            after = getattr(self.server, "last_cursor", 0)\n        self.server.last_cursor = 18', 'Read-only snapshot'],
]

for (const [name, before, after, check] of mutations) {
  test(`HTTP trial rejects ${name}`, async (t) => {
    const source = await solution()
    assert.ok(source.includes(before), `Mutation anchor missing: ${name}`)
    rejected(await candidate(t, source.replaceAll(before, after)), check)
  })
}

test('HTTP trial accepts HTTP/1.1 framing, additional response fields and reordered JSON', async (t) => {
  const source = (await solution('selection')).replace('class Handler(BaseHTTPRequestHandler):', 'class Handler(BaseHTTPRequestHandler):\n    protocol_version = "HTTP/1.1"')
  const result = await candidate(t, source)
  assert.equal(result.code, 0, JSON.stringify(result))
})

test('HTTP trial reports import failure as a failed check', async (t) => {
  rejected(await candidate(t, 'raise ValueError("Controlled import failure")\n'), 'Load HTTP trial')
})

test('HTTP trial accepts postponed dataclass annotations', async (t) => {
  const source = 'from __future__ import annotations\nfrom dataclasses import dataclass\n@dataclass\nclass Trace:\n    value: str\n' + await solution()
  assert.equal((await candidate(t, source)).code, 0)
})

test('HTTP trial rejects incomplete framing even when the received prefix is complete JSON', async t => {
  const source = (await solution()).replace('str(len(body))', 'str(len(body) + 1)')
  rejected(await candidate(t, source), 'defaults, stable pages')
})

test('HTTP trial rejects a trailing newline accepted by a dollar-anchored digit regex', async t => {
  const source = (await solution()).replace('re.fullmatch(r"[0-9]+", values[0])', 're.match(r"^[0-9]+$", values[0])')
  rejected(await candidate(t, source), 'Invalid query')
})

test('HTTP trial publishes and enforces the inclusive body bound without prescribing framing', async t => {
  const source = await solution()
  const padded = (size: number) => source.replace('        self.send_response(status)', `        body += b" " * (${size} - len(body))\n        self.send_response(status)`)
  assert.equal((await candidate(t, padded(16384))).code, 0)
  rejected(await candidate(t, padded(16385)), 'defaults, stable pages')
  const chunked = source.replace('class Handler(BaseHTTPRequestHandler):', 'class Handler(BaseHTTPRequestHandler):\n    protocol_version = "HTTP/1.1"')
    .replace('self.send_header("Content-Length", str(len(body)))', 'self.send_header("Transfer-Encoding", "chunked")')
    .replace('self.wfile.write(body)', 'self.wfile.write(format(len(body), "x").encode() + b"\\r\\n" + body + b"\\r\\n0\\r\\n\\r\\n")')
  assert.equal((await candidate(t, chunked)).code, 0)
  const closing = source.replace('        self.send_header("Content-Length", str(len(body)))\n', '')
  assert.equal((await candidate(t, closing)).code, 0)
})
