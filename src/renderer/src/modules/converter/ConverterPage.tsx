import { type ReactElement, useEffect, useMemo, useState } from 'react'
import type { ConverterCatalog, FidelityMode, Paper, PreflightResult, Verdict } from '@shared/types'
import { fmtBytes } from '@shared/units'
import { Icon } from '../../components/Icon'
import { Modal, NumberField, ProgressBar, Section, Segmented, Select, Toggle } from '../../components/controls'
import { basename, otk } from '../../lib/api'
import { modLabel, useShortcuts } from '../../lib/shortcuts'
import { useUi } from '../../lib/ui-store'
import { type DocFile, useConverter } from './store'

const TARGET_GROUPS: { label: string; ids: string[] }[] = [
  { label: 'Documents', ids: ['pdf', 'pdfa1b', 'pdfa2b', 'pdfa3b', 'docx', 'xlsx', 'pptx', 'html', 'txt', 'epub'] },
  { label: 'Images', ids: ['png', 'jpeg', 'svg'] }
]
const SHORT: Record<string, string> = {
  pdf: 'PDF', pdfa1b: 'PDF/A-1b', pdfa2b: 'PDF/A-2b', pdfa3b: 'PDF/A-3b', docx: 'Word', xlsx: 'Excel', pptx: 'PowerPoint',
  html: 'HTML', txt: 'Text', epub: 'EPUB', png: 'PNG', jpeg: 'JPEG', svg: 'SVG'
}
const LANGS: Record<string, string> = {
  eng: 'English', hin: 'Hindi', mar: 'Marathi', san: 'Sanskrit', ben: 'Bengali', guj: 'Gujarati', pan: 'Punjabi', tam: 'Tamil',
  tel: 'Telugu', kan: 'Kannada', mal: 'Malayalam', ori: 'Odia', urd: 'Urdu', ara: 'Arabic', heb: 'Hebrew', nep: 'Nepali',
  fra: 'French', deu: 'German', spa: 'Spanish', ita: 'Italian', por: 'Portuguese', rus: 'Russian', chi_sim: 'Chinese (simpl.)'
}
const PDF_TARGETS = new Set(['pdf', 'pdfa1b', 'pdfa2b', 'pdfa3b'])
const VERDICT: Record<Verdict, { label: string; tone: string; icon: string; hint: string }> = {
  perfect: { label: 'Perfect', tone: 'good', icon: 'check', hint: 'Every check passed and nothing was changed.' },
  expected: { label: 'Expected changes', tone: 'warn', icon: 'check', hint: 'Nothing failed; the report lists what this route changes.' },
  review: { label: 'Needs review', tone: 'bad', icon: 'warn', hint: 'At least one check failed. Open the report before using the file.' }
}

function formatLabel(catalog: ConverterCatalog | null, id: string | undefined): string {
  if (!id) return ''
  return catalog?.formats.find((f) => f.id === id)?.label ?? id.toUpperCase()
}

export async function addDocuments(): Promise<void> {
  const paths = await otk().dialogs.openDocuments()
  if (paths.length) await useConverter.getState().addPaths(paths)
}

async function addDocumentFolder(): Promise<void> {
  const folder = await otk().dialogs.openFolder()
  if (!folder) return
  const paths = await otk().files.listDocuments(folder, false)
  if (!paths.length) useUi.getState().toast('warn', 'No documents in that folder')
  else await useConverter.getState().addPaths(paths)
}

