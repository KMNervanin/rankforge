import * as vscode from 'vscode'
import { readFile } from 'node:fs/promises'
import path from 'node:path'

export async function activate(context: vscode.ExtensionContext) {
  const folder = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath
  if (!folder) return
  let connection: { bridgeFile: string }
  try {
    const marker = JSON.parse(await readFile(path.join(folder, '.rankforge-mission.json'), 'utf8'))
    if (marker.version !== 1) return
    connection = JSON.parse(await readFile(path.join(folder, '.rankforge-connection.json'), 'utf8'))
  } catch { return }
  const status = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 20)
  status.text = '$(radio-tower) Rankforge'; status.command = 'rankforge.openBriefing'; status.show()
  const briefing = async () => {
    const document = await vscode.workspace.openTextDocument(vscode.Uri.file(path.join(folder, 'MISSION.md')))
    await vscode.window.showTextDocument(document, { preview: false })
  }
  context.subscriptions.push(status, vscode.commands.registerCommand('rankforge.openBriefing', briefing))
  let disposed = false; let polling = false; let attempted = 0
  const poll = async () => {
    if (disposed || polling) return
    polling = true
    try {
      // Reread after service restart because the local bridge token rotates.
      const config = JSON.parse(await readFile(connection.bridgeFile, 'utf8')) as { url: string; token: string }
      const endpoint = new URL(config.url)
      if (endpoint.protocol !== 'http:' || !['127.0.0.1', 'localhost'].includes(endpoint.hostname)) throw new Error('Nonlocal bridge')
      const headers = { 'x-rankforge-bridge': config.token, 'Content-Type': 'application/json' }
      const response = await fetch(`${config.url}/api/editor/poll`, { headers, signal: AbortSignal.timeout(3000) })
      if (!response.ok) throw new Error('Bridge unavailable')
      const { command } = await response.json() as { command: { id: number; workspace: string } | null }
      status.text = '$(radio-tower) Rankforge connected'
      if (!command) return
      if (path.resolve(command.workspace) === path.resolve(folder)) {
        await fetch(`${config.url}/api/editor/ack`, { method: 'POST', headers, body: JSON.stringify({ id: command.id }), signal: AbortSignal.timeout(3000) })
        return
      }
      if (command.id === attempted) return
      const marker = JSON.parse(await readFile(path.join(command.workspace, '.rankforge-mission.json'), 'utf8'))
      if (marker.version !== 1 || path.dirname(command.workspace) !== path.dirname(folder)) throw new Error('Invalid mission workspace')
      attempted = command.id
      // Run in this extension host, never target the globally last-active editor window.
      await vscode.commands.executeCommand('vscode.openFolder', vscode.Uri.file(command.workspace), { forceReuseWindow: true })
    } catch { status.text = '$(radio-tower) Rankforge offline' }
    finally { polling = false }
  }
  const timer = setInterval(() => { void poll() }, 1500)
  context.subscriptions.push({ dispose: () => { disposed = true; clearInterval(timer) } })
  await briefing()
  await poll()
}
