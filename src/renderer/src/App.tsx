import { useEffect, useState } from 'react'
import { otk } from './lib/api'
import { modLabel, useShortcuts } from './lib/shortcuts'
import { type Page, useUi } from './lib/ui-store'
import { Icon } from './components/Icon'
import { Toasts } from './components/Toasts'
import { routeAndOpen } from './lib/route'
import { ConverterPage, useConverterBoot } from './modules/converter/ConverterPage'
import { DesignPage, useDesignBoot } from './modules/design/DesignPage'
import { PassportPage, usePassportBoot } from './modules/passport/PassportPage'
import { ResizerPage, useResizerBoot } from './modules/resizer/ResizerPage'
import { HomePage, ImageChooser } from './pages/HomePage'
import { LogPage } from './pages/LogPage'
import { SettingsPage } from './pages/SettingsPage'

const NAV: { page: Page; label: string; icon: string; phase?: number }[] = [
  { page: 'home', label: 'Home', icon: 'home' },
  { page: 'resizer', label: 'Image Resizer', icon: 'resize' },
  { page: 'converter', label: 'Document Converter', icon: 'convert' },
  { page: 'design', label: 'Image to Design', icon: 'design' },
  { page: 'passport', label: 'Passport Photo', icon: 'passport' },
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

async function handleDrop(e: React.DragEvent): Promise<void> {
  e.preventDefault()
  const paths: string[] = []
  const folders: string[] = []
  for (const item of Array.from(e.dataTransfer.items)) {
    if (item.kind !== 'file') continue
    const file = item.getAsFile()
    if (!file) continue
    const path = otk().files.pathForFile(file)
    if (!path) continue
    if (item.webkitGetAsEntry()?.isDirectory) folders.push(path)
    else paths.push(path)
  }
  await routeAndOpen(paths, folders, useUi.getState().page)
}

const DROP_HINT: Partial<Record<Page, string>> = {
  home: 'Drop files: documents go to the converter; for pictures you choose what to do',
  converter: 'Drop documents or a folder to convert them',
  design: 'Drop a picture to turn it into an editable design',
  passport: 'Drop a photo to make a passport photo'
}

export function App() {
  const page = useUi((s) => s.page)
  const setPage = useUi((s) => s.setPage)
  const loaded = useUi((s) => s.settings !== null)
  const [dragging, setDragging] = useState(false)
  useTheme()
  useResizerBoot()
  useConverterBoot()
  useDesignBoot()
  usePassportBoot()

  useEffect(() => {
    void useUi.getState().loadSettings().catch((e) => useUi.getState().reportError('Could not load settings', e))
  }, [])

  useShortcuts([
    { keys: 'mod+shift+h', run: () => setPage('home'), inInputs: true },
    { keys: 'mod+l', run: () => setPage('log'), inInputs: true },
    { keys: 'mod+,', run: () => setPage('settings'), inInputs: true },
    { keys: 'mod+1', run: () => setPage('resizer'), inInputs: true },
    { keys: 'mod+2', run: () => setPage('converter'), inInputs: true },
    { keys: 'mod+3', run: () => setPage('design'), inInputs: true },
    { keys: 'mod+4', run: () => setPage('passport'), inInputs: true }
  ])

  return (
    <div className="app"
      onDragEnter={(e) => { if (e.dataTransfer.types.includes('Files')) setDragging(true) }}
      onDragOver={(e) => e.preventDefault()}
      onDragLeave={(e) => { if (e.currentTarget === e.target || !e.relatedTarget) setDragging(false) }}
      onDrop={(e) => { setDragging(false); void handleDrop(e).catch((err) => useUi.getState().reportError('Could not add the files', err)) }}>
      <nav className="sidebar" aria-label="Modules">
        <button className="brand" onClick={() => setPage('home')} title="Home" data-testid="brand"><Icon name="shield" size={20} /> <span className="brand-name">Offline Toolkit</span></button>
        {NAV.map((n) => (
          <button key={n.page} className={`nav-item ${page === n.page ? 'active' : ''}`} data-testid={`nav-${n.page}`}
            aria-label={n.label} title={n.label}
            aria-current={page === n.page ? 'page' : undefined} onClick={() => setPage(n.page)}>
            <Icon name={n.icon} /> <span className="nav-label">{n.label}</span>
            {n.phase && <span className="soon">soon</span>}
          </button>
        ))}
        <div className="sidebar-foot muted small">
          <Icon name="shield" size={14} /> Works offline. Files never leave this computer.
          <div>{modLabel}+Shift+H home · {modLabel}+L log · {modLabel}+, settings</div>
        </div>
      </nav>
      <div className="page">
        {!loaded ? <div className="empty-view"><span className="spinner" /> Starting…</div> : (
          <>
            {page === 'home' && <HomePage />}
            {page === 'resizer' && <ResizerPage />}
            {page === 'converter' && <ConverterPage />}
            {page === 'design' && <DesignPage />}
            {page === 'passport' && <PassportPage />}
            {page === 'log' && <LogPage />}
            {page === 'settings' && <SettingsPage />}
          </>
        )}
      </div>
      {dragging && page !== 'home' && <div className="drop-overlay" aria-hidden><div>{DROP_HINT[page] ?? 'Drop images or a folder to add them'}</div></div>}
      <ImageChooser />
      <Toasts />
    </div>
  )
}