export function ConverterPage() {
  const st = useConverter.getState()
  const catalogError = useConverter((s) => s.catalogError)
  const files = useConverter((s) => s.files)
  const settings = useConverter((s) => s.history.present)
  const running = useConverter((s) => s.run.running)
  const canUndo = useConverter((s) => s.history.past.length > 0)
  const canRedo = useConverter((s) => s.history.future.length > 0)
  const [openId, setOpenId] = useState<string | null>(null)
  const ready = files.filter((f) => f.status === 'ready').length

  useEffect(() => {
    if (!useConverter.getState().catalog) void useConverter.getState().loadCatalog()
  }, [])

  useShortcuts([
    { keys: 'mod+o', run: () => void addDocuments(), inInputs: true },
    { keys: 'mod+shift+o', run: () => void addDocumentFolder(), inInputs: true },
    { keys: 'mod+enter', run: () => !running && void st.start(), inInputs: true },
    { keys: 'mod+z', run: () => st.undo() },
    { keys: 'mod+y', run: () => st.redo() },
    { keys: 'mod+shift+z', run: () => st.redo() },
    { keys: 'escape', run: () => running && void st.cancel() }
  ])

  const open = files.find((f) => f.id === openId) ?? null

  return (
    <div className="converter">
      <header className="page-head">
        <h1>Document Converter</h1>
        <span className="spacer" />
        <button className="icon-btn" title={`Undo (${modLabel}+Z)`} aria-label="Undo" disabled={!canUndo || running} onClick={st.undo}><Icon name="undo" /></button>
        <button className="icon-btn" title={`Redo (${modLabel}+Y)`} aria-label="Redo" disabled={!canRedo || running} onClick={st.redo}><Icon name="redo" /></button>
        {running
          ? <button className="btn danger" data-testid="convert-cancel" onClick={() => void st.cancel()} title="Cancel (Esc)"><Icon name="x" size={16} /> Cancel</button>
          : <button className="btn primary" data-testid="convert" disabled={!ready} onClick={() => void st.start()} title={`Convert (${modLabel}+Enter)`}>
              <Icon name="play" size={16} /> {ready > 1 ? `Convert ${ready} files` : 'Convert'} to {SHORT[settings.target]}
            </button>}
      </header>
      <div className="converter-body">
        <aside className="settings-panel" aria-label="Conversion settings">
          <TargetSection />
          <OcrSection />
          <OptionsSection />
          <OutputSection />
        </aside>
        <main className="workspace">
          <div className="file-strip-head conv-toolbar">
            <button className="btn small" onClick={() => void addDocuments()} disabled={running} data-testid="add-docs"><Icon name="add" size={14} /> Add files</button>
            <button className="btn small ghost" onClick={() => void addDocumentFolder()} disabled={running}><Icon name="folder" size={14} /> Add folder</button>
            {files.length > 0 && <button className="btn small ghost" onClick={st.clear} disabled={running}><Icon name="trash" size={14} /> Clear</button>}
            <span className="spacer" />
            {catalogError && <span className="error-text small">{catalogError}</span>}
            <span className="muted small">{files.length ? `${files.length} file${files.length > 1 ? 's' : ''}` : ''}</span>
          </div>
          <div className="table-wrap conv-table-wrap">
            {!files.length ? (
              <div className="empty-view">
                <Icon name="convert" size={40} />
                <p>Add documents to convert: drag them here, or press {modLabel}+O.</p>
                <p className="muted small">PDF, PDF/A, Word (DOCX, DOC), Excel (XLSX, XLS), PowerPoint (PPTX, PPT), HTML, TXT, EPUB, PNG, JPEG and SVG.<br />
                  Every conversion is checked afterwards, and you get a report.</p>
              </div>
            ) : (
              <table className="table conv-table" data-testid="conv-table">
                <thead><tr><th>File</th><th>Route</th><th>What changes</th><th>Status</th><th /></tr></thead>
                <tbody>
                  {files.map((f) => <FileRow key={f.id} f={f} onOpen={() => setOpenId(f.id)} />)}
                </tbody>
              </table>
            )}
          </div>
          <RunFooter />
        </main>
      </div>
      {open && <DetailDialog f={open} onClose={() => setOpenId(null)} />}
      <PasswordDialog />
    </div>
  )
}

