import { type ReactElement, useEffect, useState } from 'react'
import type { DesignExportFormat } from '@shared/types'
import { Icon } from '../../components/Icon'
import { Modal, ProgressBar, Segmented, Toggle } from '../../components/controls'
import { basename, otk } from '../../lib/api'
import { modLabel, useShortcuts } from '../../lib/shortcuts'
import { useUi } from '../../lib/ui-store'
import { CanvasView, useView } from './CanvasView'
import { CheckPanel, Inspector, LayersPanel } from './Panels'
import { useDesign } from './store'

const LANGS: Record<string, string> = {
  eng: 'English', hin: 'Hindi', mar: 'Marathi', san: 'Sanskrit', ben: 'Bengali', guj: 'Gujarati', pan: 'Punjabi', tam: 'Tamil',
  tel: 'Telugu', kan: 'Kannada', mal: 'Malayalam', ori: 'Odia', urd: 'Urdu', ara: 'Arabic', heb: 'Hebrew', nep: 'Nepali',
  fra: 'French', deu: 'German', spa: 'Spanish', ita: 'Italian', por: 'Portuguese', rus: 'Russian', chi_sim: 'Chinese (simpl.)'
}

const FORMATS: { value: DesignExportFormat; label: string; hint: string }[] = [
  { value: 'pptx', label: 'PowerPoint', hint: 'Best for editing each element: text boxes, shapes, freeform graphics, native tables and pictures on one slide.' },
  { value: 'docx', label: 'Word', hint: 'One page with floating text boxes, shapes, graphics, pictures and native tables. The fonts are embedded.' },
  { value: 'svg', label: 'SVG', hint: 'Layered vector file (one group per layer, text kept as text, fonts embedded) for Inkscape, Illustrator or a browser.' },
  { value: 'html', label: 'HTML', hint: 'A single web page: click any text or table cell to edit it in the browser. Prints at the design size.' },
  { value: 'otkd', label: 'Project', hint: 'This design with all its layers and pictures, to open again in Offline Toolkit on any computer.' }
]

export function useDesignBoot(): void {
  const settings = useUi((s) => s.settings)
  useEffect(() => {
    if (settings) useDesign.getState().init(settings)
  }, [settings])
}

/** Drop handler: an image starts an analysis, a .otkd file opens. */
export async function dropToDesign(paths: string[]): Promise<boolean> {
  const otkd = paths.find((p) => p.toLowerCase().endsWith('.otkd'))
  if (otkd) {
    await useDesign.getState().openFile(otkd)
    return true
  }
  const img = paths.find((p) => /\.(jpe?g|jpe|jfif|png|webp|bmp|dib|tiff?|heic|heif|hif)$/i.test(p))
  if (!img) return false
  if (useDesign.getState().id) {
    useUi.getState().toast('info', 'Close the current design first', 'Then drop the picture again to analyse it.')
    return true
  }
  await useDesign.getState().analyze(img)
  return true
}

