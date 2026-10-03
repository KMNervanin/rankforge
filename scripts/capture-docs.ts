import { chromium, expect } from '@playwright/test'
import { mkdir, mkdtemp, rm } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { createServer } from 'node:net'
import { once } from 'node:events'
import { createApp } from '../server/app.js'
import { root } from '../server/labs.js'
import { missions } from '../shared/content.js'
import type { MissionView, Snapshot } from '../shared/types.js'

// Documentation fixtures only. No account, learner files or existing conversation is read.
const time = '2026-10-03T12:30:00Z'
const demo: Snapshot = {
  missions: missions.map((mission, index): MissionView => ({
    ...mission,
    status: index < 2 ? 'completed' : index < 4 ? 'available' : 'locked',
    workspace: index < 2 ? `/demo/workspaces/${mission.id}` : null,
    hintsUsed: index === 0 ? 1 : 0,
    checks: index === 0 ? { passed: true, supported: true, checkedAt: time, output: '', checks: [
      { name: 'GET /health returns the relay contract', passed: true, detail: 'Demonstration result: HTTP 200 and the expected JSON.' },
      { name: 'Query parameters preserve the route', passed: true, detail: 'Demonstration result: /health?probe=1 remains a health request.' },
      { name: 'Unknown routes return 404', passed: true, detail: 'Demonstration result: an unknown path is not reported as healthy.' },
    ] } : null,
    completedAt: index < 2 ? time : null,
    independent: index === 1,
  })),
  activeMissionId: 'signal', xp: 280, rank: 'E · Initiate',
  language: { band: 'guided', evidenceCount: 0, distinctMissions: 0, due: [], coverage: 'Written interaction only. No speaking/listening level or CEFR certification is inferred.' },
  connection: { signedIn: true, model: 'gpt-6-astra', paused: false, reason: null, editorConnected: true },
  exchanges: [{
    id: 'documentation-example', missionId: 'signal', mode: 'coach',
    text: 'How do I know which version of the file is running?',
    question: 'Explain a diagnostic step.', status: 'completed', createdAt: time, error: null, grade: null,
    reply: '**First, save the file.** The operator reads the copy on disk.\n\n```python\nprint("Requested path:", self.path, flush=True)\n```\n\n| Action | What it does |\n| --- | --- |\n| Save the file | Writes the editor buffer to disk |\n| Restart and send a request | Runs the saved `do_GET` handler |\n\nLook for the output in the **server terminal**, not the terminal running `curl`.',
  }],
  journal: [
    { id: 4, kind: 'victory', missionId: 'vault', text: 'Memory vault restored. Integrity seal acquired. Unassisted technical completion recorded.', createdAt: time },
    { id: 3, kind: 'victory', missionId: 'signal', text: 'Command relay restored. Relay health probe acquired. Guided practice recorded.', createdAt: '2026-10-03T12:10:00Z' },
    { id: 2, kind: 'hint', missionId: 'signal', text: 'A running process is not the same as a correct HTTP contract. Check the status, headers and body.', createdAt: '2026-10-03T12:05:00Z' },
    { id: 1, kind: 'mission', missionId: 'signal', text: 'Entered the command relay workshop. The first expedition begins.', createdAt: '2026-10-03T12:00:00Z' },
  ],
}

const home = await mkdtemp(path.join(os.tmpdir(), 'rankforge-docs-'))
const output = path.join(root, 'docs', 'images')
await mkdir(output, { recursive: true })
const reservation = createServer()
reservation.listen(0, '127.0.0.1')
await once(reservation, 'listening')
const address = reservation.address()
if (!address || typeof address === 'string') throw new Error('Could not reserve a documentation port.')
const port = address.port
await new Promise<void>((resolve) => reservation.close(() => resolve()))
const { app } = await createApp({ home, port, launchEditor: async () => { throw new Error('Documentation capture must not open an editor.') } })
let browser: Awaited<ReturnType<typeof chromium.launch>> | undefined
try {
  const url = await app.listen({ host: '127.0.0.1', port })
  browser = await chromium.launch({ headless: true })
  const page = await browser.newPage({ viewport: { width: 1600, height: 1100 }, reducedMotion: 'reduce', timezoneId: 'UTC' })
  page.on('pageerror', (error) => console.error(error.message))
  page.on('response', (response) => { if (response.status() >= 400) console.error(`HTTP ${response.status()} ${response.url()}`) })
  await page.route('**/api/**', async (route) => {
    if (route.request().method() !== 'GET') throw new Error('Documentation capture attempted a write action.')
    await route.fulfill({ json: route.request().url().endsWith('/api/bootstrap') ? { token: 'documentation-only', snapshot: demo } : demo })
  })
  await page.goto(url)
  await expect(page.getByRole('heading', { name: 'A world worth restoring.' })).toBeVisible()
  await expect(page.locator('.map-canvas canvas')).toBeVisible()
  await page.evaluate('new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
  await page.screenshot({ path: path.join(output, 'outpost.png') })
  await page.locator('.mission-panel').screenshot({ path: path.join(output, 'quest.png') })
  await page.getByRole('button', { name: 'Operator chat', exact: true }).click()
  await expect(page.locator('.conversation table')).toBeVisible()
  await page.screenshot({ path: path.join(output, 'chat.png') })
  await page.getByRole('button', { name: 'Abilities', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Earned through experience.' })).toBeVisible()
  await page.screenshot({ path: path.join(output, 'abilities.png') })
  await page.getByRole('button', { name: 'Field journal', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Your work leaves a trace.' })).toBeVisible()
  await page.screenshot({ path: path.join(output, 'journal.png') })
  demo.connection.signedIn = false
  await page.reload()
  await page.getByRole('button', { name: 'Connection', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Connect ChatGPT', exact: true })).toBeVisible()
  await page.screenshot({ path: path.join(output, 'connection.png') })
  console.log(`Captured six documentation screenshots from synthetic fixtures in ${output}.`)
} finally {
  await browser?.close()
  await app.close()
  await rm(home, { recursive: true, force: true })
}
