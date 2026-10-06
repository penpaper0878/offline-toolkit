import { useEffect, useState } from 'react'
import { Image as KImage, Layer, Stage } from 'react-konva'
import { modLabel, useShortcuts } from '../../lib/shortcuts'
import { useUi } from '../../lib/ui-store'
import { Icon } from '../../components/Icon'
import { useElementSize, useHtmlImage } from '../resizer/CropEditor'
import { StepCrop } from './StepCrop'
import { StepFinish } from './StepFinish'
import { StepSize } from './StepSize'
import { STEPS, usePassport } from './store'

const IMAGE_RE = /\.(jpe?g|jpe|jfif|png|webp|bmp|tiff?|heic|heif|hif)$/i

/** A dropped picture opens in the wizard. */
export async function dropToPassport(paths: string[]): Promise<boolean> {
  const img = paths.find((p) => IMAGE_RE.test(p))
  if (!img) return false
  await usePassport.getState().open(img)
  return true
}

export function usePassportBoot(): void {
  const settings = useUi((s) => s.settings)
  useEffect(() => {
    if (settings) void usePassport.getState().init().catch((e) => useUi.getState().reportError('Passport presets could not be loaded', e))
  }, [settings !== null]) // eslint-disable-line react-hooks/exhaustive-deps
}

function Stepper() {
  const step = usePassport((s) => s.step)
  const photo = usePassport((s) => s.photo)
  const busy = usePassport((s) => s.busy)
  return (
    <ol className="stepper" aria-label="Steps" data-testid="passport-stepper">
      {STEPS.map((label, i) => {
        const reachable = i === 0 || (photo !== null && busy === null)
        return (
          <li key={label} className={`${i === step ? 'current' : ''} ${i < step ? 'done' : ''}`}>
            <button disabled={!reachable} aria-current={i === step ? 'step' : undefined} data-testid={`passport-step-${i + 1}`}
              onClick={() => void usePassport.getState().setStep(i)}>
              <span className="step-num">{i < step ? <Icon name="check" size={14} /> : i + 1}</span> {label}
            </button>
          </li>
        )
      })}
    </ol>
  )
}

function Viewer({ url }: { url: string }) {
  const [boxRef, box] = useElementSize<HTMLDivElement>()
  const img = useHtmlImage(url)
  const [view, setView] = useState<{ z: number; x: number; y: number } | null>(null)
  useEffect(() => setView(null), [url, box.w, box.h])
  const fitZ = img && box.w ? Math.min((box.w - 32) / img.width, (box.h - 32) / img.height, 4) : 1
  const v = view ?? (img ? { z: fitZ, x: (box.w - img.width * fitZ) / 2, y: (box.h - img.height * fitZ) / 2 } : { z: 1, x: 0, y: 0 })
  return (
    <div ref={boxRef} className="passport-viewer" data-testid="passport-viewer" data-zoom={v.z}
      onWheel={(e) => {
        if (!img) return
        const r = (e.currentTarget as HTMLDivElement).getBoundingClientRect()
        const mx = e.clientX - r.left, my = e.clientY - r.top
        const z = Math.max(fitZ * 0.5, Math.min(16, v.z * Math.exp(-e.deltaY * 0.0015)))
        setView({ z, x: mx - ((mx - v.x) * z) / v.z, y: my - ((my - v.y) * z) / v.z })
      }}>
      {box.w > 0 && img && (
        <Stage width={box.w} height={box.h}>
          <Layer>
            <KImage image={img} x={v.x} y={v.y} width={img.width * v.z} height={img.height * v.z} draggable
              onDragEnd={(e) => setView({ ...v, x: e.target.x(), y: e.target.y() })} />
          </Layer>
        </Stage>
      )}
      <div className="viewer-tools">
        <button className="icon-btn" title="Fit" aria-label="Fit" onClick={() => setView(null)}><Icon name="fit" size={16} /></button>
        <span className="zoom-label">{Math.round(v.z * 100 / (usePassport.getState().photo?.preview.scale ?? 1))}%</span>
      </div>
    </div>
  )
}

