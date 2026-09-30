import { create } from 'zustand'
import type { AppSettings, SettingsState } from '@shared/types'
import { otk, toUiError } from './api'

export type Page = 'resizer' | 'converter' | 'design' | 'passport' | 'log' | 'settings'

export interface Toast {
  id: number
  kind: 'info' | 'success' | 'warn' | 'error'
  title: string
  body?: string
}

interface UiState {
  page: Page
  settings: AppSettings | null
  settingsState: SettingsState | null
  toasts: Toast[]
  setPage(p: Page): void
  loadSettings(): Promise<void>
  toast(kind: Toast['kind'], title: string, body?: string, ms?: number): void
  dismiss(id: number): void
  reportError(title: string, e: unknown): void
}

let toastId = 1

export const useUi = create<UiState>((set, get) => ({
  page: 'resizer',
  settings: null,
  settingsState: null,
  toasts: [],
  setPage: (page) => set({ page }),
  async loadSettings() {
    const state = await otk().settings.get()
    set({ settings: state.settings, settingsState: state })
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

export async function updateAppSettings(patch: Parameters<ReturnType<typeof otk>['settings']['update']>[0]): Promise<void> {
  const state = await otk().settings.update(patch)
  useUi.setState({ settings: state.settings, settingsState: state })
}
