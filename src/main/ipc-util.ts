/**
 * Shared by the main process's IPC modules: the handler wrapper that carries errors to the window intact,
 * the validation error, and atomic JSON writes.
 */

import { mkdir, rename, writeFile } from 'node:fs/promises'
import { dirname } from 'node:path'
import { ipcMain } from 'electron'
import type { EventLog } from './log'
import { WorkerError } from './worker'

export type Result<T> = { ok: true; value: T } | { ok: false; error: { message: string; code: string } }

/** A user's JSON file (settings, presets) that does not match its schema. */
export class ValidationError extends Error {
  constructor(message: string, public details: string[]) {
    super(message)
  }
}

export function toError(e: unknown): { message: string; code: string } {
  if (e instanceof WorkerError) return { message: e.message, code: e.code }
  if (e instanceof ValidationError) return { message: e.message, code: 'validation' }
  return { message: (e as Error)?.message ?? String(e), code: 'internal' }
}

/** Every handler returns {ok, value} | {ok: false, error} so messages reach the UI intact; failures are logged
 * under the channel's area ("design" for design:export). */
export function handle<A extends unknown[], T>(channel: string, fn: (...args: A) => Promise<T> | T, log: EventLog,
  area = channel.split(':')[0]): void {
  ipcMain.handle(channel, async (_event, ...args: unknown[]): Promise<Result<T>> => {
    try {
      return { ok: true, value: await fn(...(args as A)) }
    } catch (e) {
      const error = toError(e)
      if (error.code !== 'cancelled') log.warn(area, `${channel}: ${error.message}`, { code: error.code })
      return { ok: false, error }
    }
  })
}

/** Write JSON through a temporary file, so a crash never leaves half a file. */
export async function writeJsonAtomic(path: string, data: unknown): Promise<void> {
  await mkdir(dirname(path), { recursive: true })
  const tmp = `${path}.${process.pid}.${Math.random().toString(36).slice(2, 8)}.tmp`
  await writeFile(tmp, JSON.stringify(data, null, 2) + '\n', 'utf-8')
  await rename(tmp, path)
}
