import { test, expect } from '@playwright/test'
import { copyFile } from 'node:fs/promises'
import path from 'node:path'
import type { Snapshot } from '../../shared/types.js'
import { currentContractVersion } from '../../shared/contracts.js'

test('the actual browser loop fails broken code, accepts repaired code, preserves draft and awards once', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('console', (message) => { if (message.type() === 'error') errors.push(message.text()) })
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'A world worth restoring.' })).toBeVisible()
  await expect(page.locator('.map-canvas canvas')).toBeVisible()
  await page.getByRole('button', { name: 'Prepare workspace only', exact: true }).click()
  await expect(page.locator('.workspace-info')).toContainText('workspaces/signal')
  await page.getByRole('button', { name: 'Verify lab', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Evidence needs attention' })).toBeVisible()
  const bootstrap = await page.request.get('/api/bootstrap').then((response) => response.json())
  const workspace = bootstrap.snapshot.missions[0].workspace as string
  await copyFile(path.resolve('tests/solutions/signal.py'), path.join(workspace, 'service.py'))
  await page.getByRole('button', { name: 'Verify lab', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'System restored' })).toBeVisible()
  await expect(page.locator('.xp-line')).toContainText('120 XP')
  await page.getByRole('button', { name: 'Verify lab', exact: true }).click()
  await expect(page.locator('.xp-line')).toContainText('120 XP')
  await page.getByRole('button', { name: 'View Give memory a structure', exact: true }).click()
  await expect(page.getByLabel('Mission briefing').getByRole('heading', { name: 'Give memory a structure', exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByLabel('Mission briefing').getByRole('heading', { name: 'Give memory a structure', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'View A signal in the dark', exact: true }).click()
  await page.getByRole('button', { name: 'Verify lab', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'System restored' })).toBeVisible()
  await expect(page.locator('.xp-line')).toContainText('120 XP')
  await page.getByRole('button', { name: 'Operator chat', exact: true }).click()
  await page.getByLabel('Your answer in English').fill('I found an incorrect HTTP status. I fixed the health contract.')
  await page.reload()
  await expect(page.getByLabel('Your answer in English')).toHaveValue('I found an incorrect HTTP status. I fixed the health contract.')
  await page.getByRole('button', { name: 'Send ↗', exact: true }).click()
  await expect(page.getByText('The System is resting.')).toBeVisible()
  await expect(page.locator('.learner-message')).toContainText('I found an incorrect HTTP status.')
  await page.reload()
  await expect(page.getByText('The System is resting.')).toBeVisible()
  await expect(page.locator('.learner-message')).toContainText('I found an incorrect HTTP status.')
  await page.screenshot({ path: 'test-results/outpost-paused.png', fullPage: true })
  expect(errors).toEqual([])
})

test('desktop layout, keyboard navigation and connection stay usable without overflow', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('navigation', { name: 'Main navigation' })).toBeVisible()
  for (const size of [{ width: 1600, height: 1000 }, { width: 1280, height: 800 }, { width: 1024, height: 768 }]) {
    await page.setViewportSize(size)
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    const map = await page.getByLabel('Expedition overview', { exact: true }).boundingBox()
    const navigation = await page.locator('.topbar').boundingBox()
    const mission = await page.getByLabel('Mission briefing').boundingBox()
    expect(map!.width).toBeGreaterThan(size.width * .9)
    expect(navigation!.y + navigation!.height).toBeLessThan(map!.y)
    expect(mission!.y).toBeGreaterThan(map!.y + map!.height)
    expect(mission!.y - map!.y - map!.height).toBeLessThan(60)
    expect(mission!.width).toBeGreaterThan(size.width * .9)
  }
  await page.getByLabel('Player profile', { exact: true }).click()
  await page.getByRole('button', { name: 'Skills & rewards', exact: false }).click()
  await expect(page.getByRole('heading', { name: 'Skills & rewards' })).toBeVisible()
  await expect(page.getByText('No speaking/listening level or CEFR certification is inferred.', { exact: false })).toBeVisible()
  await page.getByRole('button', { name: 'Field journal', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Your work leaves a trace.' })).toBeVisible()
  await page.getByLabel('Player profile', { exact: true }).click()
  await page.getByRole('button', { name: 'Connection', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Your account. Your outpost.' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Connect ChatGPT', exact: true })).toBeVisible()
  await page.getByRole('combobox', { name: 'Tutor model' }).focus()
  await expect(page.getByRole('combobox', { name: 'Tutor model' })).toBeFocused()
  await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'reduce' })
  await page.getByRole('button', { name: 'The outpost', exact: false }).click()
  await expect(page.locator('.map-canvas canvas')).toBeVisible()
  await page.screenshot({ path: 'test-results/outpost-1024.png', fullPage: true })
})

