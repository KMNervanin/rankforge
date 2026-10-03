import { test, expect, type Page } from '@playwright/test'
import { missions } from '../../shared/content.js'
import type { Exchange, Snapshot } from '../../shared/types.js'

const code = 'if request_is_ready:\n    print("Requested path:", path, flush=True)\n'
const markdown = '# Debug the request\n\nKeep the **saved file** and `do_GET` in view.\n\n- Save the file\n- Send a request\n\n```python\n' + code + '```\n\n| Source | What it contains |\n| --- | --- |\n| Editor | Unsaved buffer |\n| Disk | Saved code |\n\n> Check the evidence first.\n\n~~Guessing~~\n\n- [x] Read the saved file\n\n[Documentation](https://docs.python.org/3/library/http.server.html)\n\n[Unsafe link](javascript:alert(1))\n\n<img src="https://example.invalid/tracker" onerror="window.injected=true">\n<script>window.injected=true</script>\n\n![Remote picture](https://example.invalid/remote.png)'

function exchange(index: number, reply: string, missionId = 'signal'): Exchange {
  return { id: `synthetic-exchange-${index}`, missionId, mode: 'coach', text: `Question ${index}: What does the evidence show?`, question: 'Explain the diagnostic result.', status: 'completed', reply, grade: null, error: null, createdAt: '2026-10-03T10:00:00Z' }
}

function snapshot(exchanges: Exchange[]): Snapshot {
  return {
    missions: missions.map((mission) => ({ ...mission, status: mission.id === 'signal' || mission.id === 'vault' ? 'available' : 'locked', workspace: null, hintsUsed: 0, checks: null, completedAt: null, independent: false })),
    activeMissionId: 'signal', xp: 0, rank: 'E · Initiate',
    language: { band: 'guided', evidenceCount: 0, distinctMissions: 0, due: [], coverage: 'Written interaction only.' },
    journal: [], exchanges,
    connection: { signedIn: true, model: 'test-only', paused: false, reason: null, editorConnected: false },
  }
}

async function serveSnapshot(page: Page, state: Snapshot) {
  const writes: { url: string; body: { id: string; mode: Exchange['mode']; text: string } }[] = []
  await page.route('**/api/**', async (route) => {
    const request = route.request()
    if (request.method() === 'GET') {
      await route.fulfill({ json: request.url().endsWith('/api/bootstrap') ? { token: 'test-only-csrf', snapshot: state } : state })
      return
    }
    writes.push({ url: request.url(), body: request.postDataJSON() })
    await route.fulfill({ status: 202, json: { id: writes.at(-1)!.body.id } })
  })
  await page.goto('/')
  await page.getByRole('button', { name: 'Operator chat', exact: true }).click()
  await expect(page.getByRole('log', { name: 'Conversation history' })).toBeVisible()
  return writes
}

test('long conversations stay wide and bounded, retain every message and do not pull the reader to a new reply', async ({ page }) => {
  const state = snapshot(Array.from({ length: 120 }, (_, index) => exchange(index, `Reply ${index}.\n\nRead the saved file before drawing a conclusion.\n\n\`print(value)\` writes to the server terminal.\n\n${'A useful diagnostic distinguishes two plausible explanations. '.repeat(4)}`)))
  state.exchanges.push(exchange(500, 'A different quest keeps a different conversation.', 'vault'))
  const writes = await serveSnapshot(page, state)
  const history = page.getByRole('log', { name: 'Conversation history' })
  await expect(page.locator('.chat-exchange')).toHaveCount(120)
  const bounds = await history.boundingBox()
  expect(bounds!.width).toBeGreaterThan(900)
  await expect.poll(() => history.evaluate((element) => element.scrollHeight - element.clientHeight - element.scrollTop)).toBeLessThan(3)
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollHeight - innerHeight)).toBeLessThan(3)
  await page.getByRole('button', { name: 'Oldest', exact: true }).click()
  await expect(page.locator('.chat-exchange').first()).toBeInViewport()
  await expect.poll(() => history.evaluate((element) => element.scrollTop)).toBe(0)
  state.exchanges.push(exchange(120, 'A newly arrived reply. **Keep your reading position.**'))
  await expect(page.getByRole('button', { name: 'New activity ↓', exact: true })).toBeVisible()
  await expect.poll(() => history.evaluate((element) => element.scrollTop)).toBe(0)
  await expect(page.locator('.chat-exchange')).toHaveCount(121)
  await page.getByRole('button', { name: 'New activity ↓', exact: true }).click()
  await expect(page.locator('.chat-exchange').last()).toBeInViewport()
  await page.getByRole('button', { name: 'Oldest', exact: true }).click()
  await page.getByRole('button', { name: '← Back to outpost', exact: true }).click()
  await page.getByRole('button', { name: 'Operator chat', exact: true }).click()
  await expect.poll(() => history.evaluate((element) => element.scrollTop)).toBe(0)
  await page.getByLabel('Quest', { exact: true }).selectOption('vault')
  await expect(page.locator('.chat-exchange')).toHaveCount(1)
  await page.getByLabel('Quest', { exact: true }).selectOption('signal')
  await expect(page.locator('.chat-exchange')).toHaveCount(121)
  await expect.poll(() => history.evaluate((element) => element.scrollTop)).toBe(0)
  await page.setViewportSize({ width: 1024, height: 768 })
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth && document.documentElement.scrollHeight <= innerHeight + 2)).toBe(true)
  await expect(page.getByLabel('Your answer in English')).toBeInViewport({ ratio: 1 })
  expect(writes).toEqual([])
})

