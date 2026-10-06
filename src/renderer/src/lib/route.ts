/** Sending files to a module: drops, "Open a file…" on the home screen, recent files. */

import { type ModuleId, routeFiles } from '@shared/home'
import { useConverter } from '../modules/converter/store'
import { dropToDesign } from '../modules/design/DesignPage'
import { dropToPassport } from '../modules/passport/PassportPage'
import { useResizer } from '../modules/resizer/store'
import { otk } from './api'
import { useUi } from './ui-store'

/** Open files (and folders) in a module. */
export async function openIn(module: ModuleId, paths: string[], folders: string[] = []): Promise<void> {
  const ui = useUi.getState()
  ui.setPage(module)
  if (module === 'resizer') {
    const all = [...paths]
    for (const f of folders) all.push(...(await otk().files.listImages(f, false)))
    if (!all.length) return ui.toast('warn', 'Nothing to add', 'Choose image files (JPG, PNG, WEBP, BMP, TIFF, HEIC) or a folder that contains them.')
    await useResizer.getState().addPaths(all)
  } else if (module === 'converter') {
    const all = [...paths]
    for (const f of folders) all.push(...(await otk().files.listDocuments(f, false)))
    if (!all.length) return ui.toast('warn', 'Nothing to add', 'Choose documents (PDF, Word, Excel, PowerPoint, HTML, TXT, EPUB, images, SVG) or a folder.')
    await useConverter.getState().addPaths(all)
  } else if (module === 'design') {
    if (!(await dropToDesign(paths))) ui.toast('warn', 'Nothing to open', 'Choose a picture or a design project (.otkd).')
  } else {
    if (!(await dropToPassport(paths))) ui.toast('warn', 'Nothing to open', 'Choose a photo (JPG, PNG, WEBP, HEIC).')
  }
}

/** Route files the way a drop on `page` would: straight to a module, or (pictures on the home screen) ask. */
export async function routeAndOpen(paths: string[], folders: string[], page: string): Promise<void> {
  const route = routeFiles(paths, folders, page)
  if (route.kind === 'none') return
  if (route.kind === 'choose') {
    useUi.getState().choose(route.images, route.folders)
    return
  }
  await openIn(route.module, route.paths, route.folders)
}