test('map and cards are exclusive, persist the choice and preview missions without starting the editor', async ({ page }) => {
  const starts: string[] = []
  const errors: string[] = []
  page.on('request', (request) => { if (request.method() === 'POST' && request.url().endsWith('/start')) starts.push(request.url()) })
  page.on('pageerror', (error) => errors.push(error.message))
  await page.goto('/')
  await expect(page.locator('.map-canvas canvas')).toBeVisible()
  await expect(page.getByLabel('Quest cards')).toHaveCount(0)
  await page.getByRole('button', { name: '▦ Cards', exact: true }).focus()
  await page.keyboard.press('Enter')
  await expect(page.getByRole('button', { name: '▦ Cards', exact: true })).toHaveAttribute('aria-pressed', 'true')
  await expect(page.locator('.map-canvas')).toHaveCount(0)
  await expect(page.locator('.mission-card')).toHaveCount(7)
  const locked = page.locator('.mission-card.sector-recovery')
  await locked.getByRole('button', { name: 'Preview quest' }).click()
  await expect(page.getByLabel('Mission briefing')).toBeFocused()
  await expect(page.getByLabel('Mission briefing')).toContainText('After the blackout')
  await expect(page.getByRole('button', { name: 'Accept mission & open VS Code' })).toBeDisabled()
  await page.reload()
  await expect(page.locator('.mission-card.sector-recovery')).toHaveClass(/focused/)
  await expect(page.locator('.map-canvas')).toHaveCount(0)
  await page.getByRole('button', { name: '↑ Back to overview', exact: true }).click()
  await expect(page.getByRole('button', { name: '▦ Cards', exact: true })).toBeFocused()
  for (let index = 0; index < 3; index++) {
    await page.getByRole('button', { name: '◇ Map', exact: true }).click()
    await expect(page.locator('.map-canvas canvas')).toHaveCount(1)
    await page.getByRole('button', { name: '▦ Cards', exact: true }).click()
    await expect(page.locator('.map-canvas')).toHaveCount(0)
  }
  await page.locator('.mission-card.sector-signal').getByRole('button', { name: /quest/ }).click()
  await page.getByRole('button', { name: 'Open conversation ↗', exact: true }).click()
  await page.getByLabel('Your answer in English').fill('Keep this draft while I inspect the evidence.')
  await page.getByRole('button', { name: '← Back to outpost', exact: true }).click()
  await expect(page.getByLabel('Mission briefing')).toBeFocused()
  await page.getByRole('button', { name: 'Open conversation ↗', exact: true }).click()
  await expect(page.getByLabel('Your answer in English')).toHaveValue('Keep this draft while I inspect the evidence.')
  expect(starts).toEqual([])
  expect(errors).toEqual([])
})

test('legacy evidence stays historical, chat preserves a hint and a late check cannot steal navigation', async ({ page }) => {
  const bootstrap = await page.request.get('/api/bootstrap').then(response => response.json())
  const state = bootstrap.snapshot as Snapshot
  state.connection.paused = false
  state.connection.reason = null
  state.activeMissionId = 'signal'
  const old = { passed: true, supported: true, output: '', checkedAt: '2026-10-03T10:00:00Z', checks: [{ name: 'Earlier contract', passed: true, detail: 'Historical synthetic result' }] }
  for (const id of ['signal', 'vault']) {
    const mission = state.missions.find(item => item.id === id)!
    mission.status = 'completed'
    mission.workspace = `/synthetic/${id}`
    mission.checks = id === 'signal' ? old : { ...old, contractVersion: currentContractVersion }
  }
  let release: (() => Promise<void>) | undefined
  await page.route('**/api/**', async route => {
    const request = route.request()
    if (request.method() === 'GET') return route.fulfill({ json: request.url().endsWith('/api/bootstrap') ? { token: 'synthetic', snapshot: state } : state })
    if (request.url().endsWith('/hint')) return route.fulfill({ json: { hint: 'Keep this diagnostic while consulting the operator.' } })
    if (request.url().endsWith('/check')) {
      await new Promise<void>(resolve => { release = async () => { await route.fulfill({ json: state }); resolve() } })
      return
    }
    throw new Error('Unexpected write in navigation test')
  })
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Previous contract result' })).toBeVisible()
  await expect(page.locator('.legacy-evidence')).toContainText('completion and XP are preserved')
  await expect(page.locator('.objectives li > span').first()).toHaveText('1')
  await page.getByRole('button', { name: /Request a hint/ }).click()
  await expect(page.locator('.hint-box')).toContainText('Keep this diagnostic')
  await page.getByRole('button', { name: 'Open conversation ↗', exact: true }).click()
  await page.getByRole('button', { name: '← Back to outpost', exact: true }).click()
  await expect(page.locator('.hint-box')).toContainText('Keep this diagnostic')
  await page.getByRole('button', { name: 'Verify lab', exact: true }).click()
  await expect.poll(() => Boolean(release)).toBe(true)
  await page.getByRole('button', { name: 'Operator chat', exact: true }).click()
  await page.getByLabel('Quest', { exact: true }).selectOption('vault')
  await page.getByRole('button', { name: '← Back to outpost', exact: true }).click()
  await page.getByRole('button', { name: '↑ Back to overview', exact: true }).click()
  await expect(page.getByRole('button', { name: '◇ Map', exact: true })).toBeFocused()
  await release!()
  await expect(page.getByRole('button', { name: 'Verify lab', exact: true })).toBeEnabled()
  await expect(page.getByRole('button', { name: '◇ Map', exact: true })).toBeFocused()
  await expect(page.getByLabel('Mission briefing').getByRole('heading', { name: 'Give memory a structure', exact: true })).toBeVisible()
})
