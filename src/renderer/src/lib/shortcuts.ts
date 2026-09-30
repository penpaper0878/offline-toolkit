import { useEffect, useRef } from 'react'

export interface Shortcut {
  /** e.g. "mod+o", "mod+shift+z", "delete", "+", "0" — "mod" is Ctrl (Cmd on macOS). */
  keys: string
  run: (e: KeyboardEvent) => void
  /** Also fire while typing in a text field (default false). */
  inInputs?: boolean
}

const isMac = navigator.platform.toLowerCase().includes('mac')

function matches(e: KeyboardEvent, keys: string): boolean {
  const parts = keys.toLowerCase().split('+')
  const key = parts.pop()!
  const want = { mod: parts.includes('mod'), shift: parts.includes('shift'), alt: parts.includes('alt') }
  const mod = isMac ? e.metaKey : e.ctrlKey
  if (want.mod !== mod || want.alt !== e.altKey) return false
  const k = e.key.toLowerCase()
  const shiftSensitive = key.length > 1 || /[a-z0-9]/.test(key)
  if (shiftSensitive && want.shift !== e.shiftKey) return false
  if (key === '+') return k === '+' || k === '='
  if (key === '-') return k === '-' || k === '_'
  return k === key
}

function typing(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null
  if (!el) return false
  const tag = el.tagName
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || el.isContentEditable
}

/** Register shortcuts while the component is mounted. */
export function useShortcuts(shortcuts: Shortcut[], enabled = true): void {
  const ref = useRef(shortcuts)
  ref.current = shortcuts
  useEffect(() => {
    if (!enabled) return
    const onKey = (e: KeyboardEvent) => {
      for (const s of ref.current) {
        if (!matches(e, s.keys)) continue
        if (typing(e.target) && !s.inInputs) continue
        e.preventDefault()
        s.run(e)
        return
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [enabled])
}

export const modLabel = isMac ? '⌘' : 'Ctrl'
