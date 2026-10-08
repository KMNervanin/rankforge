import { test, expect } from '@playwright/test'
import type { MissionView, Snapshot } from '../../shared/types.js'

const atlasLabel: Record<MissionView['status'], string> = { completed: 'completed', available: 'available', active: 'available', locked: 'locked' }

test('the Atlas tab draws the whole oak, mirrors the map statuses and opens a mission from its card', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('console', (message) => { if (message.type() === 'error') errors.push(message.text()) })
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'A world worth restoring.' })).toBeVisible()
  // The map and the Atlas read the same snapshot; the map node texts are the map's own statement of each status.
  const snapshot = (await page.request.get('/api/bootstrap').then((response) => response.json())).snapshot as Snapshot
  const mapStatus = new Map<string, MissionView['status']>()
  for (const mission of snapshot.missions) {
    const node = page.locator(`.map-node.sector-${mission.id}`)
    if (await node.count()) {
      const text = await node.innerText()
      mapStatus.set(mission.id, text.includes('Restored!') ? 'completed' : text.includes('Yet to discover') ? 'locked' : 'available')
    }
  }
  expect(mapStatus.size).toBe(6)

  await page.getByRole('button', { name: 'Atlas', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'The campaign oak' })).toBeVisible()
  await expect(page.locator('.atlas-node.catalog')).toHaveCount(92)
  await expect(page.locator('.atlas-node.trial')).toHaveCount(1)
  await expect(page.locator('.atlas-node.leaf')).toHaveCount(snapshot.missions.filter((mission) => mission.nudge).length)
  await expect(page.locator('.atlas-node.proposal')).toHaveCount(6)
  await expect(page.locator('.atlas-node.proposal').first()).toContainText('proposed')
  for (const mission of snapshot.missions) {
    const node = page.locator(`.atlas-node[data-runtime="${mission.id}"]`)
    await expect(node).toHaveCount(1)
    const expected = mapStatus.get(mission.id) ?? mission.status
    expect(expected, `${mission.id}: the map and the snapshot agree`).toBe(mission.status === 'active' ? 'available' : mission.status)
    await expect(node).toHaveAttribute('data-status', expected)
    await expect(node).toContainText(atlasLabel[mission.status])
    await expect(node.locator('.atlas-star')).toHaveCount(3)
  }
  expect(await page.locator('.atlas-node.completed').count()).toBe(snapshot.missions.filter((mission) => mission.status === 'completed').length)
  // "Where am I" centres the first available runtime mission on screen at scale 1.
  const stage = (await page.locator('.atlas-stage').boundingBox())!
  const signal = (await page.locator('.atlas-node[data-runtime="signal"]').boundingBox())!
  expect(Math.abs(signal.x + signal.width / 2 - (stage.x + stage.width / 2))).toBeLessThan(8)
  expect(Math.abs(signal.y + signal.height / 2 - (stage.y + stage.height / 2))).toBeLessThan(8)
  expect(signal.width).toBeGreaterThan(208); expect(signal.width).toBeLessThan(215) // 210 plus the stroke at scale 1
  await page.screenshot({ path: 'test-results/atlas-where-am-i.png' })

  await page.locator('.atlas-node[data-id="I02"]').click()
  const card = page.getByRole('dialog', { name: 'Mission card' })
  await expect(card).toContainText('I02 · Give memory a structure')
  await expect(card).toContainText('Enforce relational inventory rules in SQLite')
  await expect(card).toContainText('locked')
  await expect(card.locator('.atlas-pre button')).toHaveCount(2)
  await expect(page.locator('.atlas-dep')).toHaveCount(2)
  await expect(page.locator('.atlas-node[data-id="I01"]')).not.toHaveClass(/dim/)
  await expect(page.locator('.atlas-node[data-id="C04"]')).toHaveClass(/dim/)
  await card.locator('.atlas-pre button', { hasText: 'F08' }).click()
  await expect(card).toContainText('F08 · Ask a table')
  await expect(card).toContainText('ahead')
  await page.keyboard.press('Escape')
  await expect(card).toHaveCount(0)
  await expect(page.locator('.atlas-node[data-id="F08"]')).toBeFocused()

  await page.getByRole('button', { name: 'Where am I' }).click()
  await expect.poll(async () => Math.round((await page.locator('.atlas-node[data-id="I01"]').boundingBox())!.width)).toBeGreaterThan(208)
  await page.locator('.atlas-node[data-id="I01★"]').click()
  await expect(card).toContainText('Rumour says a careful client counts every byte')
  await expect(card).toContainText('hidden bonus')
  await page.getByRole('button', { name: 'Whole tree' }).click()
  await expect.poll(async () => (await page.locator('.atlas-node[data-id="C04"]').boundingBox())!.width).toBeLessThan(100)
  await page.getByRole('button', { name: 'Where am I' }).click()
  await expect.poll(async () => Math.round((await page.locator('.atlas-node[data-id="I01"]').boundingBox())!.width)).toBeGreaterThan(208)
  await page.screenshot({ path: 'test-results/atlas-card.png' })

  await page.locator('.atlas-node[data-runtime="gateway"]').focus()
  await page.keyboard.press('Enter')
  await expect(card).toContainText('I03 · Open the right gate')
  await card.getByRole('button', { name: 'Open mission' }).click()
  await expect(page.getByLabel('Mission briefing').getByRole('heading', { name: 'Open the right gate', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Atlas', exact: true })).not.toHaveClass(/nav-active/)
  expect(errors).toEqual([])
})
