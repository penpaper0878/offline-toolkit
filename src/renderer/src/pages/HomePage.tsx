/**
 * The shared home screen: the four modules (open one, drop files on it, try a sample), recent work across
 * the modules, and the state of the offline engines.
 */

import { useEffect, useState } from 'react'
import { type ModuleId, PHOTO_RE, type RecentEntry } from '@shared/home'
import type { AppInfo, ConverterCatalog } from '@shared/types'
import { Icon } from '../components/Icon'
import { Modal } from '../components/controls'
import { otk } from '../lib/api'
import { openIn, routeAndOpen } from '../lib/route'
import { modLabel, useShortcuts } from '../lib/shortcuts'
import { useUi } from '../lib/ui-store'
import { useDesign } from '../modules/design/store'

interface ModuleCard {
  id: ModuleId
  name: string
  icon: string
  key: string
  summary: string
  points: string[]
  drop: string
}

export const MODULE_CARDS: ModuleCard[] = [
  { id: 'resizer', name: 'Image Resizer', icon: 'resize', key: '1', summary: 'Any size, DPI and file size you choose.',
    points: ['Pixels or cm / mm / inches at any DPI', 'Target file size, e.g. 20–50 KB', 'Batch, presets, ZIP'],
    drop: 'Drop pictures or a folder' },
  { id: 'converter', name: 'Document Converter', icon: 'convert', key: '2', summary: 'Every format to every other, checked after each job.',
    points: ['PDF, PDF/A, Word, Excel, PowerPoint, HTML, TXT, EPUB, images', 'OCR for scans; veraPDF-validated PDF/A', 'A report for every file'],
    drop: 'Drop documents or a folder' },
  { id: 'design', name: 'Image to Design', icon: 'design', key: '3', summary: 'A picture becomes editable layers.',
    points: ['Live text in the closest font, shapes, tables', 'Edit on the canvas, compare with the original', 'PowerPoint, Word, SVG, HTML'],
    drop: 'Drop a picture or a .otkd project' },
  { id: 'passport', name: 'Passport Photo', icon: 'passport', key: '4', summary: 'Photos that meet the size rules, and print sheets.',
    points: ['Face-guided sizing for 9 presets and your own', 'Background, adjustments, hints', 'Exact-size photo or a print sheet'],
    drop: 'Drop a photo' }
]

const MODULE_NAME: Record<ModuleId, string> = { resizer: 'Image Resizer', converter: 'Document Converter', design: 'Image to Design', passport: 'Passport Photo' }

function ago(iso: string): string {
  const s = (Date.now() - Date.parse(iso)) / 1000
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)} min ago`
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`
  const d = Math.floor(s / 86400)
  return d === 1 ? 'yesterday' : `${d} days ago`
}

async function dropped(e: React.DragEvent): Promise<{ paths: string[]; folders: string[] }> {
  const paths: string[] = []
  const folders: string[] = []
  for (const item of Array.from(e.dataTransfer.items)) {
    if (item.kind !== 'file') continue
    const file = item.getAsFile()
    const path = file ? otk().files.pathForFile(file) : ''
    if (!path) continue
    if (item.webkitGetAsEntry()?.isDirectory) folders.push(path)
    else paths.push(path)
  }
  return { paths, folders }
}

function Recent() {
  const [items, setItems] = useState<RecentEntry[] | null>(null)
  const remember = useUi((s) => s.settings?.home.rememberRecent ?? true)
  const load = () => void otk().recent.list().then(setItems, () => setItems([]))
  useEffect(load, [remember])
  const reopen = async (r: RecentEntry) => {
    if (!r.available) return
    if (r.module === 'design' && r.ref) {
      useUi.getState().setPage('design')
      await useDesign.getState().openDesign(r.ref)
    } else await openIn(r.module, r.paths)
  }
  return (
    <section className="home-recent" data-testid="home-recent">
      <header className="home-section-head">
        <h2><Icon name="clock" size={16} /> Recent</h2>
        <span className="spacer" />
        {items && items.length > 0 && <button className="btn small ghost" onClick={() => void otk().recent.clear().then(load)} data-testid="home-recent-clear">Clear list</button>}
      </header>
      {!remember ? <p className="muted small">Recent files are not kept (Settings → Home screen).</p>
        : items === null ? <span className="spinner small" />
          : items.length === 0 ? <p className="muted small">Files and designs you open appear here.</p>
            : (
              <ul className="recent-list">
                {items.map((r) => (
                  <li key={`${r.module}|${r.ref ?? ''}|${r.paths.join('|')}`} className={r.available ? '' : 'gone'} data-testid="recent-item" data-module={r.module}>
                    <button className="recent-open" disabled={!r.available} onClick={() => void reopen(r)}
                      title={r.available ? `Open in ${MODULE_NAME[r.module]}` : 'No longer there'}>
                      <Icon name={MODULE_CARDS.find((m) => m.id === r.module)!.icon} size={16} />
                      <span className="recent-label" dir="auto">{r.label}</span>
                      <span className="muted small">{MODULE_NAME[r.module]} · {r.available ? ago(r.at) : 'moved or deleted'}</span>
                    </button>
                    <button className="icon-btn" aria-label={`Remove ${r.label} from the list`}
                      onClick={() => void otk().recent.remove(r).then(load)}><Icon name="x" size={14} /></button>
                  </li>
                ))}
              </ul>
            )}
    </section>
  )
}

