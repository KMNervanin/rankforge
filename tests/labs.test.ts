import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtemp, rm, copyFile, readFile, writeFile, symlink, mkdir } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { Labs, root } from '../server/labs.js'

const files: Record<string, string> = { signal: 'service.py', vault: 'store.py', echo: 'ingest.py', ledger: 'transform.py', recovery: 'recover.py' }
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

test('reopening a mission preserves edited files and previous workspaces', async () => {
  const home = await mkdtemp(path.join(os.tmpdir(), 'rankforge-preserve-'))
  try {
    const labs = new Labs(home)
    const one = await labs.prepare('signal', 'guided')
    await writeFile(path.join(one, 'service.py'), '# my unsolved work\n')
    await labs.prepare('vault', 'connected')
    assert.equal(await labs.prepare('signal', 'independent'), one)
    assert.equal(await readFile(path.join(one, 'service.py'), 'utf8'), '# my unsolved work\n')
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
