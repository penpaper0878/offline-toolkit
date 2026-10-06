/**
 * An editable list of presets in a JSON file (passport specs, paper sizes), like presets/resizer.json:
 * the shipped list is copied to <data>/presets/<name>.json on first run; new shipped items arrive with
 * updates unless the user deleted them; an invalid user file is reported and the shipped list is used,
 * and the user's file is never overwritten until it is valid again.
 */

import { existsSync } from 'node:fs'
import { mkdir, readFile, rename, writeFile } from 'node:fs/promises'
import { dirname, join } from 'node:path'
import type { ValidateFunction } from 'ajv/dist/2020'
import type { EventLog } from './log'

export interface ListState<T> {
  items: T[]
  defaultIds: string[]
  error: string | null
  file: string
}

type Doc<T> = { $schema?: string; version: 1; deletedDefaults?: string[] } & Record<string, unknown> & { [k: string]: T[] | unknown }

async function writeJsonAtomic(path: string, data: unknown): Promise<void> {
  await mkdir(dirname(path), { recursive: true })
  const tmp = `${path}.${process.pid}.tmp`
  await writeFile(tmp, JSON.stringify(data, null, 2) + '\n', 'utf-8')
  await rename(tmp, path)
}

export class ListFile<T extends { id: string }> {
  private doc!: Doc<T>
  private shipped!: Doc<T>
  private error: string | null = null

  constructor(private name: string, private key: string, private resourcesDir: string, private dataDir: string,
    private validate: ValidateFunction, private log: EventLog) {}

  get file(): string {
    return join(this.dataDir, 'presets', `${this.name}.json`)
  }

  private items(d: Doc<T>): T[] {
    return (d[this.key] as T[]) ?? []
  }

  async init(): Promise<void> {
    this.shipped = JSON.parse(await readFile(join(this.resourcesDir, 'defaults', 'presets', `${this.name}.json`), 'utf-8'))
    if (!existsSync(this.file)) await writeJsonAtomic(this.file, { ...this.shipped, $schema: undefined })
    try {
      const data = JSON.parse(await readFile(this.file, 'utf-8')) as Doc<T>
      if (!this.validate(data)) {
        const details = (this.validate.errors ?? []).map((e) => `${e.instancePath || '(root)'} ${e.message ?? ''}`.trim())
        throw new Error(`presets/${this.name}.json is invalid: ${details.join('; ')}`)
      }
      const have = new Set(this.items(data).map((p) => p.id))
      const deleted = new Set(data.deletedDefaults ?? [])
      const added = this.items(this.shipped).filter((p) => !have.has(p.id) && !deleted.has(p.id))
      if (added.length) {
        this.items(data).push(...added)
        await writeJsonAtomic(this.file, data)
      }
      this.doc = data
      this.error = null
    } catch (e) {
      this.doc = structuredClone(this.shipped)
      this.error = `${(e as Error).message}. Showing the built-in list; your file was not changed.`
      this.log.error('presets', this.error, { file: this.file })
    }
  }

  state(): ListState<T> {
    return { items: structuredClone(this.items(this.doc)), defaultIds: this.items(this.shipped).map((p) => p.id), error: this.error, file: this.file }
  }

  private async write(next: Doc<T>): Promise<ListState<T>> {
    if (this.error) throw new Error(`Your presets/${this.name}.json has errors, so the app will not overwrite it. Fix or remove it first.`)
    if (!this.validate(next)) {
      const details = (this.validate.errors ?? []).map((e) => `${e.instancePath || '(root)'} ${e.message ?? ''}`.trim())
      throw new Error(`That entry is not valid: ${details.join('; ')}`)
    }
    await writeJsonAtomic(this.file, next)
    this.doc = next
    return this.state()
  }

  async save(item: T): Promise<ListState<T>> {
    const list = this.items(this.doc).filter((p) => p.id !== item.id)
    const idx = this.items(this.doc).findIndex((p) => p.id === item.id)
    list.splice(idx === -1 ? list.length : idx, 0, item)
    return this.write({ ...this.doc, [this.key]: list })
  }

  async remove(id: string): Promise<ListState<T>> {
    const isDefault = this.items(this.shipped).some((p) => p.id === id)
    return this.write({
      ...this.doc,
      deletedDefaults: isDefault ? [...new Set([...(this.doc.deletedDefaults ?? []), id])] : this.doc.deletedDefaults,
      [this.key]: this.items(this.doc).filter((p) => p.id !== id)
    })
  }
}
