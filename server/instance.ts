import { mkdir } from 'node:fs/promises'
import { randomUUID } from 'node:crypto'
import path from 'node:path'
import { DatabaseSync } from 'node:sqlite'

export async function claimInstance(home: string): Promise<() => Promise<void>> {
  await mkdir(home, { recursive: true, mode: 0o700 })
  const file = path.join(home, 'instance.sqlite')
  const nonce = randomUUID()
  const db = new DatabaseSync(file, { timeout: 3000 })
  db.exec('CREATE TABLE IF NOT EXISTS instance(id INTEGER PRIMARY KEY CHECK(id=1),pid INTEGER NOT NULL,nonce TEXT NOT NULL)')
  db.exec('BEGIN IMMEDIATE')
  try {
    const owner = db.prepare('SELECT pid FROM instance WHERE id=1').get() as { pid: number } | undefined
    if (owner) {
      if (!Number.isInteger(owner.pid) || owner.pid <= 0) throw new Error('Invalid Rankforge instance owner. Inspect it before restarting.')
      try { process.kill(owner.pid, 0); throw new Error('Rankforge already owns this save directory. Open its existing local address instead.') }
      catch (error) { if ((error as NodeJS.ErrnoException).code !== 'ESRCH') throw error }
    }
    // The transaction serializes stale-owner replacement; another starter cannot remove a newly acquired claim.
    db.prepare('INSERT INTO instance VALUES (1,?,?) ON CONFLICT(id) DO UPDATE SET pid=excluded.pid,nonce=excluded.nonce').run(process.pid, nonce)
    db.exec('COMMIT')
  } catch (error) { db.exec('ROLLBACK'); throw error }
  finally { db.close() }
  return async () => {
    const current = new DatabaseSync(file, { timeout: 3000 })
    try { current.prepare('DELETE FROM instance WHERE id=1 AND nonce=?').run(nonce) } finally { current.close() }
  }
}