function Status() {
  const [info, setInfo] = useState<AppInfo | null>(null)
  const [catalog, setCatalog] = useState<ConverterCatalog | null>(null)
  useEffect(() => {
    void otk().app.info().then(setInfo, () => undefined)
    void otk().converter.catalog().then(setCatalog, () => undefined)
  }, [])
  const engines = catalog ? Object.values(catalog.engines) : []
  const found = engines.filter((e) => e.available).length
  const w = info?.worker as { netguard?: boolean; fonts?: number; models?: Record<string, boolean> } | null | undefined
  const models = w?.models ? Object.values(w.models) : []
  const chip = (ok: boolean | null, text: string, testId: string) => (
    <span className={`status-chip ${ok === null ? '' : ok ? 'good' : 'bad'}`} data-testid={testId}>
      {ok !== null && <Icon name={ok ? 'check' : 'warn'} size={13} />} {text}
    </span>
  )
  return (
    <div className="home-status" data-testid="home-status">
      {chip(info ? !!w?.netguard : null, info ? (w?.netguard ? 'Offline: network blocked' : 'Network guard off') : 'Checking…', 'status-offline')}
      {catalog && chip(found === engines.length, `Conversion engines: ${found} of ${engines.length}`, 'status-engines')}
      {w?.fonts !== undefined && chip(w.fonts > 0, `Fonts: ${w.fonts} families`, 'status-fonts')}
      {models.length > 0 && chip(models.every(Boolean), `Models: ${models.filter(Boolean).length} of ${models.length}`, 'status-models')}
      <span className="spacer" />
      <button className="btn small" onClick={() => useUi.getState().setPage('settings')} data-testid="home-check">
        <Icon name="shield" size={14} /> Self-test and licences
      </button>
    </div>
  )
}

/** Pictures dropped or opened on the home screen: what should happen to them? */
export function ImageChooser() {
  const chooser = useUi((s) => s.chooser)
  if (!chooser) return null
  const ui = useUi.getState()
  const n = chooser.images.length + chooser.folders.length
  const photos = chooser.images.filter((p) => PHOTO_RE.test(p))
  const one = photos[0]?.split(/[\\/]/).pop()
  const go = (m: ModuleId) => {
    ui.closeChooser()
    void openIn(m, m === 'resizer' ? chooser.images : photos.slice(0, 1), m === 'resizer' ? chooser.folders : [])
  }
  return (
    <Modal title={n === 1 && one ? `What should happen to ${one}?` : `What should happen to these ${n} pictures?`} onClose={() => ui.closeChooser()} testId="home-chooser" wide>
      <div className="chooser-options">
        <button className="chooser-option" onClick={() => go('resizer')} data-testid="choose-resizer">
          <Icon name="resize" size={22} /><strong>Resize and compress</strong><span className="muted small">{n === 1 ? 'Exact size, DPI and file size' : `All ${n}, in one batch`}</span>
        </button>
        <button className="chooser-option" disabled={!photos.length} onClick={() => go('design')} data-testid="choose-design">
          <Icon name="design" size={22} /><strong>Turn into an editable design</strong><span className="muted small">{photos.length > 1 ? `The first picture (${one})` : 'Text, shapes and pictures as layers'}</span>
        </button>
        <button className="chooser-option" disabled={!photos.length} onClick={() => go('passport')} data-testid="choose-passport">
          <Icon name="passport" size={22} /><strong>Make a passport photo</strong><span className="muted small">{photos.length > 1 ? `The first picture (${one})` : 'Sized and checked for an office'}</span>
        </button>
      </div>
    </Modal>
  )
}

export function HomePage() {
  const ui = useUi.getState()
  const [over, setOver] = useState<ModuleId | null>(null)
  const openAny = async () => {
    const paths = await otk().dialogs.openAny()
    if (paths.length) await routeAndOpen(paths, [], 'home')
  }
  useShortcuts([{ keys: 'mod+o', run: () => void openAny() }])
  return (
    <div className="simple-page home-page" data-testid="home-page">
      <header className="page-head home-head">
        <h1>Offline Toolkit</h1>
        <span className="muted">Everything runs on this computer. Nothing is uploaded.</span>
        <span className="spacer" />
        <button className="btn primary" onClick={() => void openAny()} data-testid="home-open"><Icon name="open" size={16} /> Open a file… <kbd>{modLabel}+O</kbd></button>
      </header>
      <div className="home-body">
        <Status />
        <div className="home-cards">
          {MODULE_CARDS.map((m) => (
            <article key={m.id} className={`home-card ${over === m.id ? 'over' : ''}`} data-testid={`home-card-${m.id}`}
              onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); setOver(m.id) }}
              onDragLeave={() => setOver(null)}
              onDrop={(e) => {
                e.preventDefault()
                e.stopPropagation()
                setOver(null)
                void dropped(e).then(({ paths, folders }) => openIn(m.id, paths, folders))
                  .catch((err) => ui.reportError('Could not open the files', err))
              }}>
              <button className="home-card-main" onClick={() => ui.setPage(m.id)} data-testid={`home-go-${m.id}`}>
                <span className="home-card-icon"><Icon name={m.icon} size={26} /></span>
                <span className="home-card-text">
                  <strong>{m.name}</strong>
                  <span className="muted">{m.summary}</span>
                </span>
                <kbd>{modLabel}+{m.key}</kbd>
              </button>
              <ul className="home-points">{m.points.map((p) => <li key={p}>{p}</li>)}</ul>
              <div className="home-card-foot muted small">{over === m.id ? 'Release to open here' : m.drop}</div>
            </article>
          ))}
        </div>
        <Recent />
      </div>
    </div>
  )
}
