import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtemp, rm, copyFile, readFile, writeFile, symlink, mkdir } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { Labs, root } from '../server/labs.js'

const files: Record<string, string> = { signal: 'service.py', vault: 'store.py', echo: 'ingest.py', ledger: 'transform.py', recovery: 'recover.py' }
const solution = (id: string) => readFile(path.join(root, 'tests', 'solutions', `${id}.py`), 'utf8')
async function candidate(t: test.TestContext, id: string, source: string, helpers: Record<string, string> = {}) {
  const home = await mkdtemp(path.join(os.tmpdir(), 'rankforge-contract-'))
  t.after(() => rm(home, { recursive: true, force: true }))
  const labs = new Labs(home)
  const workspace = await labs.prepare(id, 'guided')
  await writeFile(path.join(workspace, files[id]!), source)
  for (const [name, content] of Object.entries(helpers)) await writeFile(path.join(workspace, name), content)
  const result = await labs.check(id)
  assert.equal(result.supported, true, JSON.stringify(result))
  return result
}
function rejected(result: Awaited<ReturnType<typeof candidate>>, name: string) {
  assert.equal(result.passed, false, JSON.stringify(result))
  assert.ok(result.checks.some((item) => item.name.includes(name) && !item.passed), JSON.stringify(result))
}
for (const [id, file] of Object.entries(files)) {
  test(`${id}: shipped broken fixture fails; independent behavioral checks accept the reference solution`, async () => {
    const home = await mkdtemp(path.join(os.tmpdir(), 'rankforge-lab-'))
    try {
      const labs = new Labs(home)
      const workspace = await labs.prepare(id, 'guided')
      const broken = await labs.check(id)
      assert.equal(broken.supported, true, broken.output)
      assert.equal(broken.passed, false, 'The initial exercise must expose a real problem')
      assert.ok(broken.checks.some((item) => !item.passed))
      await copyFile(path.join(root, 'tests', 'solutions', `${id}.py`), path.join(workspace, file))
      const fixed = await labs.check(id)
      assert.equal(fixed.passed, true, JSON.stringify(fixed, null, 2))
      assert.ok(fixed.checks.length >= 4)
    } finally { await rm(home, { recursive: true, force: true }) }
  })
}

test('loader accepts postponed dataclass annotations and learner helper imports', async (t) => {
  const source = `from __future__ import annotations\nfrom dataclasses import dataclass\nfrom helper import normalize\n@dataclass\nclass Record:\n    value: str\n` + (await solution('ledger')).replace('identity = row["id"]', 'identity = Record(row["id"]).value')
  const result = await candidate(t, 'ledger', source.replace('day, amount = row["date"], row["amount"]', 'day, amount = normalize(row["date"]), row["amount"]'), { 'helper.py': 'def normalize(value):\n    return value\n' })
  assert.equal(result.passed, true, JSON.stringify(result))
})

test('signal accepts different parsing, JSON order and media-type parameters', async (t) => {
  const source = (await solution('signal')).replace('urlsplit(self.path).path', 'self.path.partition("?")[0]').replace('"application/json"', '"Application/JSON; charset=utf-8"').replace('{"status": "ok", "service": "relay"}', '{"service": "relay", "status": "ok"}')
  assert.equal((await candidate(t, 'signal', source)).passed, true)
})

test('signal rejects a redirect instead of a direct health response', async (t) => {
  const source = (await solution('signal')).replace('ok = urlsplit(self.path).path == "/health"', `route = urlsplit(self.path).path
        if route == "/health":
            self.send_response(302)
            self.send_header("Location", "/internal-health")
            self.end_headers()
            return
        ok = route == "/internal-health"`)
  rejected(await candidate(t, 'signal', source), 'HTTP contract: /health')
})

test('signal rejects a JSON substring inside a different media type', async (t) => {
  const source = (await solution('signal')).replace('"application/json"', '"text/plain; note=application/json"')
  rejected(await candidate(t, 'signal', source), 'HTTP contract: /health')
})

