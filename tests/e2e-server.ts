import { mkdtemp, rm } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { createApp } from '../server/app.js'

const home = await mkdtemp(path.join(os.tmpdir(), 'rankforge-e2e-'))
const { app } = await createApp({ home, port: 4197, launchEditor: async () => { /* Headless acceptance never opens the owner's editor. */ } })
await app.listen({ host: '127.0.0.1', port: 4197 })
for (const signal of ['SIGTERM', 'SIGINT'] as const) process.once(signal, () => { void app.close().then(() => rm(home, { recursive: true, force: true })).then(() => process.exit(0)) })
