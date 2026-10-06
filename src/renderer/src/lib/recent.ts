/** Remembering what was opened, for the home screen's recent list (when the person keeps one). */

import { filesLabel, type ModuleId, type RecentItem } from '@shared/home'
import { otk } from './api'
import { useUi } from './ui-store'

/** Add an entry to the recent list. Never throws. */
export function remember(item: Omit<RecentItem, 'at'>): void {
  if (!useUi.getState().settings?.home?.rememberRecent) return
  if (!item.paths.length && !item.ref) return
  void otk().recent.add(item).catch(() => undefined)
}

export function rememberFiles(module: ModuleId, paths: string[], noun: string): void {
  if (paths.length) remember({ module, paths, label: filesLabel(paths, noun) })
}
