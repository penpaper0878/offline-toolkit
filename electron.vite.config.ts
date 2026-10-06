import { resolve } from 'node:path'
import { defineConfig } from 'electron-vite'
import type { Plugin } from 'vite'
import react from '@vitejs/plugin-react'

const shared = { '@shared': resolve(__dirname, 'src/shared') }

/** Writes bundled-packages.json: the npm packages whose code ended up in this bundle (scripts/collect_licenses.py). */
function bundledPackages(): Plugin {
  return {
    name: 'otk-bundled-packages',
    generateBundle() {
      const names = new Set<string>()
      for (const id of this.getModuleIds()) {
        const m = /[\\/]node_modules[\\/]((?:@[^\\/]+[\\/])?[^\\/]+)/.exec(id.split('?')[0])
        if (m && this.getModuleInfo(id)?.code != null) names.add(m[1].replace(/\\/g, '/'))
      }
      this.emitFile({ type: 'asset', fileName: 'bundled-packages.json', source: JSON.stringify([...names].sort(), null, 1) })
    }
  }
}

export default defineConfig({
  main: {
    resolve: { alias: shared },
    plugins: [bundledPackages()],
    build: { outDir: 'out/main' }
  },
  preload: {
    resolve: { alias: shared },
    plugins: [bundledPackages()],
    build: { outDir: 'out/preload' }
  },
  renderer: {
    root: 'src/renderer',
    base: './',
    resolve: { alias: { ...shared, '@renderer': resolve(__dirname, 'src/renderer/src') } },
    plugins: [react(), bundledPackages()],
    build: { outDir: resolve(__dirname, 'out/renderer'), rollupOptions: { input: resolve(__dirname, 'src/renderer/index.html') } }
  }
})
