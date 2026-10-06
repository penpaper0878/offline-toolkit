import { useEffect, useState } from 'react'
import { specPx, toMm } from '@shared/passport'
import { NumberField, Segmented, Select, Toggle } from '../../components/controls'
import { Icon } from '../../components/Icon'
import { otk } from '../../lib/api'
import { updateAppSettings, useUi } from '../../lib/ui-store'
import { paperOf, sheetRequest, usePassport } from './store'

type Sheet = NonNullable<ReturnType<typeof useUi.getState>['settings']>['passport']['sheet']

function useSheetSettings(): [Sheet, (patch: Partial<Sheet>) => void] {
  const s = useUi((x) => x.settings!.passport.sheet)
  const set = (patch: Partial<Sheet>) => {
    void updateAppSettings({ passport: { sheet: patch } }).then(() => void usePassport.getState().refreshSheet(),
      (e) => useUi.getState().reportError('Settings could not be saved', e))
  }
  return [s, set]
}

function SinglePhoto() {
  const render = usePassport((s) => s.render)
  const ex = useUi((x) => x.settings!.passport.export)
  const st = usePassport.getState()
  const spec = st.spec()!
  const px = specPx(spec)
  const [saving, setSaving] = useState(false)
  const set = (patch: Partial<typeof ex>) => void updateAppSettings({ passport: { export: patch } })
  const save = async () => {
    setSaving(true)
    const ex = useUi.getState().settings!.passport.export      // the latest, even if a field was changed just now
    try {
      const res = await otk().passport.exportPhoto(st.request({ format: ex.format, name: 'passport-photo',
        sizeLimit: ex.format === 'jpeg' && ex.limit ? ex.sizeLimit : null }))
      if (res) {
        const notes = res.notes.length ? ` ${res.notes.join(' ')}` : ''
        useUi.getState().toast(res.compression && !['ok', 'ok_padded'].includes(res.compression.status) ? 'warn' : 'success',
          'Photo saved', `${res.path.split(/[\\/]/).pop()}: ${res.px[0]} × ${res.px[1]} px, ${res.dpi} DPI, ${(res.bytes / 1024).toFixed(1)} KB.${notes}`)
      }
    } catch (e) {
      useUi.getState().reportError('The photo could not be saved', e)
    } finally {
      setSaving(false)
    }
  }
  return (
    <div className="finish-single" data-testid="passport-single">
      <div className="finish-preview">
        {render && <img src={render.image.url} alt="The finished photo" style={{ width: px.w > px.h ? 300 : (300 * px.w) / px.h }} />}
        <p className="muted small">{px.w} × {px.h} px at {spec.dpi} DPI = {toMm(spec.width, spec.unit).toFixed(2)} × {toMm(spec.height, spec.unit).toFixed(2)} mm
          {Math.abs(px.errorMm[0]) + Math.abs(px.errorMm[1]) > 0.001 ? ` (whole pixels print ${(px.w * 25.4 / spec.dpi).toFixed(2)} × ${(px.h * 25.4 / spec.dpi).toFixed(2)} mm; the PDF is exact)` : ''}</p>
      </div>
      <div className="finish-form">
        <Segmented label="Format" value={ex.format} onChange={(format) => set({ format })} testId="passport-format"
          options={[{ value: 'jpeg', label: 'JPG' }, { value: 'png', label: 'PNG' }, { value: 'pdf', label: 'PDF (exact size)' }]} />
        {ex.format === 'jpeg' && (
          <>
            <Toggle label="Keep the file within a size range" checked={ex.limit} onChange={(limit) => set({ limit })} testId="passport-limit"
              hint="Online forms often ask for a size range, e.g. 20–240 KB. The quality is searched; the pixel size never changes." />
            {ex.limit && (
              <div className="row">
                <NumberField label="From" value={ex.sizeLimit.min} allowEmpty min={0} width={80} onChange={(min) => set({ sizeLimit: { ...ex.sizeLimit, min } })} testId="passport-limit-min" />
                <NumberField label="To" value={ex.sizeLimit.max} allowEmpty min={0} width={80} onChange={(max) => set({ sizeLimit: { ...ex.sizeLimit, max } })} testId="passport-limit-max" />
                <Segmented label="Unit" value={ex.sizeLimit.unit} onChange={(unit) => set({ sizeLimit: { ...ex.sizeLimit, unit } })}
                  options={[{ value: 'KB', label: 'KB' }, { value: 'MB', label: 'MB' }, { value: 'B', label: 'B' }]} />
              </div>
            )}
          </>
        )}
        <button className="btn primary" disabled={saving} onClick={() => void save()} data-testid="passport-save-photo"><Icon name="save" size={16} /> {saving ? 'Saving…' : 'Save photo…'}</button>
        {ex.format === 'pdf' && <p className="muted small">Print the PDF at 100% (Actual size), not "Fit to page".</p>}
      </div>
    </div>
  )
}

