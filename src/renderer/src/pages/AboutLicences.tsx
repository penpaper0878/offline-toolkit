import { useEffect, useMemo, useState } from 'react'
import type { CopyleftLevel, LicenceComponent, LicenceInfo, LicenceKind } from '@shared/types'
import { otk } from '../lib/api'
import { useUi } from '../lib/ui-store'
import { Modal } from '../components/controls'
import { Icon } from '../components/Icon'

const KIND_LABEL: Record<LicenceKind, string> = {
  runtime: 'Application runtime', javascript: 'JavaScript libraries', python: 'Python packages', native: 'Native libraries',
  engine: 'Conversion engines', java: 'veraPDF’s Java libraries', font: 'Fonts', model: 'Models'
}
const LEVEL_LABEL: Record<CopyleftLevel, string> = { network: 'AGPL', strong: 'GPL', weak: 'Weak copyleft', none: 'Permissive' }

type Filter = 'all' | 'copyleft' | LicenceKind

function LicenceText(props: { component: LicenceComponent; onClose: () => void }) {
  const { component: c } = props
  const [index, setIndex] = useState(0)
  const [text, setText] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    const file = c.files[index]
    if (!file) return
    setText(null)
    setError(null)
    otk().about.text(file).then(setText).catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
  }, [c, index])
  return (
    <Modal title={`${c.name} ${c.version}`.trim()} onClose={props.onClose} wide testId="licence-text-modal">
      <p className="muted small"><strong>{c.license}</strong>{c.partOf ? ` · part of ${c.partOf}` : ''}{c.where ? ` · ${c.where}` : ''}</p>
      {c.note && <p className="small" dir="auto">{c.note}</p>}
      {c.files.length > 1 && (
        <div className="row-gap wrap">
          {c.files.map((f, i) => (
            <button key={f} className={`btn small ${i === index ? '' : 'ghost'}`} onClick={() => setIndex(i)}>{f.split('/').pop()}</button>
          ))}
        </div>
      )}
      {c.files.length === 0 && <p className="muted small">No licence text is shipped for this entry; see the note above.</p>}
      {error && <p className="error-text">{error}</p>}
      {c.files.length > 0 && !error && (text === null ? <span className="spinner small" /> : <pre className="licence-text" dir="auto" data-testid="licence-text">{text}</pre>)}
    </Modal>
  )
}