test('signal rejects prefix routing that exposes unknown health-like paths', async (t) => {
  const source = (await solution('signal')).replace('urlsplit(self.path).path == "/health"', 'urlsplit(self.path).path.startswith("/health")')
  rejected(await candidate(t, 'signal', source), '/healthcheck')
})

test('vault accepts reordered columns and table-level constraints', async (t) => {
  const source = `def create_schema(c):
    c.execute("CREATE TABLE IF NOT EXISTS items(name TEXT NOT NULL,id TEXT,PRIMARY KEY(id))")
    c.execute("CREATE TABLE IF NOT EXISTS movements(quantity INTEGER NOT NULL,item_id TEXT NOT NULL,id TEXT,PRIMARY KEY(id),FOREIGN KEY(item_id) REFERENCES items(id),CHECK(0 < quantity))")
`
  const result = await candidate(t, 'vault', source)
  assert.equal(result.passed, true, JSON.stringify(result))
})

test('vault accepts deferred foreign keys at the commit boundary', async (t) => {
  const source = (await solution('vault')).replace('REFERENCES items(id)', 'REFERENCES items(id) DEFERRABLE INITIALLY DEFERRED')
  const result = await candidate(t, 'vault', source)
  assert.equal(result.passed, true, JSON.stringify(result))
})

test('vault rejects missing foreign keys at both connection boundaries', async (t) => {
  const source = (await solution('vault')).replace(' REFERENCES items(id)', '')
  const result = await candidate(t, 'vault', source)
  rejected(result, 'Reject unknown item')
  rejected(result, 'persist after commit')
})

for (const [count, check] of [[0, 'Reject unknown item'], [3, 'persist after commit']] as const) {
  test(`vault does not count a deferred setup failure as an expected rejection: ${check}`, async (t) => {
    const source = (await solution('vault')).replace('REFERENCES items(id)', 'REFERENCES items(id) DEFERRABLE INITIALLY DEFERRED') + `
    if connection.execute("SELECT COUNT(*) FROM movements").fetchone()[0] == ${count}:
        connection.execute("CREATE TABLE IF NOT EXISTS pending_setup(item_id TEXT REFERENCES items(id) DEFERRABLE INITIALLY DEFERRED)")
        connection.execute("INSERT INTO pending_setup VALUES ('ghost')")
`
    const result = await candidate(t, 'vault', source)
    rejected(result, check)
    assert.match(result.checks.find((item) => item.name.includes(check))!.detail, /IntegrityError: FOREIGN KEY constraint failed/)
  })
}

test('vault rejects temporary tables that lose committed data across connections', async (t) => {
  rejected(await candidate(t, 'vault', (await solution('vault')).replaceAll('CREATE TABLE', 'CREATE TEMP TABLE')), 'persist after commit')
})

test('echo accepts insert-first collision handling and reordered columns', async (t) => {
  const result = await candidate(t, 'echo', await solution('echo-insert-first'))
  assert.equal(result.passed, true, JSON.stringify(result))
})

for (const id of ['echo', 'recovery']) {
  test(`${id}: reject missing primary key even when application deduplication works`, async (t) => {
    const result = await candidate(t, id, (await solution(id)).replaceAll('id TEXT PRIMARY KEY', 'id TEXT'))
    rejected(result, id === 'echo' ? 'One effect' : 'Recover and repeat')
  })
  test(`${id}: reject KeyError instead of ValueError for a missing individual field`, async (t) => {
    const source = (await solution(id)).replaceAll('event.get("quantity")', 'event["quantity"]')
    rejected(await candidate(t, id, source), 'missing quantity')
  })
}

for (const id of ['echo', 'recovery', 'ledger']) {
  test(`${id}: reject truthiness-only record validation for scalars and wrong containers`, async (t) => {
    const variable = id === 'ledger' ? 'row' : 'event'
    const source = await solution(id)
    const mutant = source.replace(`not isinstance(${variable}, dict)`, `not ${variable}`)
    assert.notEqual(mutant, source)
    const result = await candidate(t, id, mutant)
    for (const name of id === 'ledger' ? ['Reject non-dictionary rows'] : ['numeric record', 'string record', 'nonempty list record', 'tuple record']) {
      rejected(result, name)
      assert.match(result.checks.find((item) => item.name.includes(name))!.detail, /AttributeError/)
    }
  })
}

