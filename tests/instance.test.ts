import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtemp, rm } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { claimInstance } from '../server/instance.js'
import { DatabaseSync } from 'node:sqlite'

test('a second service cannot rotate bridge credentials or interrupt active evaluations in the same save directory', async () => {
  const home = await mkdtemp(path.join(os.tmpdir(), 'rankforge-instance-'))
  try {
    const release = await claimInstance(home)
    await assert.rejects(claimInstance(home), /already owns/)
    await release()
    const next = await claimInstance(home)
    await next()
    const db = new DatabaseSync(path.join(home, 'instance.sqlite'))
    db.prepare('INSERT INTO instance VALUES(1,?,?)').run(2147483647, 'dead-process')
    db.close()
    const recover = await claimInstance(home)
    await recover()
  } finally { await rm(home, { recursive: true, force: true }) }
})
