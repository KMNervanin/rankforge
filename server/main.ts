import os from 'node:os'
import path from 'node:path'
import { createApp } from './app.js'
import { claimInstance } from './instance.js'

const home = path.resolve(process.env.RANKFORGE_HOME ?? path.join(os.homedir(), '.local', 'share', 'rankforge'))
const port = Number(process.env.RANKFORGE_PORT ?? 4173)
if (!Number.isInteger(port) || port < 1024 || port > 65535) throw new Error('RANKFORGE_PORT must be an integer from 1024 to 65535.')
const release = await claimInstance(home)
const { app } = await createApp({ home, port }).catch(async (error) => { await release(); throw error })
app.addHook('onClose', release)
try {
  await app.listen({ host: '127.0.0.1', port })
  console.log(`Rankforge is ready at http://127.0.0.1:${port}\nProgress: ${home}\nNo browser or sign-in is opened automatically.`)
} catch (error) { console.error(error instanceof Error ? error.message : 'Unable to start Rankforge'); await app.close(); process.exitCode = 1 }
for (const signal of ['SIGINT', 'SIGTERM'] as const) process.once(signal, () => { void app.close().then(() => process.exit(0)) })