test('ledger accepts Decimal arithmetic, another date parser and reverse rejected order', async (t) => {
  const result = await candidate(t, 'ledger', await solution('ledger-decimal'))
  assert.equal(result.passed, true, JSON.stringify(result))
})

test('ledger rejects float arithmetic that loses cents', async (t) => {
  const source = (await solution('ledger-decimal')).replace('amount = Decimal(raw_amount)', 'amount = float(raw_amount)').replace('Decimal(0)', '0.0')
  rejected(await candidate(t, 'ledger', source), 'Cents must survive')
})

test('ledger rejects unsupported money spellings rather than silently normalizing them', async (t) => {
  const source = (await solution('ledger-decimal')).replace('not re.fullmatch(r"[0-9]+(?:\\.[0-9]{1,2})?", raw_amount)', 'False')
  rejected(await candidate(t, 'ledger', source), 'unsupported money spellings')
})

test('ledger rejects out-of-range amounts and duplicate rejection indices', async (t) => {
  const source = await solution('ledger-decimal')
  rejected(await candidate(t, 'ledger', source.replace('amount > Decimal("9999999999999999.99")', 'False')), 'declared amount boundary')
  rejected(await candidate(t, 'ledger', source.replace('rejected[::-1]', 'rejected + rejected')), 'Bad rows and collisions')
})

test('recovery accepts validation inside a rollback transaction with an imported helper', async (t) => {
  const result = await candidate(t, 'recovery', await solution('recovery-transaction'), { 'ingest.py': await solution('echo-insert-first') })
  assert.equal(result.passed, true, JSON.stringify(result))
})

test('recovery rejects incremental upsert masquerading as full replacement', async (t) => {
  const source = (await solution('recovery')).replace('connection.execute("DELETE FROM events")', 'if not valid: connection.execute("DELETE FROM events")').replace('INSERT INTO events', 'INSERT OR REPLACE INTO events')
  rejected(await candidate(t, 'recovery', source), 'Successful recovery replaces')
})

test('recovery rejects a late failure that committed partial replacement', async (t) => {
  const source = await solution('recovery-transaction')
  const partial = source.replace('                ingest(connection, event)', '                ingest(connection, event)\n                connection.commit()')
  rejected(await candidate(t, 'recovery', partial, { 'ingest.py': await solution('echo-insert-first') }), 'Late missing quantity')
})

test('recovery rejects schema changes before failed validation', async (t) => {
  const source = (await solution('recovery')).replace('    valid = {}', '    with sqlite3.connect(db_path) as db:\n        db.execute("CREATE TABLE IF NOT EXISTS leaked(value TEXT)")\n    valid = {}')
  rejected(await candidate(t, 'recovery', source), 'Late missing quantity')
})

test('reopening a mission preserves edited files and previous workspaces', async () => {
  const home = await mkdtemp(path.join(os.tmpdir(), 'rankforge-preserve-'))
  try {
    const labs = new Labs(home)
    const one = await labs.prepare('signal', 'guided')
    await writeFile(path.join(one, 'service.py'), '# my unsolved work\n')
    await writeFile(path.join(one, 'LEARN.md'), '# My annotated manual\n')
    const originalMission = await readFile(path.join(one, 'MISSION.md'), 'utf8')
    await labs.prepare('vault', 'connected')
    assert.equal(await labs.prepare('signal', 'independent'), one)
    assert.equal(await readFile(path.join(one, 'service.py'), 'utf8'), '# my unsolved work\n')
    assert.equal(await readFile(path.join(one, 'LEARN.md'), 'utf8'), '# My annotated manual\n')
    assert.equal(await readFile(path.join(one, 'MISSION.md'), 'utf8'), originalMission)
    assert.ok((await readFile(path.join(one, 'MISSION.md'), 'utf8')).includes('Success') === false)
    assert.ok((await readFile(path.join(one, 'MISSION.md'), 'utf8')).includes('Acceptance contract'))
  } finally { await rm(home, { recursive: true, force: true }) }
})

