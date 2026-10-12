import { cp, mkdir, readFile, realpath, writeFile, lstat, mkdtemp, rename, rm, open, opendir } from 'node:fs/promises'
import { existsSync, constants } from 'node:fs'
import { execFile } from 'node:child_process'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { createHash, randomUUID } from 'node:crypto'
import { missionById } from '../shared/content.js'
import type { CheckResult, LanguageBand } from '../shared/types.js'
import { DomainError } from './store.js'
import { currentContractVersion } from '../shared/contracts.js'
import { requiredPassed } from '../shared/checks.js'

export const root = path.resolve(fileURLToPath(new URL('..', import.meta.url)))
export type SavedCodeContext = {
  source: 'saved-files-on-disk'
  workspace: string
  capturedAt: string
  visibility: { unsavedEditorBuffers: false; runningProcessState: false; terminalOutput: false }
  files: Record<string, { content: string; lastModifiedAt: string; truncated: boolean }>
  omittedFiles: string[]
  inventoryLimited: boolean
  limits: { files: number; charactersPerFile: number; totalCharacters: number }
}
export async function run(file: string, args: string[], cwd: string, timeout = 45000): Promise<{ code: number; stdout: string; stderr: string }> {
  return new Promise((resolve, reject) => {
    execFile(file, args, { cwd, timeout, maxBuffer: 256 * 1024, env: { PATH: process.env.PATH, HOME: cwd, TMPDIR: process.env.TMPDIR, LANG: 'en_US.UTF-8', PYTHONDONTWRITEBYTECODE: '1', DOCKER_HOST: process.env.DOCKER_HOST, DOCKER_CONTEXT: process.env.DOCKER_CONTEXT, DOCKER_CONFIG: process.env.DOCKER_CONFIG ?? path.join(process.env.HOME ?? '', '.docker') } }, (error, stdout, stderr) => {
      if (error && (error as NodeJS.ErrnoException).code === 'ENOENT') { reject(new DomainError(`${file} is not installed or not on PATH.`, 503)); return }
      if (error?.killed) { resolve({ code: 124, stdout, stderr: 'The lab exceeded its time or output limit.' }); return }
      resolve({ code: error ? Number(error.code) || 1 : 0, stdout, stderr })
    })
  })
}

