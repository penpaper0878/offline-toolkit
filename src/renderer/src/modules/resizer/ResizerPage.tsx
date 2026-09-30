import { useEffect } from 'react'
import { useUi } from '../../lib/ui-store'
import { modLabel, useShortcuts } from '../../lib/shortcuts'
import { Icon } from '../../components/Icon'
import { BatchDialog } from './BatchDialog'
import { CropEditor } from './CropEditor'
import { addFolder, addImages, FileStrip } from './FileStrip'
import { OutputPanel } from './OutputPanel'
import { PresetBar } from './Presets'
import { PreviewView } from './PreviewView'
import { ResultSummary } from './ResultSummary'
import { SizePanel } from './SizePanel'
import { persistResizer, useResizer } from './store'

const ZOOMS = [0.1, 0.25, 0.5, 1, 2, 4, 8]

export function ResizerPage() {
  const files = useResizer((s) => s.files)
  const selected = useResizer((s) => s.files.find((f) => f.id === s.selectedId))
  const settings = useResizer((s) => s.history.present.settings)
  const crop = useResizer((s) => (s.selectedId ? s.history.present.crops[s.selectedId] : undefined))
  const preview = useResizer((s) => s.preview)
  const view = useResizer((s) => s.view)
  const zoom = useResizer((s) => s.zoom)
  const split = useResizer((s) => s.split)
  const outputDir = useResizer((s) => s.outputDir)
  const zip = useResizer((s) => s.zip)
  const presetId = useResizer((s) => s.presetId)
  const running = useResizer((s) => s.batch.running)
  const canUndo = useResizer((s) => s.history.past.length > 0)
  const canRedo = useResizer((s) => s.history.future.length > 0)
  const st = useResizer.getState()
  const ready = files.filter((f) => f.status === 'ready').length

  // Live preview: re-run the real pipeline shortly after anything changes.
  useEffect(() => {
    const t = setTimeout(() => void useResizer.getState().runPreview(), 300)
    return () => clearTimeout(t)
  }, [selected?.id, selected?.status, settings, crop])

  // Remember settings between sessions.
  useEffect(() => {
    const t = setTimeout(() => void persistResizer().catch(() => undefined), 700)
    return () => clearTimeout(t)
  }, [settings, outputDir, zip, presetId])

  const stepZoom = (dir: 1 | -1) => {
    const cur = zoom === 'fit' ? 1 : zoom
    const next = dir > 0 ? ZOOMS.find((z) => z > cur + 1e-9) : [...ZOOMS].reverse().find((z) => z < cur - 1e-9)
    if (next) st.setZoom(next)
    st.setView('compare')
  }

  useShortcuts([
    { keys: 'mod+o', run: () => void addImages(), inInputs: true },
    { keys: 'mod+shift+o', run: () => void addFolder(false), inInputs: true },
    { keys: 'mod+enter', run: () => !running && void st.runBatch(), inInputs: true },
    { keys: 'mod+z', run: () => st.undo() },
    { keys: 'mod+y', run: () => st.redo() },
    { keys: 'mod+shift+z', run: () => st.redo() },
    { keys: '+', run: () => stepZoom(1) },
    { keys: '-', run: () => stepZoom(-1) },
    { keys: '0', run: () => st.setZoom('fit') },
    { keys: '1', run: () => st.setZoom(1) },
    { keys: 'delete', run: () => selected && st.remove(selected.id) },
    { keys: 'arrowdown', run: () => selectOffset(1) },
    { keys: 'arrowup', run: () => selectOffset(-1) }
  ])

  function selectOffset(d: number) {
    const idx = files.findIndex((f) => f.id === selected?.id)
    const next = files[Math.min(files.length - 1, Math.max(0, idx + d))]
    if (next) st.select(next.id)
  }

  return (
    <div className="resizer">
      <header className="page-head">
        <h1>Image Resizer</h1>
        <PresetBar />
        <span className="spacer" />
        <button className="icon-btn" title={`Undo (${modLabel}+Z)`} aria-label="Undo" disabled={!canUndo} onClick={st.undo}><Icon name="undo" /></button>
        <button className="icon-btn" title={`Redo (${modLabel}+Y)`} aria-label="Redo" disabled={!canRedo} onClick={st.redo}><Icon name="redo" /></button>
        <button className="btn primary" data-testid="process" disabled={!ready || running} onClick={() => void st.runBatch()}
          title={`Process all (${modLabel}+Enter)`}>
          <Icon name="play" size={16} /> {ready > 1 ? `Process ${ready} images` : 'Process image'}
        </button>
      </header>
      <div className="resizer-body">
        <aside className="settings-panel" aria-label="Resize settings">
          <SizePanel />
          <OutputPanel />
        </aside>
        <main className="workspace">
          <FileStrip />
          <div className="view-bar">
            <div className="segmented" role="tablist">
              <button role="tab" aria-selected={view === 'crop'} className={view === 'crop' ? 'on' : ''} disabled={settings.fit !== 'crop'}
                title={settings.fit !== 'crop' ? 'The crop window is used in “Crop to fill” mode' : undefined}
                onClick={() => st.setView('crop')} data-testid="tab-crop">Crop window</button>
              <button role="tab" aria-selected={view === 'compare'} className={view === 'compare' ? 'on' : ''}
                onClick={() => st.setView('compare')} data-testid="tab-compare">Before / after</button>
            </div>
            {view === 'compare' && (
              <>
                <label className="inline-field">Zoom
                  <input type="range" min={10} max={800} step={5} data-testid="zoom"
                    value={zoom === 'fit' ? 100 : Math.round(zoom * 100)} onChange={(e) => st.setZoom(Number(e.target.value) / 100)} />
                  <span className="mono">{zoom === 'fit' ? 'fit' : `${Math.round(zoom * 100)}%`}</span>
                </label>
                <button className="btn small ghost" onClick={() => st.setZoom('fit')}>Fit</button>
                <button className="btn small ghost" onClick={() => st.setZoom(1)}>100%</button>
                <label className="inline-field">Split
                  <input type="range" min={0} max={100} value={split} onChange={(e) => st.setSplit(Number(e.target.value))} />
                </label>
              </>
            )}
          </div>
          <div className="view-area">
            {!selected && <div className="empty-view">
              <Icon name="resize" size={40} />
              <p>Add images to start: drag them here, or press {modLabel}+O.</p>
              <p className="muted small">JPG, PNG, WEBP, BMP, TIFF and HEIC. Everything stays on this computer.</p>
            </div>}
            {selected?.status === 'error' && <div className="empty-view error-text" dir="auto">{selected.error}</div>}
            {selected?.status === 'loading' && <div className="empty-view"><span className="spinner" /> Loading…</div>}
            {selected?.status === 'ready' && view === 'crop' && settings.fit === 'crop' && <CropEditor file={selected} />}
            {selected?.status === 'ready' && (view === 'compare' || settings.fit !== 'crop') && (
              preview.result && preview.status !== 'error' && preview.status !== 'invalid'
                ? <PreviewView file={selected} result={preview.result} />
                : <div className="empty-view">{preview.status === 'running' ? <><span className="spinner" /> Encoding…</> : 'No preview yet.'}</div>
            )}
          </div>
          <ResultSummary />
        </main>
      </div>
      <BatchDialog />
    </div>
  )
}

export function useResizerBoot(): void {
  const settings = useUi((s) => s.settings)
  useEffect(() => {
    if (!settings) return
    useResizer.getState().init(settings)
    void useResizer.getState().loadPresets()
  }, [settings !== null])
}