function TargetSection() {
  const catalog = useConverter((s) => s.catalog)
  const settings = useConverter((s) => s.history.present)
  const running = useConverter((s) => s.run.running)
  const update = useConverter((s) => s.update)
  const modes = catalog?.formats.find((f) => f.id === settings.target)?.targetModes ?? ['exact']
  const modeMatters = modes.includes('editable')
  return (
    <Section title="Convert to">
      {TARGET_GROUPS.map((g) => (
        <div key={g.label} className="target-group">
          <span className="field-label">{g.label}</span>
          <div className="target-grid" role="radiogroup" aria-label={`Target: ${g.label}`}>
            {g.ids.map((id) => (
              <button key={id} type="button" role="radio" aria-checked={settings.target === id} disabled={running}
                className={`target ${settings.target === id ? 'on' : ''}`} data-testid={`target-${id}`}
                title={formatLabel(catalog, id)} onClick={() => update({ target: id })}>{SHORT[id]}</button>
            ))}
          </div>
        </div>
      ))}
      <Segmented<FidelityMode> label="Fidelity" value={modeMatters ? settings.mode : 'exact'} testId="mode"
        onChange={(m) => modeMatters && update({ mode: m })}
        options={[
          { value: 'exact', label: 'Exact layout', title: 'Same look: pages, positions, fonts and pictures stay where they are.' },
          { value: 'editable', label: 'Editable', title: 'Reflowed text, real headings and tables: easy to edit, the layout may change.' }
        ]} />
      <p className="muted small">{!modeMatters
        ? `${SHORT[settings.target]} has one fidelity: the result looks like the source.`
        : settings.mode === 'exact'
          ? 'Exact: pages keep their size, and text, pictures and shapes stay in place.'
          : 'Editable: headings, paragraphs and tables are rebuilt so the text flows and can be edited.'}</p>
    </Section>
  )
}

function OcrSection() {
  const catalog = useConverter((s) => s.catalog)
  const settings = useConverter((s) => s.history.present)
  const update = useConverter((s) => s.update)
  const langs = catalog?.ocrLanguages ?? []
  const toggleLang = (l: string) => {
    const on = settings.ocrLanguages.includes(l)
    const next = on ? settings.ocrLanguages.filter((x) => x !== l) : [...settings.ocrLanguages, l]
    if (next.length) update({ ocrLanguages: next })
  }
  return (
    <Section title="Text recognition (OCR)">
      <Toggle label="Recognise text in scans and photos" checked={settings.ocr} onChange={(v) => update({ ocr: v })} testId="ocr"
        hint="Scanned pages and images get a text layer (searchable) or become editable text, depending on the target." />
      {settings.ocr && (
        <div className="field">
          <span className="field-label">Languages on the page</span>
          <div className="chips" data-testid="ocr-langs">
            {langs.length === 0 && <span className="muted small">No OCR languages are installed.</span>}
            {langs.map((l) => (
              <button key={l} type="button" className={`chip ${settings.ocrLanguages.includes(l) ? 'on' : ''}`}
                aria-pressed={settings.ocrLanguages.includes(l)} onClick={() => toggleLang(l)}>{LANGS[l] ?? l}</button>
            ))}
          </div>
          <span className="muted small">Choose only the languages that appear: more languages make recognition slower and less accurate.</span>
        </div>
      )}
    </Section>
  )
}

function OptionsSection() {
  const settings = useConverter((s) => s.history.present)
  const files = useConverter((s) => s.files)
  const update = useConverter((s) => s.update)
  const sources = new Set(files.map((f) => f.preflight?.detected?.format).filter(Boolean) as string[])
  const t = settings.target
  const rows: ReactElement[] = []
  if (t === 'png' || t === 'jpeg' || t === 'svg') {
    rows.push(<NumberField key="dpi" label="Resolution of page images" value={settings.dpi} min={36} max={1200} integer suffix="DPI"
      onChange={(v) => v !== null && v >= 36 && v <= 1200 && update({ dpi: v }, 'dpi')} testId="opt-dpi"
      hint="PDF pages and drawings are rendered at this resolution (300 DPI is print quality)." />)
  }
  if (t === 'jpeg') {
    rows.push(<NumberField key="q" label="JPEG quality" value={settings.jpegQuality} min={1} max={100} integer
      onChange={(v) => v !== null && v >= 1 && v <= 100 && update({ jpegQuality: v }, 'jpegQuality')} />)
  }
  if (PDF_TARGETS.has(t)) {
    rows.push(<Select<Paper> key="paper" label="Page size for HTML, text and EPUB" value={settings.paper}
      onChange={(v) => update({ paper: v })}
      options={[{ value: 'a4', label: 'A4' }, { value: 'letter', label: 'Letter' }, { value: 'legal', label: 'Legal' }, { value: 'a3', label: 'A3' }, { value: 'a5', label: 'A5' }]} />)
  }
  if (PDF_TARGETS.has(t) && (sources.has('pptx') || sources.has('ppt'))) {
    rows.push(<Toggle key="notes" label="Add speaker-notes pages" checked={settings.notesPages} onChange={(v) => update({ notesPages: v })} />)
  }
  if (t === 'pdfa3b') {
    rows.push(<Toggle key="embed" label="Attach the source file inside the PDF/A-3" checked={settings.pdfaEmbedSource}
      onChange={(v) => update({ pdfaEmbedSource: v })} testId="opt-embed" />)
  }
  if (t === 'pdf' && [...sources].some((s) => s.startsWith('pdfa'))) {
    rows.push(<Toggle key="keep" label="Keep PDF/A files unchanged" checked={settings.keepPdfaId} onChange={(v) => update({ keepPdfaId: v })}
      hint="Off: the PDF/A identification is removed from the copy." />)
  }
  if (t === 'xlsx' && sources.has('txt')) {
    rows.push(<Toggle key="tabs" label="Split text lines into cells at tabs" checked={settings.txtSplitTabs} onChange={(v) => update({ txtSplitTabs: v })} />)
  }
  if (t === 'pptx' && sources.has('txt')) {
    rows.push(<NumberField key="lps" label="Text lines per slide" value={settings.txtLinesPerSlide} min={1} max={200} integer
      onChange={(v) => v !== null && v >= 1 && update({ txtLinesPerSlide: v }, 'lps')} />)
  }
  return (
    <Section title="Options">
      {rows}
      <Toggle label="Compare rendered pages (exact mode)" checked={settings.verifyAppearance} onChange={(v) => update({ verifyAppearance: v })}
        hint="Renders the source and the result and compares every page. Slower, but catches layout changes." />
    </Section>
  )
}

