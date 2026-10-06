import { describe, expect, it } from 'vitest'
import { addRecent, filesLabel, RECENT_LIMIT, type RecentItem, removeRecent, routeFiles, validRecent } from './home'

describe('routing dropped or opened files', () => {
  it('sends documents to the converter and design projects to the design module, from any page', () => {
    for (const page of ['home', 'resizer', 'passport']) {
      expect(routeFiles(['/a/report.docx'], [], page)).toMatchObject({ kind: 'module', module: 'converter' })
      expect(routeFiles(['/a/poster.otkd'], [], page)).toEqual({ kind: 'module', module: 'design', paths: ['/a/poster.otkd'], folders: [] })
    }
    expect(routeFiles(['/a/report.docx', '/a/photo.jpg'], [], 'home')).toMatchObject({ kind: 'module', module: 'converter' })
    // The passport wizard keeps the photo of a mixed drop (as before the home screen existed).
    expect(routeFiles(['/a/report.docx', '/a/photo.jpg'], [], 'passport')).toEqual({ kind: 'module', module: 'passport', paths: ['/a/photo.jpg'], folders: [] })
  })

  it('asks what to do with pictures on the home screen, and keeps the module elsewhere', () => {
    expect(routeFiles(['/a/x.jpg', '/a/y.heic'], ['/f'], 'home')).toEqual({ kind: 'choose', images: ['/a/x.jpg', '/a/y.heic'], folders: ['/f'] })
    expect(routeFiles(['/a/x.jpg'], [], 'resizer')).toMatchObject({ kind: 'module', module: 'resizer' })
    expect(routeFiles(['/a/x.jpg'], [], 'converter')).toMatchObject({ kind: 'module', module: 'converter' })
    expect(routeFiles(['/a/x.png', '/a/notes.txt'], [], 'design')).toEqual({ kind: 'module', module: 'design', paths: ['/a/x.png'], folders: [] })
    expect(routeFiles(['/a/x.webp'], [], 'passport')).toEqual({ kind: 'module', module: 'passport', paths: ['/a/x.webp'], folders: [] })
    // A picture type the passport wizard cannot open goes to the resizer as before.
    expect(routeFiles(['/a/x.dib'], [], 'passport')).toMatchObject({ kind: 'module', module: 'resizer' })
  })

  it('treats a dropped folder like the module expects, and nothing as nothing', () => {
    expect(routeFiles([], ['/pics'], 'home')).toEqual({ kind: 'module', module: 'resizer', paths: [], folders: ['/pics'] })
    expect(routeFiles([], ['/docs'], 'converter')).toEqual({ kind: 'module', module: 'converter', paths: [], folders: ['/docs'] })
    expect(routeFiles([], [], 'home')).toEqual({ kind: 'none' })
  })

  it('recognises extensions case-insensitively, including Windows paths', () => {
    expect(routeFiles(['C:\\Users\\me\\IMG_0001.JPG'], [], 'home')).toMatchObject({ kind: 'choose' })
    expect(routeFiles(['C:\\Users\\me\\Design.OTKD'], [], 'home')).toMatchObject({ kind: 'module', module: 'design' })
  })
})

describe('the recent list', () => {
  const item = (n: number, module: 'resizer' | 'converter' = 'resizer'): RecentItem => ({ module, label: `f${n}`, paths: [`/f${n}`], at: `2026-10-0${n % 9 + 1}T00:00:00Z` })

  it('puts the newest first, moves a repeat to the top and stays within the limit', () => {
    let list = [item(1), item(2)].reduce<RecentItem[]>((l, i) => addRecent(l, i), [])
    expect(list.map((r) => r.label)).toEqual(['f2', 'f1'])
    list = addRecent(list, { ...item(1), label: 'again' })
    expect(list.map((r) => r.label)).toEqual(['again', 'f2'])
    for (let i = 3; i < 40; i++) list = addRecent(list, item(i))
    expect(list).toHaveLength(RECENT_LIMIT)
    expect(list[0].label).toBe('f39')
  })

  it('tells the same files in different modules apart, and the same files in any order alike', () => {
    let list: RecentItem[] = addRecent([], { module: 'resizer', label: 'a', paths: ['/x', '/y'], at: 't' })
    list = addRecent(list, { module: 'converter', label: 'b', paths: ['/x', '/y'], at: 't' })
    list = addRecent(list, { module: 'resizer', label: 'c', paths: ['/y', '/x'], at: 't' })
    expect(list.map((r) => r.label)).toEqual(['c', 'b'])
    expect(removeRecent(list, { module: 'converter', paths: ['/y', '/x'] }).map((r) => r.label)).toEqual(['c'])
  })

  it('keeps only well-formed entries from the file', () => {
    const raw = { items: [
      { module: 'design', label: 'Poster', paths: [], ref: 'abc12345', at: 't' },
      { module: 'spreadsheet', label: 'x', paths: [], at: 't' },
      { module: 'resizer', label: 'x', paths: [1], at: 't' },
      { module: 'passport', label: 'p', paths: ['/p.jpg'], at: 't' },
      null, 'junk'
    ] }
    expect(validRecent(raw).map((r) => r.label)).toEqual(['Poster', 'p'])
    expect(validRecent(null)).toEqual([])
    expect(validRecent({ items: 'no' })).toEqual([])
  })

  it('labels a single file by its name and several by their number', () => {
    expect(filesLabel(['C:\\a\\Report 2026.pdf'], 'documents')).toBe('Report 2026.pdf')
    expect(filesLabel(['/a/x.jpg', '/a/y.jpg'], 'images')).toBe('2 images')
  })
})