test('workspace symlinks cannot redirect the local runner outside the owned mission', async () => {
  const home = await mkdtemp(path.join(os.tmpdir(), 'rankforge-symlink-'))
  const elsewhere = await mkdtemp(path.join(os.tmpdir(), 'rankforge-outside-'))
  try {
    const labs = new Labs(home)
    await labs.prepare('signal', 'guided')
    await rm(labs.workspace('signal'), { recursive: true })
    await symlink(elsewhere, labs.workspace('signal'))
    await assert.rejects(labs.prepare('signal', 'guided'), /no longer belongs/)
    assert.equal((await labs.check('signal')).supported, false)
  } finally { await rm(home, { recursive: true, force: true }); await rm(elsewhere, { recursive: true, force: true }) }
})

test('concurrent preparation publishes one complete workspace without overwriting user work', async () => {
  const home = await mkdtemp(path.join(os.tmpdir(), 'rankforge-concurrent-lab-'))
  try {
    const labs = new Labs(home)
    const paths = await Promise.all(Array.from({ length: 5 }, () => labs.prepare('signal', 'guided')))
    assert.equal(new Set(paths).size, 1)
    assert.ok((await readFile(path.join(paths[0]!, 'MISSION.md'), 'utf8')).includes('Acceptance contract'))
    assert.ok((await readFile(path.join(paths[0]!, 'LEARN.md'), 'utf8')).includes('Field manual'))
  } finally { await rm(home, { recursive: true, force: true }) }
})

test('coach context includes learner-created modules but excludes hidden files, credentials, dependency trees and symlinks', async () => {
  const home = await mkdtemp(path.join(os.tmpdir(), 'rankforge-context-'))
  try {
    const labs = new Labs(home)
    const workspace = await labs.prepare('signal', 'guided')
    await mkdir(path.join(workspace, 'helpers'))
    await mkdir(path.join(workspace, 'node_modules'))
    await writeFile(path.join(workspace, 'helpers', 'debug.py'), 'def inspect_request():\n    return "learner module"\n')
    await writeFile(path.join(workspace, '.env'), 'PRIVATE_FIXTURE=not-for-the-model')
    await writeFile(path.join(workspace, 'credentials.json'), '{"private_fixture":true}')
    await writeFile(path.join(workspace, 'node_modules', 'vendor.js'), 'dependency tree')
    await writeFile(path.join(home, 'outside.py'), 'outside the mission')
    await symlink(path.join(home, 'outside.py'), path.join(workspace, 'external.py'))
    const context = await labs.context('signal')
    assert.match(context.files['helpers/debug.py']!.content, /learner module/)
    assert.ok(context.files['MISSION.md'])
    assert.ok(context.files['LEARN.md'])
    assert.equal(context.files['.env'], undefined)
    assert.equal(context.files['credentials.json'], undefined)
    assert.equal(context.files['node_modules/vendor.js'], undefined)
    assert.equal(context.files['external.py'], undefined)
    assert.equal(context.visibility.unsavedEditorBuffers, false)
  } finally { await rm(home, { recursive: true, force: true }) }
})

test('large saved-file context is bounded and tells the coach about omissions and truncation', async () => {
  const home = await mkdtemp(path.join(os.tmpdir(), 'rankforge-context-limit-'))
  try {
    const labs = new Labs(home)
    const workspace = await labs.prepare('signal', 'guided')
    for (let index = 0; index < 25; index++) await writeFile(path.join(workspace, `helper-${index}.py`), '# test fixture\n'.repeat(1500))
    const context = await labs.context('signal')
    assert.ok(context.files['service.py'])
    assert.ok(Object.keys(context.files).length <= context.limits.files)
    assert.ok(Object.values(context.files).reduce((total, file) => total + file.content.length, 0) <= context.limits.totalCharacters)
    assert.ok(Object.values(context.files).some((file) => file.truncated))
    assert.ok(context.omittedFiles.length > 0)
  } finally { await rm(home, { recursive: true, force: true }) }
})