function StepBrowse() {
  const photo = usePassport((s) => s.photo)
  const st = usePassport.getState()
  if (!photo) {
    return (
      <div className="passport-drop" data-testid="passport-drop">
        <Icon name="passport" size={44} />
        <h2>Make a passport or ID photo</h2>
        <p className="muted">Open, drop or paste a photo (JPG, PNG, WEBP, HEIC). It never leaves this computer.</p>
        <div className="row">
          <button className="btn primary" data-testid="passport-open" onClick={() => void st.openDialog()}><Icon name="open" size={16} /> Open a photo… <kbd>{modLabel}+O</kbd></button>
          <button className="btn" onClick={() => void st.paste()}><Icon name="paste" size={16} /> Paste <kbd>{modLabel}+V</kbd></button>
        </div>
        <p className="muted small">The app checks the photo against the rules you choose and shows hints. It cannot promise that an office will accept a photo.</p>
      </div>
    )
  }
  return (
    <div className="passport-browse">
      <Viewer url={photo.preview.url} />
      <div className="browse-info" data-testid="passport-photo-info">
        <span><strong>{photo.path.split(/[\\/]/).pop()}</strong></span>
        <span>{photo.width} × {photo.height} px{photo.meta.orientation && photo.meta.orientation !== 1 ? ' (turned upright from the camera’s orientation)' : ''}</span>
        {photo.meta.dpi && <span>{Math.round(photo.meta.dpi[0])} DPI in the file</span>}
        <span className="spacer" />
        <button className="btn small" onClick={() => void st.openDialog()}><Icon name="open" size={14} /> Another photo…</button>
      </div>
    </div>
  )
}

export function PassportPage() {
  const step = usePassport((s) => s.step)
  const photo = usePassport((s) => s.photo)
  const busy = usePassport((s) => s.busy)
  usePassport((s) => s.history)
  const st = usePassport.getState()
  useShortcuts([
    { keys: 'mod+o', run: () => void st.openDialog() },
    { keys: 'mod+v', run: () => void st.paste() },
    { keys: 'mod+z', run: () => st.undo() },
    { keys: 'mod+shift+z', run: () => st.redo() },
    { keys: 'mod+y', run: () => st.redo() },
    { keys: 'mod+enter', run: () => { if (photo && step < 3) void st.setStep(step + 1) } }
  ])
  return (
    <div className="passport" data-testid="passport-page">
      <header className="page-head passport-head">
        <h1>Passport Photo</h1>
        <Stepper />
        <span className="spacer" />
        <button className="icon-btn" title={`Undo (${modLabel}+Z)`} aria-label="Undo" disabled={!st.canUndo()} onClick={() => st.undo()} data-testid="passport-undo"><Icon name="undo" size={16} /></button>
        <button className="icon-btn" title={`Redo (${modLabel}+Shift+Z)`} aria-label="Redo" disabled={!st.canRedo()} onClick={() => st.redo()} data-testid="passport-redo"><Icon name="redo" size={16} /></button>
      </header>
      <div className="passport-body">
        {step === 0 && <StepBrowse />}
        {step === 1 && photo && <StepCrop />}
        {step === 2 && photo && <StepSize />}
        {step === 3 && photo && <StepFinish />}
        {busy && <div className="passport-busy" role="status"><span className="spinner" /> {busy}</div>}
      </div>
      <footer className="passport-foot">
        <button className="btn" disabled={step === 0 || busy !== null} onClick={() => void st.setStep(step - 1)} data-testid="passport-back"><Icon name="arrow-left" size={16} /> Back</button>
        <span className="muted small">{STEPS[step]} — step {step + 1} of {STEPS.length}</span>
        <span className="spacer" />
        {step < 3 && (
          <button className="btn primary" disabled={!photo || busy !== null} onClick={() => void st.setStep(step + 1)} data-testid="passport-next">
            Next: {STEPS[step + 1]} <Icon name="arrow-right" size={16} />
          </button>
        )}
      </footer>
    </div>
  )
}