function OutputSection() {
  const outputDir = useConverter((s) => s.outputDir)
  const settings = useConverter((s) => s.history.present)
  const count = useConverter((s) => s.files.length)
  const update = useConverter((s) => s.update)
  const setOutputDir = useConverter((s) => s.setOutputDir)
  return (
    <Section title="Output">
      <div className="path-row">
        <span className="path" title={outputDir ?? ''} data-testid="conv-outdir">{outputDir ?? 'Not chosen yet'}</span>
        <button className="btn small" onClick={async () => { const d = await otk().dialogs.chooseDir(outputDir); if (d) setOutputDir(d) }}>Change…</button>
      </div>
      <span className="muted small">Existing files are never overwritten: a new name like “report (1).pdf” is used. A report is saved next to each file.</span>
      <Toggle label="Also merge all results into one file" checked={settings.merge} onChange={(v) => update({ merge: v })}
        disabled={count < 2} testId="opt-merge" hint="PDF: bookmarks per file. Word: page breaks. Excel: sheets. Images: one ZIP." />
    </Section>
  )
}

function routeText(pf: PreflightResult | null): string {
  if (!pf?.route) return ''
  return pf.route.steps.map((s) => s.engineLabel).filter((v, i, a) => a.indexOf(v) === i).join(' → ')
}

function StatusCell({ f }: { f: DocFile }) {
  if (f.status === 'running') return <div className="conv-progress"><ProgressBar value={f.progress} /><span className="muted small" dir="auto">{f.message}</span></div>
  if (f.status === 'checking') return <span className="muted small"><span className="spinner small" /> Checking…</span>
  if (f.result?.status === 'done' && f.result.verdict) {
    const v = VERDICT[f.result.verdict]
    return <span className={`status-chip ${v.tone}`} title={v.hint} data-testid="verdict" data-verdict={f.result.verdict}><Icon name={v.icon} size={14} /> {v.label}</span>
  }
  if (f.status === 'done') return <span className="status-chip good" data-testid="verdict" data-verdict="none"><Icon name="check" size={14} /> Converted</span>
  if (f.status === 'needs_password') return <span className="status-chip warn"><Icon name="lock" size={14} /> {f.password ? 'Wrong password' : 'Password needed'}</span>
  if (f.status === 'failed' || f.status === 'error' || f.status === 'blocked') return <span className="error-text small" dir="auto">{f.message || 'Cannot convert'}</span>
  if (f.status === 'cancelled') return <span className="muted small">Cancelled</span>
  return <span className="muted small">Ready</span>
}

