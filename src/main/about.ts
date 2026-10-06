/**
 * About & licences: the list scripts/collect_licenses.py writes at build time (every bundled component, its SPDX
 * licence, copyleft level and licence texts), and the texts themselves, read only from inside the licences folder.
 */

import { existsSync } from 'node:fs'
import { readFile, stat } from 'node:fs/promises'
import { join, resolve, sep } from 'node:path'
import { IPC } from '@shared/api'
import type { LicenceInfo, LicenceReport } from '@shared/types'
import { handle } from './ipc-util'
import type { EventLog } from './log'
import { chromiumLicensesFile, licensesDir } from './paths'
import { WorkerError } from './worker'

const TEXT = /^texts\/[\w.@+ -]+(\/[\w.@+ -]+)*$/

export function registerAboutIpc({ log }: { log: EventLog }): void {
  handle(IPC.aboutLicences, async (): Promise<LicenceInfo> => {
    const dir = licensesDir()
    const chromium = chromiumLicensesFile()
    const notices = join(dir, 'THIRD-PARTY-NOTICES.txt')
    let report: LicenceReport | null = null
    try {
      report = JSON.parse(await readFile(join(dir, 'third-party.json'), 'utf-8')) as LicenceReport
    } catch {
      report = null                          // a development build that has not run `npm run licenses`
    }
    return { report, dir, noticesFile: existsSync(notices) ? notices : null, chromiumFile: existsSync(chromium) ? chromium : null }
  }, log)

  handle(IPC.aboutText, async (file: unknown): Promise<string> => {
    if (typeof file !== 'string' || !TEXT.test(file) || file.split('/').includes('..')) throw new WorkerError('Not a licence text.', 'input')
    const root = resolve(licensesDir())
    const path = resolve(root, file)
    if (!path.startsWith(root + sep)) throw new WorkerError('Not a licence text.', 'input')
    if ((await stat(path)).size > 4_000_000) throw new WorkerError('That licence text is too large to show.', 'input')
    return readFile(path, 'utf-8')
  }, log)
}
