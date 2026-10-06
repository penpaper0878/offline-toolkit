import { create } from 'zustand'
import type { AppSettings, SettingsState } from '@shared/types'
import { applySettingsPatch } from '@shared/settings-merge'
import { otk, toUiError } from './api'

export type Page = 'home' | 'resizer' | 'converter' | 'design' | 'passport' | 'log' | 'settings'

export interface Toast {
  id: number
  kind: 'info' | 'success' | 'warn' | 'error'
  title: string
  body?: string
}

/** Pictures dropped or opened on the home screen, waiting for the person to choose a module. */
export interface Chooser {
  images: string[]
  folders: string[]
}

interface UiState {
  page: Page
  chooser: Chooser | null
  settings: AppSettings | null
  settingsState: SettingsState | null
  toasts: Toast[]
  setPage(p: Page): void
  choose(images: string[], folders: string[]): void
  closeChooser(): void
  loadSettings(): Promise<void>
  toast(kind: Toast['kind'], title: string, body?: string, ms?: number): void
  dismiss(id: number): void
  reportError(title: string, e: unknown): void
}

let toastId = 1
let lastPageTimer: ReturnType<typeof setTimeout> | null = null

export const useUi = create<UiState>((set, get) => ({
  page: 'home',
  chooser: null,
  settings: null,
  settingsState: null,
  toasts: [],
  setPage(page) {
    if (page === get().page) return
    set({ page })
    // Remembered for "open where I left off" (written a moment later, once).
    if (lastPageTimer) clearTimeout(lastPageTimer)
    lastPageTimer = setTimeout(() => {
      if (get().settings?.home?.lastPage !== get().page) void updateAppSettings({ home: { lastPage: get().page } }).catch(() => undefined)
    }, 1000)
  },
  choose: (images, folders) => set({ chooser: { images, folders } }),
  closeChooser: () => set({ chooser: null }),
  async loadSettings() {
    const first = get().settings === null
    const state = await otk().settings.get()
    set({ settings: state.settings, settingsState: state })
    const home = state.settings.home
    if (first && home?.startPage === 'last' && home.lastPage) set({ page: home.lastPage })
    if (state.error) get().toast('error', 'Settings file problem', state.error, 0)
  },
  toast(kind, title, body, ms = kind === 'error' ? 9000 : 4500) {
    const id = toastId++
    set((s) => ({ toasts: [...s.toasts.slice(-4), { id, kind, title, body }] }))
    if (ms > 0) setTimeout(() => get().dismiss(id), ms)
  },
  dismiss: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
  reportError(title, e) {
    const err = toUiError(e)
    if (err.code === 'cancelled') return
    get().toast('error', title, err.message)
    void otk().log.add('error', `${title}: ${err.message}`)
  }
}))

let settingsSeq = 0

/** Change settings: shown at once (so a click right after a change sees it), then saved by the main process,
 * whose answer replaces the local copy when it is the answer to the newest change (or when saving failed). */
export async function updateAppSettings(patch: Parameters<ReturnType<typeof otk>['settings']['update']>[0]): Promise<void> {
  const seq = ++settingsSeq
  const cur = useUi.getState().settings
  if (cur) useUi.setState({ settings: applySettingsPatch(cur, patch) })
  try {
    const state = await otk().settings.update(patch)
    if (seq === settingsSeq) useUi.setState({ settings: state.settings, settingsState: state })
  } catch (e) {
    const state = await otk().settings.get().catch(() => null)
    if (state) useUi.setState({ settings: state.settings, settingsState: state })
    throw e
  }
}