function FileRow({ f, onOpen }: { f: DocFile; onOpen: () => void }) {
  const catalog = useConverter((s) => s.catalog)
  const running = useConverter((s) => s.run.running)
  const pf = f.preflight
  const det = pf?.detected
  const losses = (pf?.losses?.length ?? 0) + (pf?.stepLosses?.length ?? 0)
  const res = f.result
  return (
    <tr data-testid="conv-row" data-status={f.status}>
      <td>
        <div className="conv-name" dir="auto" title={f.path}>{f.name}</div>
        <div className="muted small">
          {det ? formatLabel(catalog, det.format) : '…'}
          {det?.pages ? ` · ${det.pages} page${det.pages > 1 ? 's' : ''}` : ''}
          {det?.scannedPages?.length && det.format !== 'pdf_scanned' ? ` · ${det.scannedPages.length} scanned` : ''}
          {pf?.size != null ? ` · ${fmtBytes(pf.size, 1024)}` : ''}
          {det?.encrypted ? ' · password-protected' : ''}
        </div>
      </td>
      <td><span className="small">{routeText(pf)}</span>{pf?.problems?.length ? <div className="error-text small">{pf.problems[0]}</div> : null}</td>
      <td>{losses > 0
        ? <button className="link-btn" onClick={onOpen} title="See what this route cannot keep">{losses} item{losses > 1 ? 's' : ''}</button>
        : pf?.route ? <span className="muted small">Nothing expected</span> : null}</td>
      <td><StatusCell f={f} /></td>
      <td>
        <div className="row-actions">
          {res?.report && <button className="btn small" data-testid="open-report" onClick={() => void otk().shell.openPath(res.report!)}>Report</button>}
          {res?.output && <button className="icon-btn" title="Open the result" aria-label="Open the result" onClick={() => void otk().shell.openPath(res.output!)}><Icon name="play" size={14} /></button>}
          {res?.output && <button className="icon-btn" title="Show in folder" aria-label="Show in folder" onClick={() => void otk().shell.showItem(res.output!)}><Icon name="folder" size={14} /></button>}
          {f.status === 'needs_password' && <button className="btn small" onClick={() => useConverter.getState().askPassword(f.id)}>Password…</button>}
          <button className="icon-btn" title="Details" aria-label="Details" onClick={onOpen}><Icon name="log" size={14} /></button>
          {!running && <button className="icon-btn" title="Remove from the list" aria-label="Remove" onClick={() => useConverter.getState().remove(f.id)}><Icon name="x" size={14} /></button>}
        </div>
      </td>
    </tr>
  )
}

function DetailDialog({ f, onClose }: { f: DocFile; onClose: () => void }) {
  const catalog = useConverter((s) => s.catalog)
  const pf = f.preflight
  const res = f.result
  const route = res?.route ?? pf?.route
  return (
    <Modal title={f.name} onClose={onClose} wide testId="conv-detail"
      footer={<>{res?.report && <button className="btn" onClick={() => void otk().shell.openPath(res.report!)}>Open the report</button>}
        <span className="spacer" /><button className="btn" onClick={onClose}>Close</button></>}>
      <dl className="facts">
        <div><dt>Detected</dt><dd>{formatLabel(catalog, pf?.detected?.format)}</dd></div>
        <div><dt>Target</dt><dd>{formatLabel(catalog, route?.target)} ({route?.mode})</dd></div>
        {res?.output && <div><dt>Saved as</dt><dd className="mono">{basename(res.output)}</dd></div>}
        {res && <div><dt>Time</dt><dd>{res.seconds.toFixed(1)} s</dd></div>}
      </dl>
      {route && <>
        <h3>Route</h3>
        <ol className="route-steps">{route.steps.map((s, i) => <li key={i}><b>{s.engineLabel}</b>: {s.summary}</li>)}</ol>
        {route.override && <p className="muted small">Chosen on purpose: {route.override}</p>}
      </>}
      {(pf?.losses?.length || pf?.stepLosses?.length) ? <>
        <h3>What this route cannot keep</h3>
        <ul className="warnings">
          {pf?.losses?.map((l) => <li key={l.feature}>{l.label}: {l.level === 'lost' ? 'not kept' : 'kept only partly'}</li>)}
          {pf?.stepLosses?.map((l) => <li key={l}>{l}</li>)}
        </ul>
      </> : null}
      {pf?.notes?.length ? <><h3>Notes</h3><ul>{pf.notes.map((n) => <li key={n}>{n}</li>)}</ul></> : null}
      {pf?.problems?.length ? <><h3>Problems</h3><ul className="error-text">{pf.problems.map((n) => <li key={n}>{n}</li>)}</ul></> : null}
      {res && res.status === 'done' && <>
        <h3>Verification</h3>
        <p>{res.verdict ? VERDICT[res.verdict].hint : 'Not verified.'}</p>
        <p className="muted small">{Object.entries(res.summary).map(([k, v]) => `${v} ${k === 'pass' ? 'passed' : k === 'fail' ? 'failed' : k === 'expected' ? 'expected change' : 'not checked'}`).join(' · ')}</p>
      </>}
      {res && res.status !== 'done' && <p className="error-text" dir="auto">{res.message}</p>}
    </Modal>
  )
}