function Home(): ReactElement {
  const designs = useDesign((s) => s.designs)
  const settings = useDesign((s) => s.settings)
  const st = useDesign.getState()
  const [langs, setLangs] = useState<string[]>([])
  useEffect(() => {
    void st.refreshList()
    otk().converter.catalog().then((c) => setLangs(c.ocrLanguages), () => setLangs(['eng']))
  }, [st])
  const toggleLang = (l: string) => {
    const has = settings.languages.includes(l)
    const next = has ? settings.languages.filter((x) => x !== l) : [...settings.languages, l]
    if (next.length) st.setSettings({ languages: next })
  }
  return (
    <div className="design-home" data-testid="design-home">
      <div className="design-start">
        <h2>Turn a picture into an editable design</h2>
        <p className="muted">Posters, screenshots, scanned pages, certificates, infographics, ID cards. Every text, picture, icon, shape and table becomes its own layer you can edit, then export to PowerPoint, Word, SVG or HTML.</p>
        <div className="row-gap wrap">
          <button className="btn primary" data-testid="design-open-image" onClick={() => void st.analyze()}><Icon name="image" size={16} /> Choose a picture…</button>
          <button className="btn" onClick={() => void st.openFile()}><Icon name="open" size={16} /> Open a design file (.otkd)…</button>
        </div>
        <p className="muted small">Or drop a picture anywhere in this window.</p>
        <details className="advanced">
          <summary>Reading options</summary>
          <div className="field">
            <span className="field-label">Languages in the picture</span>
            <div className="chips">
              {(langs.length ? langs : ['eng']).map((l) => (
                <button key={l} className={`chip ${settings.languages.includes(l) ? 'on' : ''}`} onClick={() => toggleLang(l)}>{LANGS[l] ?? l}</button>
              ))}
            </div>
          </div>
          <Segmented label="Enlarge small text first (offline super-resolution)" value={settings.upscale} onChange={(v) => st.setSettings({ upscale: v })}
            options={[{ value: 'auto', label: 'When text is small' }, { value: 'always', label: 'Always' }, { value: 'never', label: 'Never' }]} />
          <div className="row-gap">
            <Toggle label="Straighten tilted pictures" checked={settings.deskew} onChange={(v) => st.setSettings({ deskew: v })} />
            <Toggle label="Reduce grain on scans" checked={settings.denoise} onChange={(v) => st.setSettings({ denoise: v })} />
          </div>
        </details>
      </div>
      <section className="design-recent">
        <h3>Your designs</h3>
        {!designs.length && <p className="muted small">Designs you create are kept here until you delete them.</p>}
        <div className="design-grid">
          {designs.map((d) => (
            <div key={d.id} className="design-card" data-testid="design-card">
              <button className="design-thumb" onClick={() => void st.openDesign(d.id)} title={`Open ${d.name}`}>
                {d.thumbUrl ? <img src={d.thumbUrl} alt="" /> : <Icon name="design" size={28} />}
              </button>
              <div className="design-card-foot">
                <div className="ellipsis" title={d.name}>{d.name}</div>
                <div className="muted small">{d.width} × {d.height} · {d.layers} layers · {new Date(d.modified).toLocaleDateString()}</div>
              </div>
              <button className="icon-btn tiny design-card-del" aria-label={`Delete ${d.name}`} title="Delete"
                onClick={() => { if (window.confirm(`Delete the design "${d.name}"? This cannot be undone.`)) void st.deleteDesign(d.id) }}>
                <Icon name="trash" size={14} />
              </button>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}

function Analyzing(): ReactElement {
  const job = useDesign((s) => s.job)!
  return (
    <div className="empty-view design-analyzing" data-testid="design-analyzing">
      <h2>Analysing {basename(job.source)}</h2>
      <div style={{ width: 420 }}><ProgressBar value={job.fraction} label="Analysis progress" /></div>
      <div className="muted">{job.message}…</div>
      <button className="btn" onClick={() => void useDesign.getState().cancelAnalysis()}>Cancel</button>
    </div>
  )
}

function ExportDialog({ onClose }: { onClose: () => void }): ReactElement {
  const settings = useDesign((s) => s.settings)
  const busy = useDesign((s) => s.busy)
  const st = useDesign.getState()
  const [format, setFormat] = useState<DesignExportFormat>(settings.exportFormat)
  const [fontsFolder, setFontsFolder] = useState(settings.fontsFolder)
  const hint = FORMATS.find((f) => f.value === format)!.hint
  return (
    <Modal title="Export the design" onClose={onClose} testId="design-export-dialog" footer={
      <>
        <button className="btn ghost" onClick={onClose}>Close</button>
        <button className="btn primary" data-testid="design-export-go" disabled={!!busy}
          onClick={() => void st.exportAs(format, fontsFolder).then(onClose)}><Icon name="export" size={16} /> Export…</button>
      </>
    }>
      <Segmented label="Format" value={format} onChange={setFormat} options={FORMATS.map((f) => ({ value: f.value, label: f.label }))} testId="design-export-format" />
      <p className="muted small">{hint}</p>
      {(format === 'pptx' || format === 'docx' || format === 'svg') && (
        <Toggle label="Also save the font files next to it" checked={fontsFolder} onChange={setFontsFolder}
          hint="For sending the design to another computer that does not have these fonts." />
      )}
      {format === 'pptx' && (
        <div className="callout">
          PowerPoint uses fonts installed on the computer. Install this design's fonts once (for your user, no administrator rights needed) to see it exactly.
          <div><button className="btn small" onClick={() => void st.installFonts()}>Install the fonts</button></div>
        </div>
      )}
    </Modal>
  )
}

function Toolbar({ onExport }: { onExport: () => void }): ReactElement {
  const st = useDesign.getState()
  const canUndo = useDesign((s) => (s.history?.past.length ?? 0) > 0)
  const canRedo = useDesign((s) => (s.history?.future.length ?? 0) > 0)
  const overlay = useDesign((s) => s.overlay)
  const saveState = useDesign((s) => s.saveState)
  const highlight = useDesign((s) => s.settings.highlightLowConfidence)
  const snap = useDesign((s) => s.settings.snap)
  const busy = useDesign((s) => s.busy)
  const name = useDesign((s) => s.history?.present.source.name ?? '')
  const zoom = useView((s) => s.zoom)
  const view = useView.getState()
  const [shapeMenu, setShapeMenu] = useState(false)
  return (
    <div className="design-toolbar" role="toolbar" aria-label="Design tools">
      <button className="icon-btn" title={`Back to your designs`} aria-label="Close design" onClick={() => void st.close()}><Icon name="x" size={16} /></button>
      <span className="design-title ellipsis" title={name}>{name}</span>
      <span className={`save-state ${saveState}`} data-testid="design-save-state">{{ saved: 'Saved', dirty: 'Unsaved', saving: 'Saving…', error: 'Not saved' }[saveState]}</span>
      <span className="sep" />
      <button className="icon-btn" title={`Undo (${modLabel}+Z)`} aria-label="Undo" disabled={!canUndo} onClick={() => st.undo()}><Icon name="undo" size={16} /></button>
      <button className="icon-btn" title={`Redo (${modLabel}+Shift+Z)`} aria-label="Redo" disabled={!canRedo} onClick={() => st.redo()}><Icon name="redo" size={16} /></button>
      <span className="sep" />
      <button className="btn small" data-testid="design-add-text" title="Add text (T)" onClick={() => st.addText()}><Icon name="text" size={15} /> Text</button>
      <div className="menu-wrap">
        <button className="btn small" data-testid="design-add-shape" onClick={() => setShapeMenu(!shapeMenu)} aria-expanded={shapeMenu}><Icon name="square" size={15} /> Shape ▾</button>
        {shapeMenu && (
          <div className="menu" onMouseLeave={() => setShapeMenu(false)}>
            {([['rect', 'Rectangle', 'square'], ['rounded', 'Rounded rectangle', 'square'], ['ellipse', 'Ellipse', 'circle'], ['line', 'Line', 'line']] as const).map(([k, label, icon]) => (
              <button key={k} className="menu-item" onClick={() => { st.addShape(k); setShapeMenu(false) }}><Icon name={icon} size={15} /> {label}</button>
            ))}
          </div>
        )}
      </div>
      <button className="btn small" onClick={() => void st.addImage()}><Icon name="image" size={15} /> Picture</button>
      <span className="sep" />
      <button className="icon-btn" title="Zoom out" aria-label="Zoom out" onClick={() => view.zoomBy(1 / 1.25)}><Icon name="zoom-out" size={16} /></button>
      <span className="zoom-label">{Math.round(zoom * 100)}%</span>
      <button className="icon-btn" title="Zoom in" aria-label="Zoom in" onClick={() => view.zoomBy(1.25)}><Icon name="zoom-in" size={16} /></button>
      <button className="icon-btn" title={`Fit (${modLabel}+0)`} aria-label="Fit to window" onClick={() => view.fit()}><Icon name="fit" size={16} /></button>
      <span className="sep" />
      <Segmented value={overlay} onChange={(v) => st.setOverlay(v)} testId="design-compare"
        options={[{ value: 'off', label: 'Design' }, { value: 'split', label: 'Compare', title: 'Slide between the original picture and the rebuilt design' }, { value: 'diff', label: 'Difference', title: 'Black where they match; anything bright differs' }]} />
      <button className={`icon-btn ${highlight ? 'on' : ''}`} title="Highlight words the OCR was unsure of" aria-label="Highlight words to check"
        onClick={() => st.setSettings({ highlightLowConfidence: !highlight })}><Icon name="warn" size={16} /></button>
      <button className={`icon-btn ${snap ? 'on' : ''}`} title="Snap to edges and centres (hold Alt to move freely)" aria-label="Snap"
        onClick={() => st.setSettings({ snap: !snap })}><Icon name="fit" size={16} /></button>
      <span className="spacer" />
      {busy && <span className="muted small"><span className="spinner" /> {busy}</span>}
      <button className="btn primary" data-testid="design-export" onClick={onExport}><Icon name="export" size={16} /> Export</button>
    </div>
  )
}

function Editor(): ReactElement {
  const st = useDesign.getState()
  const [tab, setTab] = useState<'layer' | 'check'>('layer')
  const [exporting, setExporting] = useState(false)
  const selection = useDesign((s) => s.selection)
  const editing = useDesign((s) => s.editingText)
  useEffect(() => {
    if (selection.length) setTab('layer')
  }, [selection])
  const view = useView.getState()
  useShortcuts([
    { keys: 'mod+z', run: () => st.undo() },
    { keys: 'mod+shift+z', run: () => st.redo() },
    { keys: 'mod+y', run: () => st.redo() },
    { keys: 'mod+s', run: () => void st.save(), inInputs: true },
    { keys: 'mod+e', run: () => setExporting(true), inInputs: true },
    { keys: 'mod+d', run: () => st.duplicateSelected() },
    { keys: 'delete', run: () => st.removeSelected() },
    { keys: 'backspace', run: () => st.removeSelected() },
    { keys: 'escape', run: () => st.select([]) },
    { keys: 'mod+]', run: () => st.reorderSelected(1) },
    { keys: 'mod+[', run: () => st.reorderSelected(-1) },
    { keys: 'mod+0', run: () => view.fit() },
    { keys: 'mod++', run: () => view.zoomBy(1.25) },
    { keys: 'mod+-', run: () => view.zoomBy(1 / 1.25) },
    { keys: 't', run: () => st.addText() },
    { keys: 'enter', run: () => { const s = useDesign.getState(); const id = s.selection[0]; const l = s.history?.present.layers.find((x) => x.id === id); if (l?.type === 'text') s.setEditingText(id) } },
    { keys: 'arrowleft', run: () => st.nudge(-1, 0) }, { keys: 'arrowright', run: () => st.nudge(1, 0) },
    { keys: 'arrowup', run: () => st.nudge(0, -1) }, { keys: 'arrowdown', run: () => st.nudge(0, 1) },
    { keys: 'shift+arrowleft', run: () => st.nudge(-10, 0) }, { keys: 'shift+arrowright', run: () => st.nudge(10, 0) },
    { keys: 'shift+arrowup', run: () => st.nudge(0, -10) }, { keys: 'shift+arrowdown', run: () => st.nudge(0, 10) }
  ], !editing)
  return (
    <div className="design-editor" data-testid="design-editor">
      <Toolbar onExport={() => setExporting(true)} />
      <div className="design-body">
        <LayersPanel />
        <CanvasView />
        <aside className="design-side">
          <div className="segmented tabs" role="tablist">
            <button role="tab" aria-selected={tab === 'layer'} className={tab === 'layer' ? 'on' : ''} onClick={() => setTab('layer')}>Edit</button>
            <button role="tab" aria-selected={tab === 'check'} className={tab === 'check' ? 'on' : ''} data-testid="design-tab-check" onClick={() => setTab('check')}>Check</button>
          </div>
          <div className="design-side-body">{tab === 'layer' ? <Inspector /> : <CheckPanel />}</div>
        </aside>
      </div>
      {exporting && <ExportDialog onClose={() => setExporting(false)} />}
    </div>
  )
}

export function DesignPage(): ReactElement {
  const job = useDesign((s) => s.job)
  const id = useDesign((s) => s.id)
  return (
    <div className="design-page">
      {job ? <Analyzing /> : id ? <Editor /> : <Home />}
    </div>
  )
}
