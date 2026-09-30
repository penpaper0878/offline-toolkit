/**
 * Offline self-test (Help → Offline self-test).
 *
 * Deliberately tries to reach a public host from every runtime and passes only
 * if every attempt is blocked and recorded. It also reports any network
 * attempt made since the app started. See docs/ARCHITECTURE.md §4 for what
 * this can and cannot prove.
 */

import https from 'node:https'
import { type BrowserWindow, net } from 'electron'
import type { SelfTestCheck, SelfTestReport } from '@shared/types'
import { listViolations, violationCount } from './offline-guard'
import type { WorkerPool } from './worker'

const CANARY = 'https://example.com/'

async function check(name: string, fn: () => Promise<{ passed: boolean; detail: string }>): Promise<SelfTestCheck> {
  try {
    return { name, ...(await fn()) }
  } catch (e) {
    return { name, passed: false, detail: `Test error: ${(e as Error).message}` }
  }
}

export async function runOfflineSelfTest(pool: WorkerPool, win: BrowserWindow | null): Promise<SelfTestReport> {
  const before = violationCount()
  const earlier = listViolations()
  const checks: SelfTestCheck[] = []

  checks.push(await check('Main process (Node https)', async () => {
    try {
      https.get(CANARY)
      return { passed: false, detail: 'A request was started — the Node guard is not active.' }
    } catch (e) {
      return { passed: true, detail: `Blocked: ${(e as Error).message}` }
    }
  }))

  checks.push(await check('Main process (Chromium network stack)', async () => {
    try {
      await net.fetch(CANARY)
      return { passed: false, detail: 'example.com answered — Chromium requests are not blocked.' }
    } catch (e) {
      return { passed: true, detail: `Blocked: ${(e as Error).message}` }
    }
  }))

  if (win && !win.isDestroyed()) {
    checks.push(await check('User interface (renderer fetch)', async () => {
      const out: string = await win.webContents.executeJavaScript(
        `fetch(${JSON.stringify(CANARY)}, {mode: 'no-cors'}).then(() => 'reached', (e) => 'blocked: ' + e.message)`, true)
      return { passed: out.startsWith('blocked'), detail: out }
    }))
  }

  checks.push(await check('Python worker (socket/DNS)', async () => {
    const r = await pool.interactive.request<{ blocked: boolean; error: string | null; installed: boolean }>('selftest.canary', {}, 30_000)
    return { passed: r.blocked && r.installed, detail: r.blocked ? `Blocked: ${r.error}` : `Not blocked: ${r.error ?? 'connection attempted'}` }
  }))

  // Give the Python stderr line a moment to arrive and be counted.
  await new Promise((r) => setTimeout(r, 300))
  const after = violationCount()
  checks.push({
    name: 'Blocked attempts were recorded',
    passed: after - before >= checks.filter((c) => c.passed).length,
    detail: `${after - before} attempt(s) recorded during this test.`
  })
  checks.push({
    name: 'No other network attempts since start-up',
    passed: earlier.length === 0,
    detail: earlier.length === 0 ? 'None.' : `${earlier.length} earlier attempt(s): ${earlier.slice(0, 5).map((v) => `${v.layer} ${v.target}`).join(', ')}`
  })
  return { passed: checks.every((c) => c.passed), checks, violationsBefore: before, violationsAfter: after }
}
