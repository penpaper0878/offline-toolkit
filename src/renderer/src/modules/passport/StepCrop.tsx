import type Konva from 'konva'
import { useEffect, useRef, useState } from 'react'
import { Group, Image as KImage, Layer, Line, Rect, Shape, Stage, Transformer } from 'react-konva'
import { type Crop, cropWithRatio, fitInside, fullCrop, rot } from '@shared/passport'
import { NumberField, Segmented } from '../../components/controls'
import { Icon } from '../../components/Icon'
import { useShortcuts } from '../../lib/shortcuts'
import { useElementSize, useHtmlImage } from '../resizer/CropEditor'
import { usePassport } from './store'

/** Turn a display-space shift of the frame into a shift of the crop centre in source pixels. */
function sourceShift(c: Crop, dx: number, dy: number, vz: number): [number, number] {
  const [a, b, cc, d] = rot(-c.angle)
  const fx = (c.flipH ? -1 : 1) * dx / vz, fy = (c.flipV ? -1 : 1) * dy / vz
  return [a * fx + b * fy, cc * fx + d * fy]
}

function ratioValue(ratio: string, specRatio: number): number | null {
  if (ratio === 'free') return null
  if (ratio === 'spec') return specRatio
  const m = /^(\d+(?:\.\d+)?):(\d+(?:\.\d+)?)$/.exec(ratio)
  return m ? Number(m[1]) / Number(m[2]) : null
}