test('Markdown renders semantically, preserves code and never executes HTML or fetches remote images', async ({ page }) => {
  const state = snapshot([exchange(0, markdown)])
  const externalRequests: string[] = []
  page.on('request', (request) => { if (!request.url().startsWith('http://127.0.0.1:4197')) externalRequests.push(request.url()) })
  await page.addInitScript(() => {
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: async (text: string) => { (window as Window & { copiedCode?: string }).copiedCode = text } } })
  })
  await serveSnapshot(page, state)
  const message = page.locator('.operator-message')
  await expect(message.locator('strong', { hasText: 'saved file' })).toHaveCount(1)
  await expect(message.getByRole('heading', { name: 'Debug the request' })).toHaveCount(1)
  await expect(message.locator('table')).toHaveCount(1)
  await expect(message.locator('blockquote')).toHaveCount(1)
  await expect(message.locator('del')).toHaveText('Guessing')
  await expect(message.locator('input[type=checkbox]')).toBeChecked()
  await expect(message.locator('pre code')).toHaveText(code)
  expect(await message.locator('pre code').textContent()).toBe(code)
  await message.getByRole('button', { name: 'Copy code', exact: true }).click()
  await expect.poll(() => page.evaluate(() => (window as Window & { copiedCode?: string }).copiedCode)).toBe(code)
  await expect(message.getByRole('link', { name: 'Documentation', exact: true })).toHaveAttribute('rel', 'noopener noreferrer')
  await expect(message.locator('script, iframe, img, a[href^="javascript:"]')).toHaveCount(0)
  expect(await page.evaluate(() => Boolean((window as Window & { injected?: boolean }).injected))).toBe(false)
  expect(externalRequests).toEqual([])
})

test('composer remains visible for wide code, restores drafts and submits only on the explicit shortcut', async ({ page }) => {
  const state = snapshot([exchange(0, '```text\n' + 'very_long_identifier_'.repeat(90) + '\n```')])
  const writes = await serveSnapshot(page, state)
  await page.getByRole('button', { name: 'Ask for guidance', exact: true }).click()
  const input = page.getByLabel('Your answer in English')
  await input.fill('Why is my print missing?')
  await input.press('Enter')
  await input.type('The server received the request.')
  expect(writes).toHaveLength(0)
  await page.getByRole('button', { name: 'Mission debrief', exact: true }).click()
  await input.fill('I checked the saved file.')
  await page.getByRole('button', { name: 'Ask for guidance', exact: true }).click()
  await expect(input).toHaveValue('Why is my print missing?\nThe server received the request.')
  await page.reload()
  await expect(page.getByRole('log', { name: 'Conversation history' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Ask for guidance', exact: true })).toHaveAttribute('aria-pressed', 'true')
  await expect(input).toHaveValue('Why is my print missing?\nThe server received the request.')
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  expect(await page.locator('.code-block pre').evaluate((element) => element.scrollWidth > element.clientWidth)).toBe(true)
  await input.press('Control+Enter')
  await expect.poll(() => writes.length).toBe(1)
  expect(writes[0]!.body.text).toBe('Why is my print missing?\nThe server received the request.')
  expect(writes[0]!.body.mode).toBe('coach')
  await expect(input).toHaveValue('')
  state.connection.paused = true
  state.connection.reason = 'Synthetic quota pause.'
  await expect(page.getByText('The System is resting.', { exact: true })).toBeVisible()
  await page.setViewportSize({ width: 1024, height: 768 })
  await expect(input).toBeInViewport({ ratio: 1 })
  await expect(page.getByRole('button', { name: 'Send ↗', exact: true })).toBeDisabled()
})
