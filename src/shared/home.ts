/**
 * The home screen's shared logic: which module a set of files belongs to, and the list of recent work
 * (kept by the main process in <data>/recent.json). Pure functions, used by the main process, the window
 * and the tests.
 */

export type ModuleId = 'resizer' | 'converter' | 'design' | 'passport'

export const MODULES: readonly ModuleId[] = ['resizer', 'converter', 'design', 'passport']

export const IMAGE_RE = /\.(jpe?g|jpe|jfif|png|webp|bmp|dib|tiff?|heic|heif|hif)$/i
export const DESIGN_RE = /\.otkd$/i

/** Pictures the passport wizard and the design module can open (a subset of the resizer's). */
export const PHOTO_RE = /\.(jpe?g|jpe|jfif|png|webp|bmp|tiff?|heic|heif|hif)$/i

export type DropRoute =
  | { kind: 'module'; module: ModuleId; paths: string[]; folders: string[] }
  | { kind: 'choose'; images: string[]; folders: string[] }   // pictures from the home screen: ask what to do
  | { kind: 'none' }

/**
 * Where dropped (or opened) files go. On a module's page they go to that module when it can take them;
 * a design project always opens in the design module; documents (anything that is not a picture) go to
 * the converter; pictures go to the resizer, except on the home screen, where the person chooses.
 */
export function routeFiles(paths: string[], folders: string[], page: string): DropRoute {
  if (!paths.length && !folders.length) return { kind: 'none' }
  const photos = paths.filter((p) => PHOTO_RE.test(p))
  if (page === 'design' && (photos.length || paths.some((p) => DESIGN_RE.test(p)))) {
    return { kind: 'module', module: 'design', paths: paths.filter((p) => PHOTO_RE.test(p) || DESIGN_RE.test(p)), folders: [] }
  }
  if (page === 'passport' && photos.length) return { kind: 'module', module: 'passport', paths: photos, folders: [] }
  if (paths.some((p) => DESIGN_RE.test(p))) return { kind: 'module', module: 'design', paths: paths.filter((p) => DESIGN_RE.test(p)), folders: [] }
  const documents = paths.some((p) => !IMAGE_RE.test(p))
  if (page === 'converter' || documents) return { kind: 'module', module: 'converter', paths, folders }
  if (page === 'home' && paths.length) return { kind: 'choose', images: paths, folders }
  return { kind: 'module', module: 'resizer', paths, folders }
}

export interface RecentItem {
  module: ModuleId
  label: string             // what the person sees: a file name, "12 images", a design's name
  paths: string[]           // the files to open again (at most RECENT_PATHS)
  ref?: string              // a design's id
  at: string                // ISO time
}

/** A recent item as listed, with what is still there. */
export interface RecentEntry extends RecentItem {
  available: boolean
}

export const RECENT_LIMIT = 20
export const RECENT_PATHS = 50

function key(r: Pick<RecentItem, 'module' | 'paths' | 'ref'>): string {
  return `${r.module}|${r.ref ?? ''}|${[...r.paths].sort().join('\n')}`
}

/** The list with `item` first (an older entry for the same files moves up), at most RECENT_LIMIT long. */
export function addRecent(list: RecentItem[], item: RecentItem): RecentItem[] {
  const clean: RecentItem = { ...item, paths: item.paths.slice(0, RECENT_PATHS), label: item.label.slice(0, 200) }
  const k = key(clean)
  return [clean, ...list.filter((r) => key(r) !== k)].slice(0, RECENT_LIMIT)
}

export function removeRecent(list: RecentItem[], item: Pick<RecentItem, 'module' | 'paths' | 'ref'>): RecentItem[] {
  const k = key(item)
  return list.filter((r) => key(r) !== k)
}

/** A label for a set of files: the name of one, or "N images" / "N documents". */
export function filesLabel(paths: string[], noun: string): string {
  if (paths.length === 1) return paths[0].split(/[\\/]/).pop() ?? paths[0]
  return `${paths.length} ${noun}`
}

/** Only well-formed items survive (the file is the person's to edit). */
export function validRecent(v: unknown): RecentItem[] {
  if (!v || typeof v !== 'object' || !Array.isArray((v as { items?: unknown }).items)) return []
  const out: RecentItem[] = []
  for (const r of (v as { items: unknown[] }).items) {
    if (!r || typeof r !== 'object') continue
    const o = r as Record<string, unknown>
    if (!MODULES.includes(o.module as ModuleId) || typeof o.label !== 'string' || typeof o.at !== 'string') continue
    if (!Array.isArray(o.paths) || !o.paths.every((p) => typeof p === 'string')) continue
    if (o.ref !== undefined && typeof o.ref !== 'string') continue
    out.push({ module: o.module as ModuleId, label: o.label, paths: o.paths as string[], at: o.at, ...(o.ref ? { ref: o.ref as string } : {}) })
  }
  return out.slice(0, RECENT_LIMIT)
}