export function StepCrop() {
  const photo = usePassport((s) => s.photo)!
  const doc = usePassport((s) => s.history.present)
  const st = usePassport.getState()
  const spec = st.spec()
  const [boxRef, box] = useElementSize<HTMLDivElement>()
  const img = useHtmlImage(photo.preview.url)
  const [live, setLive] = useState<Crop | null>(null)
  const frameRef = useRef<Konva.Rect>(null)
  const trRef = useRef<Konva.Transformer>(null)
  const groupRef = useRef<Konva.Group>(null)
  const W = photo.width, H = photo.height
  const specRatio = spec ? spec.width / spec.height : 35 / 45
  const crop = live ?? doc.crop ?? fullCrop(W, H)
  const r = ratioValue(doc.ratio, specRatio)
  const vz = box.w ? Math.min((box.w * 0.74) / crop.w, (box.h * 0.74) / crop.h) : 1
  const fw = crop.w * vz, fh = crop.h * vz
  const fx = (box.w - fw) / 2, fy = (box.h - fh) / 2
  const oneFlip = crop.flipH !== crop.flipV
  const custom = !['free', 'spec', '1:1'].includes(doc.ratio)
  const [cw, ch] = custom ? doc.ratio.split(':').map(Number) : [4, 5]

  useEffect(() => {
    if (trRef.current && frameRef.current) {
      trRef.current.nodes([frameRef.current])
      trRef.current.getLayer()?.batchDraw()
    }
  }, [img, box.w, box.h, doc.ratio])

  const commit = (c: Crop, key: string | null = null) => {
    setLive(null)
    st.update({ crop: fitInside(c, W, H) }, key)
  }
  const nudge = (dx: number, dy: number) => commit({ ...crop, cx: crop.cx + dx, cy: crop.cy + dy }, 'crop-nudge')
  useShortcuts([
    { keys: 'arrowleft', run: () => nudge(-1, 0) }, { keys: 'arrowright', run: () => nudge(1, 0) },
    { keys: 'arrowup', run: () => nudge(0, -1) }, { keys: 'arrowdown', run: () => nudge(0, 1) },
    { keys: 'shift+arrowleft', run: () => nudge(-10, 0) }, { keys: 'shift+arrowright', run: () => nudge(10, 0) },
    { keys: 'shift+arrowup', run: () => nudge(0, -10) }, { keys: 'shift+arrowdown', run: () => nudge(0, 10) },
    { keys: '[', run: () => commit({ ...crop, angle: Math.max(-45, Math.round((crop.angle - 0.1) * 10) / 10) }, 'crop-angle') },
    { keys: ']', run: () => commit({ ...crop, angle: Math.min(45, Math.round((crop.angle + 0.1) * 10) / 10) }, 'crop-angle') }
  ])

  const setRatio = (ratio: string) => {
    const rv = ratioValue(ratio, specRatio)
    st.update({ ratio, crop: rv ? cropWithRatio(crop, rv, W, H) : crop })
  }

  return (
    <div className="passport-crop">
      <div ref={boxRef} className="crop-stage passport-crop-stage" data-testid="passport-crop-stage"
        data-crop={JSON.stringify(crop)} data-vz={vz}
        onWheel={(e) => {
          const k = Math.exp(e.deltaY * 0.0012)
          const max = Math.max(W, H) * 2
          if (crop.w * k > max || crop.h * k > max || crop.w * k < 16 || crop.h * k < 16) return
          commit({ ...crop, w: crop.w * k, h: crop.h * k }, 'crop-zoom')
        }}>
        {box.w > 0 && img && (
          <Stage width={box.w} height={box.h}>
            <Layer>
              <Group ref={groupRef} x={box.w / 2} y={box.h / 2} offsetX={crop.cx} offsetY={crop.cy}
                scaleX={vz * (crop.flipH ? -1 : 1)} scaleY={vz * (crop.flipV ? -1 : 1)} rotation={oneFlip ? -crop.angle : crop.angle}
                draggable
                onDragMove={(e) => {
                  const g = e.target
                  const [sx, sy] = sourceShift(crop, g.x() - box.w / 2, g.y() - box.h / 2, vz)
                  const next = fitInside({ ...(doc.crop ?? crop), cx: (doc.crop ?? crop).cx - sx, cy: (doc.crop ?? crop).cy - sy }, W, H)
                  g.position({ x: box.w / 2, y: box.h / 2 })
                  setLive(next)
                }}
                onDragEnd={() => { if (live) commit(live, null) }}>
                <KImage image={img} width={W} height={H} />
              </Group>
              <Shape listening={false} sceneFunc={(ctx) => {
                const c = ctx._context
                c.save()
                c.beginPath()
                c.rect(0, 0, box.w, box.h)
                c.rect(fx, fy, fw, fh)
                c.fillStyle = 'rgba(10,12,16,0.62)'
                c.fill('evenodd')
                c.restore()
              }} />
              {[1, 2].map((i) => <Line key={`v${i}`} listening={false} points={[fx + (fw * i) / 3, fy, fx + (fw * i) / 3, fy + fh]} stroke="rgba(255,255,255,0.6)" strokeWidth={1} />)}
              {[1, 2].map((i) => <Line key={`h${i}`} listening={false} points={[fx, fy + (fh * i) / 3, fx + fw, fy + (fh * i) / 3]} stroke="rgba(255,255,255,0.6)" strokeWidth={1} />)}
              <Rect ref={frameRef} x={fx} y={fy} width={fw} height={fh} stroke="#4f8cff" strokeWidth={2} listening
                onTransformEnd={(e) => {
                  const n = e.target
                  const w = n.width() * n.scaleX(), h = n.height() * n.scaleY()
                  n.scaleX(1)
                  n.scaleY(1)
                  const [sx, sy] = sourceShift(crop, n.x() + w / 2 - box.w / 2, n.y() + h / 2 - box.h / 2, vz)
                  commit({ ...crop, cx: crop.cx + sx, cy: crop.cy + sy, w: w / vz, h: h / vz })
                }} />
              <Transformer ref={trRef} keepRatio={r !== null} rotateEnabled={false} flipEnabled={false} anchorSize={12}
                borderStroke="#4f8cff" anchorStroke="#4f8cff"
                enabledAnchors={r !== null ? ['top-left', 'top-right', 'bottom-left', 'bottom-right'] : undefined}
                boundBoxFunc={(o, n) => (n.width < 24 || n.height < 24 ? o : n)} />
            </Layer>
          </Stage>
        )}
        <div className="crop-dims" data-testid="passport-crop-dims">
          {Math.round(crop.w)} × {Math.round(crop.h)} px{crop.angle ? ` · ${crop.angle.toFixed(1)}°` : ''}{crop.flipH ? ' · mirrored' : ''}{crop.flipV ? ' · upside down' : ''}
        </div>
      </div>
      <aside className="passport-side">
        <section className="panel-section">
          <header><h3>Shape</h3></header>
          <Segmented value={custom ? 'custom' : doc.ratio} testId="passport-ratio" onChange={(v) => setRatio(v === 'custom' ? `${cw}:${ch}` : v)}
            options={[{ value: 'spec', label: 'Photo', title: spec ? `The shape of ${spec.name}` : 'The photo shape' }, { value: '1:1', label: '1:1' },
              { value: 'free', label: 'Free' }, { value: 'custom', label: 'Custom' }]} />
          {custom && (
            <div className="row">
              <NumberField label="Width" value={cw} min={0.1} step={1} width={70} onChange={(v) => v && setRatio(`${v}:${ch}`)} />
              <NumberField label="Height" value={ch} min={0.1} step={1} width={70} onChange={(v) => v && setRatio(`${cw}:${v}`)} />
            </div>
          )}
          <p className="muted small">The crop is only the first stage: the next step sizes the photo exactly. A loose crop around the head and shoulders works best.</p>
        </section>
        <section className="panel-section">
          <header><h3>Straighten</h3><span className="muted small">{crop.angle.toFixed(1)}°</span></header>
          <input type="range" min={-45} max={45} step={0.1} value={crop.angle} aria-label="Straighten" data-testid="passport-straighten"
            onChange={(e) => setLive(fitInside({ ...crop, angle: Number(e.target.value) }, W, H))}
            onPointerUp={() => { if (live) commit(live, 'crop-angle') }}
            onKeyUp={() => { if (live) commit(live, 'crop-angle') }} />
          <div className="row">
            <NumberField label="Angle" value={Math.round(crop.angle * 10) / 10} min={-45} max={45} step={0.1} suffix="°" width={80}
              onChange={(v) => v !== null && commit({ ...crop, angle: v }, 'crop-angle')} testId="passport-angle" />
            <button className="btn small" title="Mirror left to right" onClick={() => commit({ ...crop, flipH: !crop.flipH })} data-testid="passport-flip-h"><Icon name="flip-h" size={14} /> Flip</button>
            <button className="btn small" title="Turn upside down" onClick={() => commit({ ...crop, flipV: !crop.flipV })}><Icon name="flip-v" size={14} /> Flip</button>
          </div>
          <p className="muted small">The crop shrinks as you turn, so no empty corners appear. <kbd>[</kbd> <kbd>]</kbd> turn by 0.1°; arrow keys move by 1 px.</p>
        </section>
        <section className="panel-section">
          <header><h3>Frame</h3></header>
          <div className="row">
            <button className="btn small" onClick={() => void st.frameFace()} data-testid="passport-frame-face"><Icon name="target" size={14} /> Frame the face</button>
            <button className="btn small" onClick={() => commit(r ? cropWithRatio(fullCrop(W, H), r, W, H) : fullCrop(W, H))}>Whole photo</button>
          </div>
          <p className="muted small">Drag the photo to move it, scroll to zoom, or drag the corners of the frame.</p>
        </section>
      </aside>
    </div>
  )
}