export class Labs {
  constructor(readonly home: string) {}
  workspace(id: string) { missionById(id); return path.join(this.home, 'workspaces', id) }
  async context(id: string): Promise<SavedCodeContext> {
    const result: SavedCodeContext = { source: 'saved-files-on-disk', workspace: this.workspace(id), capturedAt: new Date().toISOString(), visibility: { unsavedEditorBuffers: false, runningProcessState: false, terminalOutput: false }, files: {}, omittedFiles: [], inventoryLimited: false, limits: { files: 20, charactersPerFile: 12000, totalCharacters: 64000 } }
    if (!existsSync(this.workspace(id))) return result
    const workspace = await this.assertOwned(id)
    const names: Record<string, string[]> = { signal: ['service.py'], vault: ['store.py'], gateway: ['nginx.conf', 'compose.yaml'], echo: ['ingest.py'], ledger: ['transform.py'], recovery: ['recover.py'], briefing: ['manifest.py', 'ticket.json'], capacity: ['capacity.py', 'workload.json'], contract: ['probe.py'], 'http-trial': ['service.py'] }
    const preferred = names[id] ?? missionById(id).files ?? []
    const candidates = new Set(preferred)
    const textTypes = new Set(['.py', '.sql', '.js', '.ts', '.tsx', '.jsx', '.go', '.rs', '.sh', '.json', '.yaml', '.yml', '.conf', '.toml', '.ini', '.md', '.txt', '.csv', '.html', '.css'])
    const excludedDirectories = new Set(['node_modules', '__pycache__', 'venv', 'env', 'dist', 'build'])
    let visited = 0
    async function visit(directory: string, depth: number) {
      for await (const entry of await opendir(directory)) {
        if (++visited > 200) { result.inventoryLimited = true; return }
        if (entry.name.startsWith('.') || entry.isSymbolicLink()) continue
        const file = path.join(directory, entry.name)
        if (entry.isDirectory() && !excludedDirectories.has(entry.name)) {
          if (depth < 3) await visit(file, depth + 1)
          else result.inventoryLimited = true
        }
        if (!entry.isFile()) continue
        const extension = path.extname(entry.name).toLowerCase()
        if (!textTypes.has(extension) && !['Dockerfile', 'Makefile'].includes(entry.name)) continue
        if (/^(?:auth|credentials?|secrets?|tokens?)(?:[._-]|$)/i.test(entry.name) && ['.json', '.yaml', '.yml', '.toml', '.ini', '.txt'].includes(extension)) continue
        if (['package-lock.json', 'npm-shrinkwrap.json'].includes(entry.name)) continue
        candidates.add(path.relative(workspace, file))
      }
    }
    await visit(workspace, 0)
    const ordered = [...candidates].sort((a, b) => {
      const aRank = preferred.includes(a) ? preferred.indexOf(a) : 100
      const bRank = preferred.includes(b) ? preferred.indexOf(b) : 100
      return aRank - bRank || a.localeCompare(b)
    })
    let remaining = result.limits.totalCharacters
    for (const name of ordered) {
      if (Object.keys(result.files).length >= result.limits.files || remaining <= 0) { result.omittedFiles.push(name); continue }
      const file = path.join(workspace, name)
      if (existsSync(file) && (await lstat(file)).isFile()) {
        const handle = await open(file, constants.O_RDONLY | constants.O_NOFOLLOW)
        try {
          const metadata = await handle.stat()
          const buffer = Buffer.alloc(Math.min(metadata.size, 48001))
          const { bytesRead } = await handle.read(buffer, 0, buffer.length, 0)
          if (buffer.subarray(0, bytesRead).includes(0)) { result.omittedFiles.push(name); continue }
          const text = buffer.subarray(0, bytesRead).toString('utf8')
          const content = text.slice(0, Math.min(remaining, result.limits.charactersPerFile))
          result.files[name] = { content, lastModifiedAt: metadata.mtime.toISOString(), truncated: metadata.size > bytesRead || text.length > content.length }
          remaining -= content.length
        } finally { await handle.close() }
      }
    }
    return result
  }
  async assertOwned(id: string) {
    const workspace = this.workspace(id)
    const resolved = await realpath(workspace)
    const base = await realpath(path.join(this.home, 'workspaces'))
    if (resolved !== path.join(base, id)) throw new DomainError('The workspace path no longer belongs to this mission.', 409)
    const marker = JSON.parse(await readFile(path.join(workspace, '.rankforge-mission.json'), 'utf8'))
    if (marker.mission !== id || marker.version !== 1) throw new DomainError('The workspace marker does not match the mission.', 409)
    return workspace
  }
  async prepare(id: string, band: LanguageBand) {
    const mission = missionById(id)
    const workspace = this.workspace(id)
    await mkdir(path.join(this.home, 'workspaces'), { recursive: true })
    if (existsSync(workspace)) return this.assertOwned(id)
    const temporaryRoot = await mkdtemp(path.join(this.home, 'workspaces', `.preparing-${id}-`))
    const staging = path.join(temporaryRoot, 'workspace')
    try {
      await cp(path.join(root, 'labs', id), staging, { recursive: true, errorOnExist: true, force: false })
      await writeFile(path.join(staging, '.rankforge-mission.json'), JSON.stringify({ mission: id, version: 1 }), { flag: 'wx' })
      if (id === 'gateway') {
        const compose = await readFile(path.join(staging, 'compose.yaml'), 'utf8')
        const project = `rankforge-gateway-${createHash('sha256').update(workspace).digest('hex').slice(0, 8)}`
        await writeFile(path.join(staging, 'compose.yaml'), `name: ${project}\n${compose}`)
      }
      const markdown = `# ${mission.title}\n\n${mission.briefs[band]}\n\n## Learn\n\n${mission.lesson}\n\n[Open the field manual](LEARN.md) for concepts, investigation steps and Python/terminal guidance.\n\n## Acceptance contract\n\n${mission.objectives.map((item) => `- ${item}`).join('\n')}\n\n## Terminal starting points\n\n\`\`\`sh\n${mission.commands.join('\n')}\n\`\`\`\n\n## Debrief\n\n${mission.prompt}\n\n## References\n\n${mission.sources.map((item) => `- [${item.title}](${item.url})`).join('\n')}\n\nSave your files, then use **Verify lab** in Rankforge. Checks run your Python code locally as your user; only run code you trust. Your previous mission folders are preserved.\n`
      await writeFile(path.join(staging, 'MISSION.md'), markdown, { flag: 'wx' })
      try { await rename(staging, workspace) }
      catch (error) { if (!existsSync(workspace)) throw error; return this.assertOwned(id) }
      return workspace
    } finally { await rm(temporaryRoot, { recursive: true, force: true }) }
  }
  // Reset never deletes: the whole workspace is renamed into .backups first, then the starter is prepared again at the same path.
  async reset(id: string, band: LanguageBand): Promise<{ backup: string; workspace: string }> {
    const workspace = this.workspace(id)
    if (!existsSync(workspace)) throw new DomainError('There is no workspace to reset yet. Prepare the workspace first.', 409)
    await this.assertOwned(id)
    const backups = path.join(this.home, 'workspaces', '.backups')
    await mkdir(backups, { recursive: true })
    let backup = path.join(backups, `${id}-${new Date().toISOString().replace(/:/g, '-')}`)
    for (let attempt = 1; existsSync(backup); attempt++) backup = `${backup}-${attempt}`
    await rename(workspace, backup)
    try { await this.prepare(id, band) }
    catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      try { await rename(backup, workspace) }
      catch { throw new DomainError(`The starter could not be restored (${message}) and your files could not be moved back. They are intact at ${backup}.`, 500) }
      throw new DomainError(`The starter could not be restored (${message}). Your files were moved back unchanged.`, 500)
    }
    return { backup, workspace }
  }
  async check(id: string): Promise<CheckResult> {
    return { ...await this.runCheck(id), contractVersion: currentContractVersion }
  }
  private async runCheck(id: string): Promise<CheckResult> {
    const checkedAt = new Date().toISOString()
    try {
      const workspace = await this.assertOwned(id)
      if (id === 'gateway') return this.checkGateway(workspace, checkedAt)
      for (const name of ['service.py', 'store.py', 'ingest.py', 'transform.py', 'recover.py', 'manifest.py', 'capacity.py', 'probe.py', ...(missionById(id).files ?? [])]) {
        const file = path.join(workspace, name)
        if (existsSync(file) && (await lstat(file)).isSymbolicLink()) throw new DomainError('Lab source must be a regular file inside the workspace.', 409)
      }
      const verifier = ['briefing', 'capacity', 'contract'].includes(id) ? 'verify_architect.py' : existsSync(path.join(root, 'server', `verify_${id.replaceAll('-', '_')}.py`)) ? `verify_${id.replaceAll('-', '_')}.py` : 'verify.py'
      const result = await run('python3', ['-I', '-B', path.join(root, 'server', verifier), id, workspace], workspace)
      let parsed: { checks: CheckResult['checks'] }
      try { parsed = JSON.parse(result.stdout.trim().split('\n').at(-1) ?? '') } catch { return { passed: false, supported: true, checkedAt, checks: [{ name: 'Run the lab', passed: false, detail: result.stderr || result.stdout || 'No valid check report was produced.' }], output: result.stderr } }
      if (!Array.isArray(parsed.checks) || !parsed.checks.length) throw new Error('Invalid check report')
      const supported = !parsed.checks.some((item) => item.name === 'Environment blocked')
      return { passed: supported && result.code === 0 && requiredPassed(parsed.checks), checks: parsed.checks, checkedAt, supported, output: result.stderr.slice(0, 6000) }
    } catch (error) {
      return { passed: false, supported: false, checkedAt, checks: [], output: error instanceof DomainError ? error.message : 'The workspace could not be checked. Reopen the mission and try again.' }
    }
  }
  private async checkGateway(workspace: string, checkedAt: string): Promise<CheckResult> {
    const port = await run('docker', ['compose', 'port', 'gateway', '8080'], workspace)
    const address = port.stdout.trim()
    if (port.code || !/^127\.0\.0\.1:\d+$/.test(address)) return { passed: false, supported: false, checkedAt, checks: [], output: 'Start the supplied gateway project with docker compose up -d. Its port must be bound to 127.0.0.1. If 45103 is busy, use GATEWAY_PORT=45113 docker compose up -d.' }
    const checks: CheckResult['checks'] = []
    const config = await run('docker', ['compose', 'exec', '-T', 'gateway', 'nginx', '-t'], workspace)
    checks.push({ name: 'nginx configuration is valid', passed: config.code === 0, detail: (config.stderr || config.stdout).slice(0, 2000) })
    const probe = `rankforge-${randomUUID()}`
    const forwarded = [`/health?probe=${probe}&check=health`, `/missing?probe=${probe}&check=unknown`]
    for (const route of ['/api/health', `/api${forwarded[0]}`, '/missing', '/missing?next=/health', `/api${forwarded[1]}`, '/api/healthcheck', '/api/health/extra']) {
      try {
        const response = await fetch(`http://${address}${route}`, { signal: AbortSignal.timeout(5000), redirect: 'manual' })
        const body = await response.text()
        const healthy = route.split('?')[0] === '/api/health'
        let valid = false
        try { const json = JSON.parse(body); valid = json.status === 'ok' && json.service === 'relay' } catch { /* An nginx error page is evidence of a broken route. */ }
        const mediaType = (response.headers.get('content-type') ?? '').split(';')[0]!.trim().toLowerCase()
        checks.push({ name: `GET ${route}`, passed: healthy ? response.status === 200 && valid && mediaType === 'application/json' : response.status === 404, detail: `HTTP ${response.status}: ${body.slice(0, 180)}` })
      } catch { checks.push({ name: `GET ${route}`, passed: false, detail: 'Gateway did not respond within five seconds.' }) }
    }
    if (config.code === 0 && checks.some((item) => !item.passed)) {
      const hint = ' The nginx configuration test passed. If you edited nginx.conf after starting the project, run: docker compose exec gateway nginx -s reload, then verify again.'
      for (const item of checks) if (!item.passed) item.detail += hint
    }
    // Hidden bonus: the bare prefix /api/ must reach the relay as / with its query, where the relay answers 404.
    const bare = `/?probe=${probe}&check=bare`
    let bareDetail = 'Gateway did not respond within five seconds.'
    let bareStatus = 0
    try {
      const response = await fetch(`http://${address}/api${bare}`, { signal: AbortSignal.timeout(5000), redirect: 'manual' })
      bareStatus = response.status
      bareDetail = `HTTP ${response.status}: ${(await response.text()).slice(0, 180)}`
    } catch { /* The missing response is the evidence. */ }
    const upstream = await run('docker', ['compose', 'logs', '--no-color', '--tail', '100', 'relay'], workspace)
    const log = `${upstream.stdout}\n${upstream.stderr}`
    checks.push({ name: 'Known and unknown API paths reach the relay with queries preserved', passed: upstream.code === 0 && forwarded.every((route) => log.includes(`GET ${route} `)), detail: upstream.code === 0 ? 'Checked the relay log for both unique requests, with /api/ removed and query parameters intact.' : 'The relay log could not be read.' })
    const bareForwarded = upstream.code === 0 && log.includes(`GET ${bare} `)
    checks.push({ name: 'bonus: GET /api/ with a query reaches the relay as / and returns its 404', optional: true, passed: bareStatus === 404 && bareForwarded, detail: `${bareDetail} ${bareForwarded ? 'The relay log shows the bare path with its query intact.' : 'The relay log does not show GET / with that query.'}` })
    return { passed: requiredPassed(checks), checks, checkedAt, supported: true, output: '' }
  }
}