/** Settings → About & licences: every bundled component with its licence, copyleft first. */
export function AboutLicences() {
  const [info, setInfo] = useState<LicenceInfo | null>(null)
  const [filter, setFilter] = useState<Filter>('all')
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState<LicenceComponent | null>(null)
  const [showWeak, setShowWeak] = useState(false)
  useEffect(() => {
    otk().about.licences().then(setInfo).catch((e) => useUi.getState().reportError('Could not read the licence list', e))
  }, [])

  const report = info?.report ?? null
  const shown = useMemo(() => {
    if (!report) return []
    const q = query.trim().toLowerCase()
    return report.components.filter((c) =>
      (filter === 'all' || (filter === 'copyleft' ? c.copyleft !== 'none' : c.kind === filter)) &&
      (!q || `${c.name} ${c.license} ${c.partOf ?? ''}`.toLowerCase().includes(q)))
  }, [report, filter, query])

  if (!info) return <span className="spinner small" />
  if (!report) {
    return (
      <p className="muted small" data-testid="about-licences">
        This development build has no licence list yet. Run <code>npm run licenses</code> (it reads the build in <code>out/</code>) to
        make one in <span dir="auto">{info.dir}</span>.
      </p>
    )
  }
  const s = report.summary
  const serious = report.components.filter((c) => c.copyleft === 'network' || c.copyleft === 'strong')
  const weak = report.components.filter((c) => c.copyleft === 'weak')
  const kinds = Object.keys(s.byKind) as LicenceKind[]
  return (
    <div className="about-licences" data-testid="about-licences">
      <p className="small">
        <strong>{report.app.name} {report.app.version}</strong>, for personal use. It is built from <strong data-testid="licence-total">{s.total}</strong> third-party
        components, each listed here with its licence and the text of that licence.
      </p>
      <div className="row-gap wrap" data-testid="licence-summary">
        {(['network', 'strong', 'weak', 'none'] as const).map((l) => s.byCopyleft[l] > 0 && (
          <span key={l} className={`status-chip ${l === 'none' ? 'good' : l === 'weak' ? '' : 'warn'}`} data-level={l}>
            {s.byCopyleft[l]} {LEVEL_LABEL[l]}
          </span>
        ))}
      </div>
      <div className="licence-flagged" data-testid="licence-flagged">
        <h4><Icon name="info" size={14} /> Copyleft: matters only if you give the app to someone else</h4>
        <p className="muted small">Running the app yourself, on any number of your own computers, places no obligations on you.</p>
        <ul>
          {serious.map((c) => (
            <li key={c.id} data-testid="licence-flag" data-level={c.copyleft}>
              <button className="link-btn" onClick={() => setOpen(c)}><strong>{c.name}</strong> {c.version}</button>: {c.license}. {c.note}
            </li>
          ))}
        </ul>
        {(['network', 'strong'] as const).filter((l) => serious.some((c) => c.copyleft === l)).map((l) => (
          <p key={l} className="muted small"><strong>{LEVEL_LABEL[l]}</strong>: {report.meaning[l]}</p>
        ))}
        <p className="muted small">
          <strong>{weak.length} weak-copyleft components</strong> (LGPL, MPL, CDDL, GPL with the Classpath exception): {report.meaning.weak}{' '}
          <button className="link-btn" onClick={() => setShowWeak((v) => !v)}>{showWeak ? 'Hide them' : 'Show them'}</button>
        </p>
        {showWeak && (
          <ul className="small" data-testid="licence-weak">
            {weak.map((c) => <li key={c.id}><button className="link-btn" onClick={() => setOpen(c)}>{c.name}</button> {c.version}: {c.license}{c.partOf ? ` (in ${c.partOf})` : ''}</li>)}
          </ul>
        )}
      </div>
      <div className="row-gap wrap">
        <label className="field licence-filter">
          <span className="field-label">Show</span>
          <select value={filter} onChange={(e) => setFilter(e.target.value as Filter)} data-testid="licence-filter">
            <option value="all">Everything ({s.total})</option>
            <option value="copyleft">Copyleft only ({s.total - s.byCopyleft.none})</option>
            {kinds.map((k) => <option key={k} value={k}>{KIND_LABEL[k]} ({s.byKind[k]})</option>)}
          </select>
        </label>
        <input type="search" className="licence-search" placeholder="Search name or licence" value={query} onChange={(e) => setQuery(e.target.value)}
          aria-label="Search the licences" data-testid="licence-search" />
      </div>
      <div className="licence-list" role="list">
        {shown.map((c) => (
          <div key={c.id} role="listitem" className="licence-row" data-testid="licence-row" data-kind={c.kind} data-copyleft={c.copyleft}>
            <button className="link-btn licence-name" onClick={() => setOpen(c)} title="Show the licence text">
              {c.name}{c.partOf && <span className="muted small"> in {c.partOf}</span>}
            </button>
            <span className="muted small">{c.version}</span>
            <span className="small licence-spdx">{c.license}</span>
            <span className={`badge level-${c.copyleft}`}>{LEVEL_LABEL[c.copyleft]}</span>
          </div>
        ))}
        {shown.length === 0 && <p className="muted small">Nothing matches.</p>}
      </div>
      <div className="row-gap wrap">
        {info.noticesFile && (
          <button className="btn small" onClick={() => void otk().shell.openPath(info.noticesFile as string)} data-testid="open-notices">
            Open the full notices file
          </button>
        )}
        {info.chromiumFile && (
          <button className="btn small ghost" onClick={() => void otk().shell.openPath(info.chromiumFile as string)}>
            Chromium’s licences
          </button>
        )}
        <span className="muted small">Listed for {report.platform}, {report.generated.slice(0, 10)}.</span>
      </div>
      {open && <LicenceText component={open} onClose={() => setOpen(null)} />}
    </div>
  )
}
