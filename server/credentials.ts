import { execFile, spawn } from 'node:child_process'
import { promisify } from 'node:util'
import { createHash } from 'node:crypto'
import { existsSync, writeFileSync, unlinkSync } from 'node:fs'
import path from 'node:path'

export type Credential = { access: string; refresh: string; expires: number; accountId?: string }
export interface Credentials { has(): boolean; read(): Promise<Credential | null>; write(value: Credential): Promise<void>; clear(): Promise<void> }
const exec = promisify(execFile)

export class SystemCredentials implements Credentials {
  private readonly marker: string
  private readonly service: string
  constructor(home: string) {
    this.marker = path.join(home, 'account-linked')
    this.service = `rankforge.${createHash('sha256').update(home).digest('hex').slice(0, 16)}`
  }
  has() { return existsSync(this.marker) }
  async read(): Promise<Credential | null> {
    if (!this.has()) return null
    const result = process.platform === 'darwin'
      ? await exec('security', ['find-generic-password', '-a', 'rankforge', '-s', this.service, '-w'])
      : await exec('secret-tool', ['lookup', 'application', this.service])
    return JSON.parse(result.stdout) as Credential
  }
  async write(value: Credential) {
    const serialized = JSON.stringify(value)
    if (process.platform === 'darwin') await exec('security', ['add-generic-password', '-U', '-a', 'rankforge', '-s', this.service, '-w', serialized])
    else await new Promise<void>((resolve, reject) => {
      const child = spawn('secret-tool', ['store', '--label=Rankforge ChatGPT', 'application', this.service], { stdio: ['pipe', 'ignore', 'ignore'] })
      child.on('error', reject)
      child.on('close', (code) => code === 0 ? resolve() : reject(new Error('Secret Service could not store the account.')))
      child.stdin.end(serialized)
    })
    writeFileSync(this.marker, 'Credentials are stored in the operating system credential store.\n', { mode: 0o600 })
  }
  async clear() {
    if (!this.has()) return
    if (process.platform === 'darwin') await exec('security', ['delete-generic-password', '-a', 'rankforge', '-s', this.service])
    else await exec('secret-tool', ['clear', 'application', this.service])
    unlinkSync(this.marker)
  }
}
