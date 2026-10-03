import { cp, mkdir, readFile, realpath, writeFile, lstat, mkdtemp, rename, rm } from 'node:fs/promises'
import { existsSync } from 'node:fs'
import { execFile } from 'node:child_process'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { createHash, randomUUID } from 'node:crypto'
import { missionById } from '../shared/content.js'
import type { CheckResult, LanguageBand } from '../shared/types.js'
import { DomainError } from './store.js'

export const root = path.resolve(fileURLToPath(new URL('..', import.meta.url)))
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
  async context(id: string): Promise<Record<string, string>> {
    if (!existsSync(this.workspace(id))) return {}
    const workspace = await this.assertOwned(id)
    const names: Record<string, string[]> = { signal: ['service.py'], vault: ['store.py'], gateway: ['nginx.conf', 'compose.yaml'], echo: ['ingest.py'], ledger: ['transform.py'], recovery: ['recover.py'] }
    const result: Record<string, string> = {}
    for (const name of names[id] ?? []) {
      const file = path.join(workspace, name)
      if (existsSync(file) && (await lstat(file)).isFile()) result[name] = (await readFile(file, 'utf8')).slice(0, 12000)
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
  async check(id: string): Promise<CheckResult> {
    const checkedAt = new Date().toISOString()
    try {
      const workspace = await this.assertOwned(id)
      if (id === 'gateway') return this.checkGateway(workspace, checkedAt)
      for (const name of ['service.py', 'store.py', 'ingest.py', 'transform.py', 'recover.py']) {
        const file = path.join(workspace, name)
        if (existsSync(file) && (await lstat(file)).isSymbolicLink()) throw new DomainError('Lab source must be a regular file inside the workspace.', 409)
      }
      const result = await run('python3', ['-I', '-B', path.join(root, 'server', 'verify.py'), id, workspace], workspace)
      let parsed: { checks: CheckResult['checks'] }
      try { parsed = JSON.parse(result.stdout.trim().split('\n').at(-1) ?? '') } catch { return { passed: false, supported: true, checkedAt, checks: [{ name: 'Run the lab', passed: false, detail: result.stderr || result.stdout || 'No valid check report was produced.' }], output: result.stderr } }
      if (!Array.isArray(parsed.checks) || !parsed.checks.length) throw new Error('Invalid check report')
      return { passed: result.code === 0 && parsed.checks.every((item) => item.passed), checks: parsed.checks, checkedAt, supported: true, output: result.stderr.slice(0, 6000) }
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
    for (const route of ['/api/health', `/api/health?probe=${probe}`, '/missing']) {
      try {
        const response = await fetch(`http://${address}${route}`, { signal: AbortSignal.timeout(5000), redirect: 'manual' })
        const body = await response.text()
        const healthy = route.startsWith('/api/')
        let valid = false
        try { const json = JSON.parse(body); valid = json.status === 'ok' && json.service === 'relay' } catch { /* An nginx error page is evidence of a broken route. */ }
        checks.push({ name: `GET ${route}`, passed: healthy ? response.status === 200 && valid && (response.headers.get('content-type') ?? '').includes('application/json') : response.status === 404, detail: `HTTP ${response.status}: ${body.slice(0, 180)}` })
      } catch { checks.push({ name: `GET ${route}`, passed: false, detail: 'Gateway did not respond within five seconds.' }) }
    }
    const upstream = await run('docker', ['compose', 'logs', '--no-color', '--tail', '100', 'relay'], workspace)
    checks.push({ name: 'Request really reaches the relay with /api/ removed', passed: upstream.code === 0 && `${upstream.stdout}\n${upstream.stderr}`.includes(`GET /health?probe=${probe} `), detail: upstream.code === 0 ? 'Checked the relay log for this verification’s unique request identifier.' : 'The relay log could not be read.' })
    return { passed: checks.every((item) => item.passed), checks, checkedAt, supported: true, output: '' }
  }
}
