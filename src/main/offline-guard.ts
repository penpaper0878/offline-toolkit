/**
 * Offline guarantee for the Electron side (docs/ARCHITECTURE.md §4).
 *
 * 1. Chromium switches: no proxy fallback, no background networking.
 * 2. session.webRequest: cancels every request that is not otk:, file:,
 *    data:, blob: or devtools: (plus the Vite dev server in development).
 * 3. Node guard: http/https/net/tls/dns entry points in the main process throw.
 * Every blocked attempt is counted and written to the event log.
 */

import dns from 'node:dns'
import http from 'node:http'
import https from 'node:https'
import net from 'node:net'
import tls from 'node:tls'
import { app, type Session } from 'electron'
import type { EventLog } from './log'

export interface Violation {
  ts: string
  layer: 'chromium' | 'node' | 'python'
  target: string
  /** A self-test's deliberate attempt (to CANARY_HOST), not something the app tried to do. */
  canary?: boolean
}

/** The host the offline self-test tries to reach from every runtime. */
export const CANARY_HOST = 'example.com'

const violations: Violation[] = []
let canaryArmed = false
let log: EventLog | null = null
const ALLOWED_SCHEMES = new Set(['otk:', 'file:', 'data:', 'blob:', 'devtools:', 'chrome-extension:'])

export function recordViolation(layer: Violation['layer'], target: string): void {
  const v: Violation = { ts: new Date().toISOString(), layer, target, ...(canaryArmed && target.includes(CANARY_HOST) ? { canary: true } : {}) }
  violations.push(v)
  log?.warn('offline-guard', `Blocked a network attempt (${layer}): ${target}`, v)
}

export function violationCount(): number {
  return violations.length
}

export function listViolations(): Violation[] {
  return [...violations]
}

/** Attempts the app itself made: everything except the self-tests' canaries. */
export function realViolations(): Violation[] {
  return violations.filter((v) => !v.canary)
}

/** From now on, attempts to CANARY_HOST are the self-test's own (they may be logged after the test returns). */
export function armCanary(): void {
  canaryArmed = true
}

/** Must run before app 'ready'. `devServer` is the Vite URL in development only. */
export function applyOfflineSwitches(devServer?: string): void {
  const sw = app.commandLine
  sw.appendSwitch('proxy-server', '127.0.0.1:9') // discard port: any direct fetch fails immediately
  sw.appendSwitch('proxy-bypass-list', devServer ? 'localhost;127.0.0.1' : '<-loopback>')
  sw.appendSwitch('disable-background-networking')
  sw.appendSwitch('disable-component-update')
  sw.appendSwitch('disable-domain-reliability')
  sw.appendSwitch('disable-breakpad')
  sw.appendSwitch('no-pings')
  sw.appendSwitch('disable-features', 'AutofillServerCommunication,OptimizationHints,MediaRouter,DialMediaRouteProvider,SafeBrowsing,NetworkTimeServiceQuerying')
}

export function guardSession(session: Session, devServer?: string): void {
  const devOrigin = devServer ? new URL(devServer).origin : null
  session.webRequest.onBeforeRequest({ urls: ['<all_urls>'] }, (details, callback) => {
    let allowed = false
    try {
      const u = new URL(details.url)
      allowed = ALLOWED_SCHEMES.has(u.protocol) || (devOrigin !== null && (u.origin === devOrigin || u.protocol === 'ws:' && u.host === new URL(devOrigin).host))
    } catch {
      allowed = false
    }
    if (!allowed) recordViolation('chromium', details.url)
    callback({ cancel: !allowed })
  })
  session.setPermissionRequestHandler((_wc, _perm, cb) => cb(false))
  session.setPermissionCheckHandler(() => false)
  session.setSpellCheckerEnabled(false)
  session.setSpellCheckerDictionaryDownloadURL('otk://blocked/')
}

function blocked(what: string): never {
  recordViolation('node', what)
  throw new Error(`Offline Toolkit blocks network access (${what})`)
}

function describe(args: unknown[]): string {
  const a = args[0]
  if (typeof a === 'string') return a
  if (a instanceof URL) return a.href
  if (a && typeof a === 'object') {
    const o = a as Record<string, unknown>
    return String(o.href ?? o.host ?? o.hostname ?? o.path ?? JSON.stringify(o))
  }
  return String(a)
}

/** Replace Node's network entry points in the main process. Local IPC pipes stay allowed. */
export function guardNode(eventLog: EventLog): void {
  log = eventLog
  const deny = (name: string) => (...args: unknown[]) => blocked(`${name} ${describe(args)}`)
  for (const mod of [http, https] as unknown as Record<string, unknown>[]) {
    mod.request = deny(mod === (https as unknown) ? 'https.request' : 'http.request')
    mod.get = deny(mod === (https as unknown) ? 'https.get' : 'http.get')
  }
  const realConnect = net.connect
  const netConnect = ((...args: unknown[]) => {
    const first = args[0] as { path?: string } | string | undefined
    const isPipe = (typeof first === 'object' && first !== null && typeof first.path === 'string') ||
      (typeof first === 'string' && isNaN(Number(first)))
    if (isPipe) return (realConnect as (...a: unknown[]) => net.Socket)(...args)
    return blocked(`net.connect ${describe(args)}`)
  }) as typeof net.connect
  ;(net as unknown as Record<string, unknown>).connect = netConnect
  ;(net as unknown as Record<string, unknown>).createConnection = netConnect
  ;(tls as unknown as Record<string, unknown>).connect = deny('tls.connect')
  for (const fn of ['lookup', 'resolve', 'resolve4', 'resolve6', 'resolveAny']) {
    ;(dns as unknown as Record<string, unknown>)[fn] = deny(`dns.${fn}`)
  }
}
