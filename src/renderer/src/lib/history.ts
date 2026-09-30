/**
 * Undo/redo stack of immutable snapshots. Consecutive changes with the same
 * `coalesceKey` inside `windowMs` merge into one step (typing "240" is one
 * undo, not three).
 */

export interface History<T> {
  past: T[]
  present: T
  future: T[]
  lastKey: string | null
  lastAt: number
}

export const LIMIT = 200

export function createHistory<T>(present: T): History<T> {
  return { past: [], present, future: [], lastKey: null, lastAt: 0 }
}

export function record<T>(h: History<T>, next: T, coalesceKey: string | null = null, now = Date.now(), windowMs = 800): History<T> {
  if (Object.is(next, h.present)) return h
  const merge = coalesceKey !== null && coalesceKey === h.lastKey && now - h.lastAt < windowMs
  const past = merge ? h.past : [...h.past, h.present].slice(-LIMIT)
  return { past, present: next, future: [], lastKey: coalesceKey, lastAt: now }
}

/** Replace the present without creating an undo step (e.g. loading a file). */
export function replace<T>(h: History<T>, next: T): History<T> {
  return { ...h, present: next, lastKey: null }
}

export function undo<T>(h: History<T>): History<T> {
  if (!h.past.length) return h
  const prev = h.past[h.past.length - 1]
  return { past: h.past.slice(0, -1), present: prev, future: [h.present, ...h.future], lastKey: null, lastAt: 0 }
}

export function redo<T>(h: History<T>): History<T> {
  if (!h.future.length) return h
  const [next, ...rest] = h.future
  return { past: [...h.past, h.present], present: next, future: rest, lastKey: null, lastAt: 0 }
}

export const canUndo = <T>(h: History<T>): boolean => h.past.length > 0
export const canRedo = <T>(h: History<T>): boolean => h.future.length > 0
