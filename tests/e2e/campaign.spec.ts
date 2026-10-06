import { test, expect } from '@playwright/test'
import { copyFile, mkdtemp, rm } from 'node:fs/promises'
import { createServer } from 'node:net'
import { once } from 'node:events'
import os from 'node:os'
import path from 'node:path'
import { createApp } from '../../server/app.js'
import { root } from '../../server/labs.js'
import { currentContractVersion } from '../../shared/contracts.js'
import type { CheckResult } from '../../shared/types.js'

test('guild quests and skill trial run real checks through the browser, preserve rewards and equip after reload', async ({ page }) => {
  test.setTimeout(90000)
  const home = await mkdtemp(path.join(os.tmpdir(), 'rankforge-campaign-browser-'))
  const reservation = createServer().listen(0, '127.0.0.1')
  await once(reservation, 'listening')
  const port = (reservation.address() as { port: number }).port
  await new Promise<void>(resolve => reservation.close(() => resolve()))
  const { app, store, labs } = await createApp({ home, port, provider: { model: 'unused', hasAccount: () => false, complete: async () => { throw new Error('No model in technical acceptance') } }, launchEditor: async () => { throw new Error('Do not open editor') } })
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  try {
    // Earlier chapter setup is synthetic; the new missions below use actual Python/HTTP checks.
    const prior: CheckResult = { passed: true, supported: true, contractVersion: currentContractVersion, checkedAt: new Date().toISOString(), output: '', checks: [{ name: 'Prerequisite fixture', passed: true, detail: 'Controlled browser setup only' }] }
    for (const id of ['signal', 'vault', 'gateway', 'echo', 'ledger', 'recovery']) store.saveCheck(id, prior)
    await app.listen({ host: '127.0.0.1', port })
    await page.goto(`http://127.0.0.1:${port}`)
    await page.getByLabel('Explore', { exact: true }).selectOption('guild')
    await expect(page.getByRole('heading', { name: 'Think before you build.' })).toBeVisible()
    await expect(page.locator('.map-node')).toHaveCount(3)
    for (const [id, title, file, reference] of [
      ['briefing', 'Before the blueprint', 'manifest.py', 'architect/briefing-separated.py'],
      ['capacity', 'Count before choosing', 'capacity.py', 'architect/capacity-float.py'],
      ['contract', 'A contract you can execute', 'probe.py', 'architect/contract-urllib.py'],
    ]) {
      await page.getByRole('button', { name: `View ${title}`, exact: true }).click()
      await page.getByRole('button', { name: 'Prepare workspace only' }).click()
      await page.getByRole('button', { name: 'Verify lab', exact: true }).click()
      await expect(page.getByRole('heading', { name: 'Evidence needs attention' })).toBeVisible()
      await copyFile(path.join(root, 'tests/solutions', reference!), path.join(labs.workspace(id!), file!))
      await page.getByRole('button', { name: 'Verify lab', exact: true }).click()
      await expect(page.getByRole('heading', { name: 'System restored' })).toBeVisible()
      await expect(page.getByLabel('Lab verification')).toBeFocused()
    }
    await page.getByLabel('Player profile', { exact: true }).click()
    await page.getByRole('button', { name: 'Skills & rewards' }).click()
    await expect(page.getByRole('heading', { name: 'Skills & rewards' })).toBeVisible()
    await page.getByRole('button', { name: 'Equip Relay frame', exact: true }).click()
    await expect(page.locator('.profile-menu')).toHaveClass(/frame-relay-frame/)
    await page.getByRole('button', { name: 'Enter HTTP field trial', exact: true }).click()
    await expect(page.getByLabel('Mission briefing')).toContainText('Beyond the health check')
    await page.getByRole('button', { name: 'Prepare workspace only' }).click()
    await page.getByRole('button', { name: 'Verify lab', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'Evidence needs attention' })).toBeVisible()
    await copyFile(path.join(root, 'tests/solutions/http-trial/selection.py'), path.join(labs.workspace('http-trial'), 'service.py'))
    await page.getByRole('button', { name: 'Verify lab', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'System restored' })).toBeVisible()
    const earned = store.snapshot({ signedIn: false, paused: false, model: 'unused', editorConnected: false, reason: null }).progression!.inventory
    await page.getByRole('button', { name: 'Verify lab', exact: true }).click()
    await expect(page.getByRole('button', { name: 'Verify lab', exact: true })).toBeEnabled()
    await page.reload()
    await expect(page.locator('.profile-menu')).toHaveClass(/frame-relay-frame/)
    await expect(page.getByLabel('Mission briefing')).toContainText('Beyond the health check')
    expect(store.snapshot({ signedIn: false, paused: false, model: 'unused', editorConnected: false, reason: null }).progression!.inventory).toEqual(earned)
    await page.getByLabel('Player profile', { exact: true }).click()
    await page.getByRole('button', { name: 'Skills & rewards' }).click()
    await expect(page.locator('.charge-reserve')).toContainText('140 game charge')
    for (const width of [1024, 1280, 1600]) {
      await page.setViewportSize({ width, height: 1000 })
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    }
    await page.screenshot({ path: 'test-results/skills-and-rewards.png', fullPage: true })
    expect(errors).toEqual([])
  } finally { await app.close(); await rm(home, { recursive: true, force: true }) }
})

test('the reward infographic remains interactive under the actual service CSP', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()) })
  const response = await page.goto('/progression.html')
  expect(response?.status()).toBe(200)
  expect(response?.headers()['content-security-policy']).toContain('sha256-')
  await expect(page.getByRole('heading', { name: /Как растёт твой персонаж/ })).toBeVisible()
  expect(await page.locator('[data-step]').count()).toBeGreaterThan(0)
  await page.locator('[data-step]').first().click()
  expect(errors).toEqual([])
})
