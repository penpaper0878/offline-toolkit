import { useEffect, useState } from 'react'
import { otk } from './lib/api'
import { modLabel, useShortcuts } from './lib/shortcuts'
import { type Page, useUi } from './lib/ui-store'
import { Icon } from './components/Icon'
import { Toasts } from './components/Toasts'
import { ConverterPage, useConverterBoot } from './modules/converter/ConverterPage'
import { useConverter } from './modules/converter/store'
import { ResizerPage, useResizerBoot } from './modules/resizer/ResizerPage'
import { useResizer } from './modules/resizer/store'
import { ComingSoon } from './pages/ComingSoon'
import { LogPage } from './pages/LogPage'
import { SettingsPage } from './pages/SettingsPage'

const NAV: { page: Page; label: string; icon: string; phase?: number }[] = [
  { page: 'resizer', label: 'Image Resizer', icon: 'resize' },
  { page: 'converter', label: 'Document Converter', icon: 'convert' },
  { page: 'design', label: 'Image to Design', icon: 'design', phase: 3 },
  { page: 'passport', label: 'Passport Photo', icon: 'passport', phase: 4 },
  { page: 'log', label: 'Event log', icon: 'log' },
  { page: 'settings', label: 'Settings', icon: 'settings' }
]

function useTheme(): void {
  const theme = useUi((s) => s.settings?.theme ?? 'system')
  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const apply = () => {
      const dark = theme === 'dark' || (theme === 'system' && mq.matches)
      document.documentElement.dataset.theme = dark ? 'dark' : 'light'
    }
    apply()
    mq.addEventListener('change', apply)
    return () => mq.removeEventListener('change', apply)
  }, [theme])
}

const IMAGE_RE = /\.(jpe?g|jpe|jfif|png|webp|bmp|dib|tiff?|heic|heif|hif)$/i

async function handleDrop(e: React.DragEvent): Promise<void> {
  e.preventDefault()
  const paths: string[] = []
  const folders: string[] = []
  const items = Array.from(e.dataTransfer.items)
  for (const item of items) {
    if (item.kind !== 'file') continue
    const file = item.getAsFile()
    if (!file) continue
    const path = otk().files.pathForFile(file)
    if (!path) continue
    if (item.webkitGetAsEntry()?.isDirectory) folders.push(path)
    else paths.push(path)
  }
  // Documents go to the converter; images go to the resizer unless the converter is open.
  const toConverter = useUi.getState().page === 'converter' || paths.some((p) => !IMAGE_RE.test(p))
  if (toConverter) {
    for (const f of folders) paths.push(...(await otk().files.listDocuments(f, false)))
    if (!paths.length) {
      useUi.getState().toast('warn', 'Nothing to add', 'Drop documents (PDF, Word, Excel, PowerPoint, HTML, TXT, EPUB, images, SVG) or a folder.')
      return
    }
    useUi.getState().setPage('converter')
    await useConverter.getState().addPaths(paths)
    return
  }
  for (const f of folders) paths.push(...(await otk().files.listImages(f, false)))
  if (!paths.length) {
    useUi.getState().toast('warn', 'Nothing to add', 'Drop image files (JPG, PNG, WEBP, BMP, TIFF, HEIC) or a folder that contains them.')
    return
  }
  useUi.getState().setPage('resizer')
  await useResizer.getState().addPaths(paths)
}

export function App() {
  const page = useUi((s) => s.page)
  const setPage = useUi((s) => s.setPage)
  const loaded = useUi((s) => s.settings !== null)
  const [dragging, setDragging] = useState(false)
  useTheme()
  useResizerBoot()
  useConverterBoot()

  useEffect(() => {
    void useUi.getState().loadSettings().catch((e) => useUi.getState().reportError('Could not load settings', e))
  }, [])

  useShortcuts([
    { keys: 'mod+l', run: () => setPage('log'), inInputs: true },
    { keys: 'mod+,', run: () => setPage('settings'), inInputs: true },
    { keys: 'mod+1', run: () => setPage('resizer'), inInputs: true },
    { keys: 'mod+2', run: () => setPage('converter'), inInputs: true }
  ])

  return (
    <div className="app"
      onDragEnter={(e) => { if (e.dataTransfer.types.includes('Files')) setDragging(true) }}
      onDragOver={(e) => e.preventDefault()}
      onDragLeave={(e) => { if (e.currentTarget === e.target || !e.relatedTarget) setDragging(false) }}
      onDrop={(e) => { setDragging(false); void handleDrop(e).catch((err) => useUi.getState().reportError('Could not add the files', err)) }}>
      <nav className="sidebar" aria-label="Modules">
        <div className="brand"><Icon name="shield" size={20} /> Offline Toolkit</div>
        {NAV.map((n) => (
          <button key={n.page} className={`nav-item ${page === n.page ? 'active' : ''}`} data-testid={`nav-${n.page}`}
            aria-current={page === n.page ? 'page' : undefined} onClick={() => setPage(n.page)}>
            <Icon name={n.icon} /> <span>{n.label}</span>
            {n.phase && <span className="soon">soon</span>}
          </button>
        ))}
        <div className="sidebar-foot muted small">
          <Icon name="shield" size={14} /> Works offline. Files never leave this computer.
          <div>{modLabel}+L log · {modLabel}+, settings</div>
        </div>
      </nav>
      <div className="page">
        {!loaded ? <div className="empty-view"><span className="spinner" /> Starting…</div> : (
          <>
            {page === 'resizer' && <ResizerPage />}
            {page === 'converter' && <ConverterPage />}
            {page === 'design' && <ComingSoon title="Image to Editable Design" phase={3} />}
            {page === 'passport' && <ComingSoon title="Passport Photo Maker" phase={4} />}
            {page === 'log' && <LogPage />}
            {page === 'settings' && <SettingsPage />}
          </>
        )}
      </div>
      {dragging && <div className="drop-overlay" aria-hidden><div>{page === 'converter' ? 'Drop documents or a folder to convert them' : 'Drop images or a folder to add them'}</div></div>}
      <Toasts />
    </div>
  )
}
