/**
 * Recent work across the modules (the home screen's list): files opened in the resizer, the converter and
 * the passport wizard, and designs. Kept in <data>/recent.json, at most 20 entries, newest first. Nothing is
 * kept when "Remember recent files" is off; clearing removes the file's entries.
 */

import { existsSync } from 'node:fs'
import { readFile } from 'node:fs/promises'
import { join } from 'node:path'
import { IPC } from '@shared/api'
import { addRecent, MODULES, type ModuleId, type RecentEntry, type RecentItem, removeRecent, validRecent } from '@shared/home'
import { handle, writeJsonAtomic } from './ipc-util'
import type { EventLog } from './log'
import { dataDir, designsDir } from './paths'
import type { Store } from './store'
import { WorkerError } from './worker'

const file = (): string => join(dataDir(), 'recent.json')

let items: RecentItem[] | null = null
let queue: Promise<unknown> = Promise.resolve()

async function load(): Promise<RecentItem[]> {
  if (items) return items
  try {
    items = validRecent(JSON.parse(await readFile(file(), 'utf-8')))
  } catch {
    items = []                               // missing or unreadable: start empty (the file is rewritten on the next add)
  }
  return items
}

/** Writes run one at a time, in order. */
function save(next: RecentItem[]): Promise<void> {
  items = next
  const p = queue.then(() => writeJsonAtomic(file(), { version: 1, items: next }))
  queue = p.catch(() => undefined)
  return p
}

function available(r: RecentItem): boolean {
  if (r.module === 'design' && r.ref) return /^[a-f0-9-]{8,64}$/i.test(r.ref) && existsSync(join(designsDir(), r.ref))
  return r.paths.some((p) => existsSync(p))
}

function checkItem(v: unknown): RecentItem {
  const [item] = validRecent({ items: [v] })
  if (!item) throw new WorkerError('Not a recent item.', 'input')
  if (!MODULES.includes(item.module as ModuleId)) throw new WorkerError('Unknown module.', 'input')
  return item
}

export function registerRecentIpc({ store, log }: { store: Store; log: EventLog }): void {
  handle(IPC.recentList, async (): Promise<RecentEntry[]> => {
    if (!store.getSettings().home?.rememberRecent) return []
    return (await load()).map((r) => ({ ...r, available: available(r) }))
  }, log)

  handle(IPC.recentAdd, async (v: unknown): Promise<void> => {
    if (!store.getSettings().home?.rememberRecent) return
    const item = checkItem({ ...(v as object), at: new Date().toISOString() })
    await save(addRecent(await load(), item))
  }, log)

  handle(IPC.recentRemove, async (v: unknown): Promise<void> => {
    const item = checkItem({ ...(v as object), at: new Date().toISOString() })
    await save(removeRecent(await load(), item))
  }, log)

  handle(IPC.recentClear, async (): Promise<void> => {
    await save([])
    log.info('home', 'Recent files cleared')
  }, log)
}
