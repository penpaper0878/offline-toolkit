import { describe, expect, it } from 'vitest'
import { canRedo, canUndo, createHistory, LIMIT, record, redo, replace, undo } from './history'

describe('undo/redo history', () => {
  it('records, undoes and redoes', () => {
    let h = createHistory(1)
    h = record(h, 2)
    h = record(h, 3)
    expect(h.present).toBe(3)
    h = undo(h)
    expect(h.present).toBe(2)
    h = undo(h)
    expect(h.present).toBe(1)
    expect(canUndo(h)).toBe(false)
    h = redo(h)
    expect(h.present).toBe(2)
    h = record(h, 9)
    expect(canRedo(h)).toBe(false)
  })

  it('coalesces fast edits of the same field', () => {
    let h = createHistory('')
    h = record(h, '2', 'width', 1000)
    h = record(h, '24', 'width', 1200)
    h = record(h, '240', 'width', 1400)
    h = record(h, '240px', 'unit', 1500)
    expect(h.past).toEqual(['', '240'])
    h = undo(h)
    expect(h.present).toBe('240')
    h = undo(h)
    expect(h.present).toBe('')
  })

  it('does not coalesce after a pause', () => {
    let h = createHistory(0)
    h = record(h, 1, 'k', 0)
    h = record(h, 2, 'k', 5000)
    expect(h.past).toEqual([0, 1])
  })

  it('replace does not add a step, and history is bounded', () => {
    let h = createHistory(0)
    h = replace(h, 5)
    expect(canUndo(h)).toBe(false)
    for (let i = 1; i <= LIMIT + 50; i++) h = record(h, i)
    expect(h.past.length).toBe(LIMIT)
  })
})
