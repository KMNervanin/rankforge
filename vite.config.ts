import { defineConfig } from 'vite'

export default defineConfig({
  server: { port: 4174, strictPort: true, proxy: { '/api': 'http://127.0.0.1:4173' } },
  build: { outDir: 'dist', sourcemap: true },
})
