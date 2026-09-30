import type { OtkApi } from '@shared/api'

declare global {
  interface Window {
    otk: OtkApi
  }
}

export const otk = (): OtkApi => window.otk

export interface UiError {
  code: string
  message: string
}

/** IPC errors arrive as "code::message" (see src/preload/index.ts). */
export function toUiError(e: unknown): UiError {
  const raw = e instanceof Error ? e.message : String(e)
  const cleaned = raw.replace(/^Error invoking remote method '[^']+': (Error: )?/, '')
  const m = /^([a-z_]+)::([\s\S]*)$/.exec(cleaned)
  return m ? { code: m[1], message: m[2] } : { code: 'internal', message: cleaned }
}

export const isCancelled = (e: unknown): boolean => toUiError(e).code === 'cancelled'

export function newJobId(prefix: string): string {
  return `${prefix}-${crypto.randomUUID()}`
}

export function basename(p: string): string {
  return p.split(/[\\/]/).pop() ?? p
}

export function dirname(p: string): string {
  const i = Math.max(p.lastIndexOf('/'), p.lastIndexOf('\\'))
  return i > 0 ? p.slice(0, i) : p
}
