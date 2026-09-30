import { createHash } from 'node:crypto'
import { appendFile, mkdir, readdir, stat, unlink } from 'node:fs/promises'
import { join } from 'node:path'
import type { LogEntry, LogLevel } from '@shared/types'

const KEEP_IN_MEMORY = 1000
const KEEP_DAYS = 30
const PATHISH = /(?:[A-Za-z]:\\|\/)[^\s"']+/g

/** Event log: JSON Lines per day on disk, the latest entries in memory for the UI. */
export class EventLog {
  private entries: LogEntry[] = []
  private listeners = new Set<(e: LogEntry) => void>()
  private queue: Promise<void> = Promise.resolve()
  hashPaths = false

  constructor(private dir: string) {}

  async init(): Promise<void> {
    await mkdir(this.dir, { recursive: true })
    const cutoff = Date.now() - KEEP_DAYS * 86_400_000
    for (const name of await readdir(this.dir)) {
      const p = join(this.dir, name)
      try {
        if (name.endsWith('.jsonl') && (await stat(p)).mtimeMs < cutoff) await unlink(p)
      } catch {
        /* ignore */
      }
    }
  }

  private scrub(text: string): string {
    if (!this.hashPaths) return text
    return text.replace(PATHISH, (m) => `<path:${createHash('sha256').update(m).digest('hex').slice(0, 10)}>`)
  }

  add(level: LogLevel, source: string, message: string, data?: unknown): LogEntry {
    const entry: LogEntry = { ts: new Date().toISOString(), level, source, message: this.scrub(message) }
    if (data !== undefined) entry.data = JSON.parse(this.scrub(JSON.stringify(data)))
    this.entries.push(entry)
    if (this.entries.length > KEEP_IN_MEMORY) this.entries.splice(0, this.entries.length - KEEP_IN_MEMORY)
    const file = join(this.dir, `${entry.ts.slice(0, 10)}.jsonl`)
    const line = JSON.stringify(entry) + '\n'
    this.queue = this.queue.then(() => appendFile(file, line, 'utf-8')).catch(() => undefined)
    for (const l of this.listeners) l(entry)
    if (level === 'error') console.error(`[${source}] ${message}`)
    return entry
  }

  info(source: string, message: string, data?: unknown): void {
    this.add('info', source, message, data)
  }

  warn(source: string, message: string, data?: unknown): void {
    this.add('warn', source, message, data)
  }

  error(source: string, message: string, data?: unknown): void {
    this.add('error', source, message, data)
  }

  recent(): LogEntry[] {
    return [...this.entries]
  }

  onEntry(cb: (e: LogEntry) => void): () => void {
    this.listeners.add(cb)
    return () => this.listeners.delete(cb)
  }

  flush(): Promise<void> {
    return this.queue
  }
}
