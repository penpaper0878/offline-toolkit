import { fmtBytes } from '@shared/units'
import { basename, otk } from '../../lib/api'
import { useUi } from '../../lib/ui-store'
import { Modal, ProgressBar } from '../../components/controls'
import { StatusChip } from './ResultSummary'
import { useResizer } from './store'

export function BatchDialog() {
  const batch = useResizer((s) => s.batch)
  const base = useUi((s) => s.settings?.sizeUnitBase ?? 1024)
  const { cancelBatch, closeBatch } = useResizer.getState()
  if (!batch.open) return null
  const p = batch.progress
  const res = batch.result
  return (
    <Modal title={batch.running ? 'Processing images…' : 'Results'} wide testId="batch-dialog"
      onClose={batch.running ? undefined : closeBatch}
      footer={batch.running ? (
        <button className="btn danger" onClick={() => void cancelBatch()} data-testid="batch-cancel">Cancel</button>
      ) : (
        <>
          {res?.zipPath && <button className="btn" onClick={() => void otk().shell.showItem(res.zipPath!)}>Show ZIP</button>}
          {res && <button className="btn" onClick={() => void otk().shell.openPath(res.outputDir)}>Open output folder</button>}
          <span className="spacer" />
          <button className="btn primary" onClick={closeBatch} data-testid="batch-close">Close</button>
        </>
      )}>
      {batch.running && p && (
        <div className="stack">
          <ProgressBar value={p.fraction} label="Batch progress" />
          <span className="muted" dir="auto">{p.message}</span>
        </div>
      )}
      {batch.error && !batch.running && <p className="error-text">{batch.error}</p>}
      {res && (
        <>
          <p data-testid="batch-counts">
            {Object.entries(res.counts).map(([k, v]) => `${v} ${k.replace('_', ' ')}`).join(' · ')}
            {res.zipPath && <> · ZIP: <span dir="auto">{basename(res.zipPath)}</span></>}
          </p>
          <div className="table-wrap">
            <table className="table" data-testid="batch-table">
              <thead>
                <tr><th>Image</th><th>Status</th><th>Saved as</th><th>Pixels</th><th>DPI</th><th>Size</th><th>Note</th></tr>
              </thead>
              <tbody>
                {res.results.map((r, i) => (
                  <tr key={`${r.path}-${i}`}>
                    <td dir="auto">{basename(r.path ?? '')}</td>
                    <td><StatusChip status={r.status} /></td>
                    <td dir="auto">{r.outputPath ? basename(r.outputPath) : '—'}</td>
                    <td>{r.output ? `${r.output.width} × ${r.output.height}` : '—'}</td>
                    <td>{r.size ? `${Math.round(r.size.width.dpi * 1000) / 1000}` : '—'}</td>
                    <td>{r.output ? fmtBytes(r.output.bytes, base) : '—'}</td>
                    <td className="small" dir="auto">{[r.message, ...(r.warnings ?? [])].filter(Boolean).join(' ')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </Modal>
  )
}
