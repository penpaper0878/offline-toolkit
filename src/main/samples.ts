/**
 * "Try a sample" on the home screen: copies the module's bundled sample (resources/samples/<module>, made by
 * scripts/make_samples.py) into <data>/samples/<module>, where results can be saved next to it, and returns the copies.
 */

import { copyFile, mkdir, readdir } from 'node:fs/promises'
import { join } from 'node:path'
import { IPC } from '@shared/api'
import { MODULES, type ModuleId } from '@shared/home'
import { handle } from './ipc-util'
import type { EventLog } from './log'
import { dataDir, resourcesDir } from './paths'
import { WorkerError } from './worker'

export function registerSamplesIpc({ log }: { log: EventLog }): void {
  handle(IPC.samplesPrepare, async (module: unknown): Promise<string[]> => {
    if (!MODULES.includes(module as ModuleId)) throw new WorkerError('Unknown module.', 'input')
    const src = join(resourcesDir(), 'samples', module as string)
    const dest = join(dataDir(), 'samples', module as string)
    let names: string[]
    try {
      names = (await readdir(src)).filter((n) => !n.endsWith('.md'))
    } catch {
      throw new WorkerError('This copy of the app has no sample files.', 'input')
    }
    await mkdir(dest, { recursive: true })
    const out: string[] = []
    for (const n of names.sort()) {
      await copyFile(join(src, n), join(dest, n))
      out.push(join(dest, n))
    }
    log.info('home', `Sample opened in ${module as string}`, { files: names })
    return out
  }, log)
}
