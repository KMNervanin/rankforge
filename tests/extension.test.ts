import test from 'node:test'
import assert from 'node:assert/strict'
import vm from 'node:vm'
import { createRequire } from 'node:module'
import { mkdtemp, rm, writeFile } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { build } from 'esbuild'
import { Labs, root } from '../server/labs.js'

test('the real extension targets its own host, preserves a cancelled transition and rereads rotating bridge credentials', async () => {
  const home = await mkdtemp(path.join(os.tmpdir(), 'rankforge-extension-'))
  try {
    const labs = new Labs(home)
    const first = await labs.prepare('signal', 'guided')
    const second = await labs.prepare('vault', 'guided')
    const bridgeFile = path.join(home, 'bridge.json')
    await writeFile(bridgeFile, JSON.stringify({ url: 'http://127.0.0.1:4173', token: 'first-test-token' }))
    await writeFile(path.join(first, '.rankforge-connection.json'), JSON.stringify({ bridgeFile }))
    const calls: { name: string; args: unknown[] }[] = []
    const headers: string[] = []
    const callbacks: (() => void)[] = []
    const subscriptions: { dispose: () => void }[] = []
    let command = { id: 1, workspace: second }
    const fakeVSCode = {
      workspace: { workspaceFolders: [{ uri: { fsPath: first } }], openTextDocument: async (uri: unknown) => uri },
      window: { createStatusBarItem: () => ({ text: '', command: '', show() {}, dispose() {} }), showTextDocument: async () => {} },
      StatusBarAlignment: { Left: 1 },
      Uri: { file: (file: string) => ({ fsPath: file }) },
      commands: { registerCommand: () => ({ dispose() {} }), executeCommand: async (name: string, ...args: unknown[]) => { calls.push({ name, args }) } },
    }
    const bundle = await build({ entryPoints: [path.join(root, 'extension/src/extension.ts')], bundle: true, platform: 'node', format: 'cjs', external: ['vscode'], write: false })
    const localRequire = createRequire(import.meta.url)
    const module = { exports: {} as { activate?: (context: unknown) => Promise<void> } }
    const context = vm.createContext({ module, exports: module.exports, require: (name: string) => name === 'vscode' ? fakeVSCode : localRequire(name), URL, AbortSignal, console, setInterval: (callback: () => void) => { callbacks.push(callback); return 1 }, clearInterval: () => {}, fetch: async (_url: string, init: RequestInit) => { headers.push(new Headers(init.headers).get('x-rankforge-bridge')!); return Response.json({ command }) } })
    vm.runInContext(bundle.outputFiles[0]!.text, context)
    await module.exports.activate!({ subscriptions })
    assert.equal(calls.length, 1)
    assert.equal(calls[0]!.name, 'vscode.openFolder')
    assert.equal((calls[0]!.args[0] as { fsPath: string }).fsPath, second)
    assert.equal((calls[0]!.args[1] as { forceReuseWindow: boolean }).forceReuseWindow, true)
    callbacks[0]!(); await new Promise((resolve) => setTimeout(resolve, 30))
    assert.equal(calls.length, 1, 'A cancelled switch must not show another save prompt every poll')
    command = { id: 2, workspace: second }
    await writeFile(bridgeFile, JSON.stringify({ url: 'http://127.0.0.1:4173', token: 'rotated-test-token' }))
    callbacks[0]!(); await new Promise((resolve) => setTimeout(resolve, 30))
    assert.equal(calls.length, 2, 'An explicit new mission-open action can retry the transition')
    assert.equal(headers.at(-1), 'rotated-test-token')
    subscriptions.forEach((subscription) => subscription.dispose())
    command = { id: 3, workspace: second }
    callbacks[0]!(); await new Promise((resolve) => setTimeout(resolve, 30))
    assert.equal(calls.length, 2)
  } finally { await rm(home, { recursive: true, force: true }) }
})