function PrintSheet() {
  const papers = usePassport((s) => s.papers)
  const preview = usePassport((s) => s.sheetPreview)
  const busy = usePassport((s) => s.sheetBusy)
  const others = usePassport((s) => s.sheetPhotos)
  const mine = usePassport((s) => s.sheetMine)
  const [s, set] = useSheetSettings()
  const st = usePassport.getState()
  const paper = paperOf(papers, s)
  const [working, setWorking] = useState<string | null>(null)
  useEffect(() => { void st.refreshSheet() }, []) // eslint-disable-line react-hooks/exhaustive-deps
  const fits = preview?.layout.fits ?? false
  const exportSheet = async () => {
    setWorking('Saving the sheet…')
    try {
      const res = await otk().passport.sheet(sheetRequest(s.format, 'passport-sheet'))
      if (res) useUi.getState().toast('success', 'Sheet saved', `${res.path?.split(/[\\/]/).pop()}: ${res.layout.count} places on ${paper.name}. Print at 100% (Actual size).`)
    } catch (e) {
      useUi.getState().reportError('The sheet could not be saved', e)
    } finally {
      setWorking(null)
    }
  }
  const print = async () => {
    setWorking('Opening the print dialog…')
    try {
      const r = await otk().passport.print(sheetRequest('pdf'))
      if (!r.printed && r.reason && r.reason !== 'cancelled') useUi.getState().toast('warn', 'Not printed', r.reason)
    } catch (e) {
      useUi.getState().reportError('Printing failed', e)
    } finally {
      setWorking(null)
    }
  }
  const addPhotos = async () => {
    const paths = await otk().passport.pick(true)
    if (!paths.length) return
    usePassport.setState({ sheetPhotos: [...others, ...paths.map((p) => ({ kind: 'file' as const, path: p, name: p.split(/[\\/]/).pop() ?? p, copies: null }))] })
    void st.refreshSheet()
  }
  const setCopies = (i: number, copies: number | null) => {
    if (i < 0) usePassport.setState({ sheetMine: copies })
    else usePassport.setState({ sheetPhotos: others.map((p, j) => (j === i ? { ...p, copies } : p)) })
    void st.refreshSheet()
  }
  return (
    <div className="finish-sheet" data-testid="passport-sheet">
      <div className="sheet-preview">
        {preview?.image ? <img src={preview.image.url} alt="Print sheet preview" data-testid="passport-sheet-preview" /> : <div className="muted">Preparing the preview…</div>}
        {busy && <span className="size-rendering"><span className="spinner small" /></span>}
      </div>
      <div className="finish-form">
        <div className="row">
          <Select label="Paper" value={s.paperId} testId="passport-paper" onChange={(paperId) => set({ paperId })}
            options={[...papers.map((p) => ({ value: p.id, label: p.name })), { value: 'custom', label: 'Custom…' }]} />
          <Segmented label="Orientation" value={s.orientation} onChange={(orientation) => set({ orientation })}
            options={[{ value: 'portrait', label: 'Portrait' }, { value: 'landscape', label: 'Landscape' }]} />
        </div>
        {s.paperId === 'custom' && (
          <div className="row">
            <NumberField label="Width" value={s.custom.width} min={10} width={80} onChange={(v) => v && set({ custom: { ...s.custom, width: v } })} />
            <NumberField label="Height" value={s.custom.height} min={10} width={80} onChange={(v) => v && set({ custom: { ...s.custom, height: v } })} />
            <Segmented label="Unit" value={s.custom.unit} onChange={(unit) => set({ custom: { ...s.custom, unit } })}
              options={[{ value: 'mm', label: 'mm' }, { value: 'cm', label: 'cm' }, { value: 'in', label: 'in' }]} />
          </div>
        )}
        <Toggle label="As many photos as fit" checked={s.auto} onChange={(auto) => set({ auto })} testId="passport-autofill" />
        {!s.auto && (
          <div className="row">
            <NumberField label="Rows" value={s.rows} min={1} max={50} integer width={70} onChange={(v) => v && set({ rows: v })} testId="passport-rows" />
            <NumberField label="Columns" value={s.cols} min={1} max={50} integer width={70} onChange={(v) => v && set({ cols: v })} testId="passport-cols" />
          </div>
        )}
        <div className="row">
          <NumberField label="Margins" value={s.margins} min={0} max={100} step={0.5} suffix="mm" width={80} onChange={(v) => v !== null && set({ margins: v })} />
          <NumberField label="Gap" value={s.gutter} min={0} max={50} step={0.5} suffix="mm" width={80} onChange={(v) => v !== null && set({ gutter: v })} />
          <Toggle label="Cut marks" checked={s.cutMarks} onChange={(cutMarks) => set({ cutMarks })} />
          <Toggle label="Thin borders" checked={s.borders} onChange={(borders) => set({ borders })} />
        </div>
        {preview && (
          <div className={`sheet-status ${fits ? '' : 'bad'}`} data-testid="passport-sheet-status">
            {fits ? <>{preview.layout.rows} × {preview.layout.cols} = <strong>{preview.layout.count}</strong> photos on {paper.name}
              {preview.counts.length > 1 ? ` (${preview.counts.join(' + ')})` : ''}</> : preview.layout.problems.join(' ')}
            {preview.notes.map((n) => <div key={n} className="warn-text small">{n}</div>)}
          </div>
        )}
        <div className="sheet-people">
          <div className="row"><strong>Photos on the sheet</strong><span className="spacer" />
            <button className="btn small" onClick={() => void addPhotos()} data-testid="passport-add-person"><Icon name="add" size={14} /> Another person…</button></div>
          <ul>
            <li>This photo {others.length > 0 && <NumberField label="copies" value={mine} allowEmpty min={0} integer width={70} hint="Empty: fill the places left" onChange={(v) => setCopies(-1, v)} testId="passport-copies-mine" />}</li>
            {others.map((p, i) => (
              <li key={p.path}>{p.name}
                <NumberField label="copies" value={p.copies} allowEmpty min={0} integer width={70} hint="Empty: fill the places left" onChange={(v) => setCopies(i, v)} testId={`passport-copies-${i + 1}`} />
                <button className="icon-btn" aria-label={`Remove ${p.name}`} onClick={() => { usePassport.setState({ sheetPhotos: others.filter((_, j) => j !== i) }); void st.refreshSheet() }}><Icon name="trash" size={14} /></button>
              </li>
            ))}
          </ul>
          {others.length > 0 && <p className="muted small">Other people&apos;s photos must already be passport photos (for example saved from this app); they are printed at this photo&apos;s size.</p>}
        </div>
        <div className="row">
          <Segmented label="Save as" value={s.format} onChange={(format) => set({ format })} testId="passport-sheet-format"
            options={[{ value: 'pdf', label: 'PDF' }, { value: 'jpeg', label: 'JPG' }, { value: 'png', label: 'PNG' }]} />
          {s.format !== 'pdf' && <Segmented label="Resolution" value={String(s.dpi) as '300' | '600'} onChange={(v) => set({ dpi: Number(v) as 300 | 600 })}
            options={[{ value: '300', label: '300 DPI' }, { value: '600', label: '600 DPI' }]} />}
        </div>
        <div className="row">
          <button className="btn primary" disabled={!fits || working !== null} onClick={() => void exportSheet()} data-testid="passport-save-sheet"><Icon name="save" size={16} /> Save sheet…</button>
          <button className="btn" disabled={!fits || working !== null} onClick={() => void print()} data-testid="passport-print"><Icon name="print" size={16} /> Print…</button>
          {working && <span className="muted small"><span className="spinner small" /> {working}</span>}
        </div>
        <p className="callout small"><strong>Print at 100% / Actual size.</strong> Turn off "Fit to page" or "Scale to fit" in the print dialog, or the photos will not be the right size. Measure one printed photo with a ruler before you cut them all.</p>
      </div>
    </div>
  )
}

export function StepFinish() {
  const [tab, setTab] = useState<'single' | 'sheet'>('single')
  return (
    <div className="passport-finish">
      <div className="tabs" role="tablist">
        <button role="tab" aria-selected={tab === 'single'} className={tab === 'single' ? 'on' : ''} onClick={() => setTab('single')} data-testid="passport-tab-single">Single photo</button>
        <button role="tab" aria-selected={tab === 'sheet'} className={tab === 'sheet' ? 'on' : ''} onClick={() => setTab('sheet')} data-testid="passport-tab-sheet">Print sheet</button>
      </div>
      {tab === 'single' ? <SinglePhoto /> : <PrintSheet />}
    </div>
  )
}
