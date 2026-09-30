import { useState } from 'react'
import type { ResultStatus } from '@shared/types'
import { otk } from '../../lib/api'
import { useUi } from '../../lib/ui-store'
import { Icon } from '../../components/Icon'
import { Toggle } from '../../components/controls'
import { useResizer } from './store'

export const STATUS_LABEL: Record<ResultStatus, string> = {
  ok: 'In range',
  ok_padded: 'Padded to minimum',
  no_target: 'Saved',
  below_min: 'Below minimum',
  above_max: 'Too big',
  error: 'Error',
  cancelled: 'Cancelled'
}

export function statusTone(s?: ResultStatus): 'good' | 'warn' | 'bad' | 'none' {
  if (!s) return 'none'
  if (s === 'ok' || s === 'no_target') return 'good'
  if (s === 'ok_padded' || s === 'cancelled') return 'warn'
  return 'bad'
}

export async function addFolder(recursive: boolean): Promise<void> {
  const folder = await otk().dialogs.openFolder()
  if (!folder) return
  const files = await otk().files.listImages(folder, recursive)
  if (!files.length) {
    useUi.getState().toast('warn', 'No images found in that folder', recursive ? undefined : 'Tip: turn on “Include subfolders”.')
    return
  }
  await useResizer.getState().addPaths(files)
}

export async function addImages(): Promise<void> {
  const files = await otk().dialogs.openImages()
  if (files.length) await useResizer.getState().addPaths(files)
}

export function FileStrip() {
  const files = useResizer((s) => s.files)
  const selectedId = useResizer((s) => s.selectedId)
  const [recursive, setRecursive] = useState(false)
  const { select, remove, clear } = useResizer.getState()
  return (
    <div className="file-strip">
      <div className="file-strip-head">
        <strong>Images ({files.length})</strong>
        <button className="btn small" onClick={() => void addImages()} data-testid="add-images"><Icon name="add" size={16} /> Add images</button>
        <button className="btn small" onClick={() => void addFolder(recursive).catch((e) => useUi.getState().reportError('Could not read the folder', e))}>
          <Icon name="folder" size={16} /> Add folder
        </button>
        <Toggle label="Include subfolders" checked={recursive} onChange={setRecursive} />
        <span className="spacer" />
        {files.length > 0 && <button className="btn small ghost" onClick={clear}>Clear all</button>}
      </div>
      <div className="thumbs" role="listbox" aria-label="Images" data-testid="thumbs">
        {files.length === 0 && <div className="thumbs-empty">Drop images or a folder anywhere in this window, or use Add images (Ctrl+O).</div>}
        {files.map((f) => {
          const tone = statusTone(f.lastResult?.status)
          return (
            <div key={f.id} role="option" aria-selected={f.id === selectedId} tabIndex={0}
              className={`thumb ${f.id === selectedId ? 'selected' : ''} ${f.status}`}
              onClick={() => select(f.id)} onKeyDown={(e) => e.key === 'Enter' && select(f.id)}
              title={f.error ?? f.path}>
              <div className="thumb-img">
                {f.status === 'ready' && f.probe ? <img src={f.probe.preview.url} alt="" draggable={false} /> :
                  f.status === 'loading' ? <span className="spinner" aria-label="Loading" /> : <Icon name="warn" />}
              </div>
              <div className="thumb-name" dir="auto">{f.name}</div>
              {tone !== 'none' && <span className={`dot ${tone}`} title={STATUS_LABEL[f.lastResult!.status]} />}
              <button className="thumb-remove icon-btn" aria-label={`Remove ${f.name}`} onClick={(e) => { e.stopPropagation(); remove(f.id) }}>✕</button>
            </div>
          )
        })}
      </div>
    </div>
  )
}