function RunFooter() {
  const run = useConverter((s) => s.run)
  const files = useConverter((s) => s.files)
  const start = useConverter((s) => s.start)
  const done = files.filter((f) => f.result?.status === 'done')
  const merged = run.result?.merged
  if (run.running) {
    return (
      <div className="summary conv-footer" data-testid="conv-running">
        <ProgressBar value={run.progress?.fraction ?? 0} label="Conversion progress" />
        <span className="small" dir="auto">{run.progress?.message ?? 'Starting…'}</span>
      </div>
    )
  }
  if (!run.result && !run.resumable) return null
  const counts = { perfect: 0, expected: 0, review: 0 }
  for (const f of done) if (f.result?.verdict) counts[f.result.verdict]++
  return (
    <div className="summary conv-footer" data-testid="conv-summary">
      <div className="summary-head">
        <b>{done.length} of {files.length} converted</b>
        {counts.perfect > 0 && <span className="status-chip good">{counts.perfect} perfect</span>}
        {counts.expected > 0 && <span className="status-chip warn">{counts.expected} expected changes</span>}
        {counts.review > 0 && <span className="status-chip bad">{counts.review} need review</span>}
        <span className="spacer" />
        {run.resumable && <button className="btn small" data-testid="resume" onClick={() => void start(true)}>Resume</button>}
        {run.result?.outputDir && <button className="btn small ghost" onClick={() => void otk().shell.openPath(run.result!.outputDir)}><Icon name="folder" size={14} /> Open output folder</button>}
      </div>
      {merged && (merged.status === 'done'
        ? <div className="small">Merged file: <button className="link-btn" onClick={() => void otk().shell.showItem(merged.output!)}>{basename(merged.output!)}</button>
          {merged.notes?.length ? <span className="muted"> · {merged.notes.join(' ')}</span> : null}</div>
        : <div className="error-text small">Merging failed: {merged.message}</div>)}
    </div>
  )
}

function PasswordDialog() {
  const id = useConverter((s) => s.passwordFor)
  const file = useConverter((s) => s.files.find((f) => f.id === s.passwordFor))
  const others = useConverter((s) => s.files.filter((f) => f.status === 'needs_password' && f.id !== s.passwordFor).length)
  const [pw, setPw] = useState('')
  const [all, setAll] = useState(false)
  useEffect(() => setPw(''), [id])
  const close = () => useConverter.getState().askPassword(null)
  const submit = () => pw && file && void useConverter.getState().setPassword(file.id, pw, all)
  const wrong = useMemo(() => Boolean(file?.password), [file?.password])
  if (!id || !file) return null
  return (
    <Modal title="Password needed" onClose={close} testId="password-dialog"
      footer={<><span className="spacer" /><button className="btn" onClick={close}>Skip this file</button>
        <button className="btn primary" disabled={!pw} onClick={submit} data-testid="password-ok">Open</button></>}>
      <p dir="auto"><b>{file.name}</b> is protected with a password.{wrong ? ' The password you entered was not correct.' : ''}</p>
      <label className="field">
        <span className="field-label">Password</span>
        <input type="password" autoFocus value={pw} data-testid="password-input" onChange={(e) => setPw(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && submit()} />
      </label>
      {others > 0 && <Toggle label={`Use it for the other ${others} protected file${others > 1 ? 's' : ''} in this list`} checked={all} onChange={setAll} />}
      <p className="muted small">The password is kept only while the app is open. It is never saved or written to the log. The converted file is not password-protected.</p>
    </Modal>
  )
}

export function useConverterBoot(): void {
  const settings = useUi((s) => s.settings)
  useEffect(() => {
    if (settings) useConverter.getState().init(settings)
  }, [settings !== null])
}
