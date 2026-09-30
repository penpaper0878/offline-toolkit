import type { ItemResult, Suggestion } from '@shared/types'
import { fmtBytes, fmtNum } from '@shared/units'
import { useUi } from '../../lib/ui-store'
import { Icon } from '../../components/Icon'
import { STATUS_LABEL, statusTone } from './FileStrip'
import { useResizer } from './store'

function dpiText(r: ItemResult): string {
  const d = r.output?.dpiStored
  if (!d) return '—'
  const pair = (v?: number[]) => (v ? (v[0] === v[1] ? fmtNum(v[0], 4) : `${fmtNum(v[0], 4)} × ${fmtNum(v[1], 4)}`) : '')
  if (d.jfif) return `${pair(d.jfif)} (JFIF) · ${pair(d.exif)} (EXIF)`
  if (d.pngPpm) return `${pair(d.pngDpi)} (PNG pHYs ${pair(d.pngPpm)} px/m)`
  return `${pair(d.exif)} (EXIF)`
}

function encoderText(e: Record<string, unknown> | undefined): string {
  if (!e) return '—'
  const parts: string[] = []
  if (e.lossless) parts.push('lossless')
  if (typeof e.quality === 'number') parts.push(`quality ${e.quality}`)
  if (e.subsampling) parts.push(String(e.subsampling))
  if (e.progressive === true) parts.push('progressive')
  if (e.progressive === false) parts.push('baseline')
  if (e.optimizedHuffman === false) parts.push('standard Huffman tables')
  if (e.palette === 'exact') parts.push('palette (lossless)')
  if (e.palette === 'quantize') parts.push(`${e.colors} colours (reduced)`)
  return parts.join(' · ') || String(e.format).toUpperCase()
}

export function StatusChip({ status }: { status: ItemResult['status'] }) {
  const tone = statusTone(status)
  return (
    <span className={`status-chip ${tone}`} data-testid="status-chip" data-status={status}>
      <Icon name={tone === 'good' ? 'check' : tone === 'warn' ? 'warn' : 'x'} size={14} /> {STATUS_LABEL[status]}
    </span>
  )
}

export function ResultSummary() {
  const preview = useResizer((s) => s.preview)
  const base = useUi((s) => s.settings?.sizeUnitBase ?? 1024)
  const update = useResizer((s) => s.update)

  if (preview.status === 'idle') return <div className="summary muted">Select an image to see the result here.</div>
  if (preview.status === 'invalid') {
    return (
      <div className="summary" data-testid="summary">
        <StatusChip status="error" />
        <ul className="warnings">{preview.issues?.map((i) => <li key={i}>{i}</li>)}</ul>
      </div>
    )
  }
  if (preview.status === 'error') {
    return (
      <div className="summary" data-testid="summary">
        <StatusChip status="error" /> <span className="error-text" dir="auto">{preview.error}</span>
      </div>
    )
  }
  const r = preview.result
  const running = preview.status === 'running'
  if (!r) return <div className="summary muted">{running ? 'Working…' : ''}</div>

  const applySuggestion = (sg: Suggestion) => {
    if (sg.kind === 'dimensions' && sg.width && sg.height) update({ unit: 'px', width: sg.width, height: sg.height, lockAspect: true })
    if (sg.kind === 'format' && sg.format) update({ format: sg.format })
  }
  const out = r.output!
  const size = r.size!
  const range = r.range
  const rangeText = range && (range.min != null || range.max != null)
    ? `${range.min != null ? fmtBytes(range.min, base) : '0'} – ${range.max != null ? fmtBytes(range.max, base) : '∞'}`
    : 'no target'
  return (
    <div className={`summary ${running ? 'stale' : ''}`} data-testid="summary">
      <div className="summary-head">
        <StatusChip status={r.status} />
        {running && <span className="spinner small" aria-label="Updating" />}
        {r.message && <span className="summary-message" dir="auto">{r.message}</span>}
      </div>
      <dl className="facts">
        <div><dt>Pixels</dt><dd data-testid="out-px">{out.width} × {out.height} px</dd></div>
        <div><dt>Physical size</dt><dd>{fmtNum(size.width.actualMm, 3)} × {fmtNum(size.height.actualMm, 3)} mm ({fmtNum(size.width.actualMm / 25.4, 4)} × {fmtNum(size.height.actualMm / 25.4, 4)} in)</dd></div>
        <div><dt>DPI in the file</dt><dd data-testid="out-dpi">{dpiText(r)}</dd></div>
        <div><dt>File size</dt><dd data-testid="out-bytes" data-bytes={out.bytes}>{fmtBytes(out.bytes, base)} ({out.bytes.toLocaleString('en-US')} bytes) · target {rangeText}</dd></div>
        <div><dt>Encoder</dt><dd>{out.format.toUpperCase()} · {encoderText(r.encoder)}{r.paddingBytes ? ` · +${r.paddingBytes.toLocaleString('en-US')} bytes padding` : ''}</dd></div>
        {typeof r.ssim === 'number' && <div><dt>Similarity</dt><dd title="SSIM against the uncompressed resize: 1.000 = identical">{fmtNum(r.ssim, 3)} SSIM</dd></div>}
        {r.source && <div><dt>Source</dt><dd dir="auto">{r.source.width} × {r.source.height} px {r.source.format}{r.source.orientation !== 1 ? ' · EXIF orientation applied' : ''}{r.source.iccName ? ` · ${r.source.iccName}` : ''}</dd></div>}
      </dl>
      {!!r.warnings?.length && (
        <ul className="warnings" data-testid="warnings">{r.warnings.map((w) => <li key={w} dir="auto">{w}</li>)}</ul>
      )}
      {!!r.suggestions?.length && (
        <div className="suggestions" data-testid="suggestions">
          <strong>Suggestions (nothing is changed unless you choose it):</strong>
          <ul>
            {r.suggestions.map((sg) => (
              <li key={sg.text}>
                <span>{sg.text}</span>
                {(sg.kind === 'dimensions' || sg.kind === 'format') && (
                  <button className="btn small" onClick={() => applySuggestion(sg)}>Use this</button>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
