import type Konva from 'konva'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Circle, Group, Image as KImage, Layer, Line, Rect, Shape, Stage, Text } from 'react-konva'
import {
  type Adjust, apply, cropMap, fullCrop, invert, NO_ADJUST, type PassportSpec, PER_INCH, type Place, placeMap, specPx
} from '@shared/passport'
import { Segmented, Select, Toggle } from '../../components/controls'
import { Icon } from '../../components/Icon'
import { useShortcuts } from '../../lib/shortcuts'
import { updateAppSettings, useUi } from '../../lib/ui-store'
import { useElementSize, useHtmlImage } from '../resizer/CropEditor'
import { SpecEditor } from './SpecEditor'
import { CUSTOM_ID, customSpecFrom, usePassport } from './store'

const STANDARD_BG = [
  { name: 'White', color: '#FFFFFF' }, { name: 'Off-white', color: '#F4F4F2' }, { name: 'Light grey', color: '#E3E3E3' }, { name: 'Light blue', color: '#D6E6F5' }
]

const SLIDERS: { key: keyof Adjust; label: string; min: number }[] = [
  { key: 'exposure', label: 'Exposure', min: -100 }, { key: 'brightness', label: 'Brightness', min: -100 },
  { key: 'contrast', label: 'Contrast', min: -100 }, { key: 'highlights', label: 'Highlights', min: -100 },
  { key: 'shadows', label: 'Shadows', min: -100 }, { key: 'saturation', label: 'Saturation', min: -100 },
  { key: 'vibrance', label: 'Vibrance', min: -100 }, { key: 'warmth', label: 'Warmth', min: -100 }, { key: 'tint', label: 'Tint', min: -100 },
  { key: 'sharpness', label: 'Sharpness', min: 0 }, { key: 'denoise', label: 'Noise reduction', min: 0 }
]

export function specSummary(s: PassportSpec): string {
  const u = s.unit === 'in' ? ' in' : ` ${s.unit}`
  return `${s.width} × ${s.height}${u} at ${s.dpi} DPI`
}

function fmt(v: number, unit: string): string {
  return unit === 'in' ? `${v.toFixed(2)} in` : `${v.toFixed(1)} ${unit}`
}

function Slider({ label, value, min, onChange }: { label: string; value: number; min: number; onChange: (v: number, done: boolean) => void }) {
  const [v, setV] = useState(value)
  useEffect(() => setV(value), [value])
  return (
    <label className="slider-row" onDoubleClick={() => onChange(0, true)} title="Double-click to reset">
      <span>{label}</span>
      <input type="range" min={min} max={100} step={1} value={v} aria-label={label}
        onChange={(e) => { setV(Number(e.target.value)); onChange(Number(e.target.value), false) }}
        onPointerUp={() => onChange(v, true)} />
      <output>{v > 0 ? `+${v}` : v}</output>
    </label>
  )
}

function SpecPanel() {
  const specs = usePassport((s) => s.specs)
  const doc = usePassport((s) => s.history.present)
  const st = usePassport.getState()
  const spec = st.spec()
  const [editing, setEditing] = useState(false)
  if (!spec) return null
  const px = specPx(spec)
  const src = spec.source
  return (
    <section className="panel-section">
      <header><h3>Photo rules</h3><button className="btn small ghost" onClick={() => setEditing(true)} data-testid="passport-edit-spec">Edit…</button></header>
      <Select value={doc.specId} testId="passport-spec"
        options={[...specs.map((s) => ({ value: s.id, label: s.name })), { value: CUSTOM_ID, label: 'Custom size…' }]}
        onChange={(id) => id === CUSTOM_ID ? st.update({ specId: CUSTOM_ID, customSpec: doc.customSpec ?? customSpecFrom(spec), place: null })
          : st.update({ specId: id, customSpec: null, place: null })} />
      <dl className="spec-facts" data-testid="passport-spec-facts">
        <dt>Size</dt><dd>{specSummary(spec)} = {px.w} × {px.h} px{Math.abs(px.errorMm[0]) + Math.abs(px.errorMm[1]) > 0.001 ? ` (prints ${px.errorMm[0] >= 0 ? '+' : ''}${px.errorMm[0].toFixed(2)} / ${px.errorMm[1] >= 0 ? '+' : ''}${px.errorMm[1].toFixed(2)} mm)` : ''}</dd>
        <dt>Head</dt><dd>{fmt(spec.head.min, spec.unit)}–{fmt(spec.head.max, spec.unit)}, chin to {spec.head.crown === 'hair' ? 'top of the hair' : 'top of the head (not the hair)'}</dd>
        {spec.eyeLine && <><dt>Eyes</dt><dd>{fmt(spec.eyeLine.min ?? 0, spec.unit)}–{fmt(spec.eyeLine.max ?? spec.height, spec.unit)} above the bottom</dd></>}
        {spec.topMargin && <><dt>Above head</dt><dd>{fmt(spec.topMargin.min ?? 0, spec.unit)}–{fmt(spec.topMargin.max ?? spec.height, spec.unit)}</dd></>}
        {spec.bottomMargin?.min !== undefined && <><dt>Below chin</dt><dd>at least {fmt(spec.bottomMargin.min, spec.unit)}</dd></>}
      </dl>
      <div className={`spec-source ${src.status}`} data-testid="passport-spec-source">
        {src.status === 'official-excerpt' && <>Rules from <strong>{src.authority}</strong>, checked {src.checked} through a search of the official page (the page itself could not be opened when the app was built). Check the current rules before you apply.</>}
        {src.status === 'official' && <>Rules from <strong>{src.authority}</strong>, checked {src.checked}.</>}
        {src.status === 'unverified' && <><strong>Unverified.</strong> No issuing authority&apos;s rule was found for this size; set the rules of the office you apply to.</>}
        {src.status === 'user' && <>Your own rules.</>}
        {src.url && <div className="muted small source-url">{src.url}</div>}
        {src.quote && <details><summary>What the source says</summary><p className="small">{src.quote}</p></details>}
      </div>
      {spec.notes && <p className="muted small">{spec.notes}</p>}
      {editing && <SpecEditor spec={spec} onClose={() => setEditing(false)} />}
    </section>
  )
}

function Hints() {
  const render = usePassport((s) => s.render)
  const rendering = usePassport((s) => s.rendering)
  if (!render) return <section className="panel-section"><header><h3>Checks</h3></header><p className="muted small">{rendering ? 'Checking…' : 'No checks yet.'}</p></section>
  const bad = render.hints.filter((h) => h.level === 'bad').length
  const warn = render.hints.filter((h) => h.level === 'warn').length
  return (
    <section className="panel-section">
      <header><h3>Checks</h3><span className={`muted small ${bad ? 'bad-text' : warn ? 'warn-text' : 'ok-text'}`}>{bad ? `${bad} to fix` : warn ? `${warn} to look at` : 'All fine'}</span></header>
      <ul className="hints" data-testid="passport-hints">
        {render.hints.map((h) => (
          <li key={h.id} className={`hint ${h.level}`} data-testid={`hint-${h.id}`} data-level={h.level} title={h.detail}>
            <span className="dot" aria-hidden />
            <span><strong>{h.label}</strong>{h.detail && <span className="muted small"> — {h.detail}</span>}</span>
          </li>
        ))}
      </ul>
      <p className="muted small">These are hints from measuring the photo. An office decides whether it accepts a photo.</p>
    </section>
  )
}

function BackgroundPanel() {
  const doc = usePassport((s) => s.history.present)
  const analysis = usePassport((s) => s.analysis)
  const tool = usePassport((s) => s.tool)
  const brush = usePassport((s) => s.brush)
  const st = usePassport.getState()
  const spec = st.spec()
  const bg = doc.background
  const swatches = [...(spec?.backgrounds ?? []), ...STANDARD_BG.filter((b) => !spec?.backgrounds.some((x) => x.color.toUpperCase() === b.color))]
  return (
    <div className="tab-body">
      <Segmented value={bg.mode} testId="passport-bg-mode" onChange={(mode) => st.update({ background: { ...bg, mode } })}
        options={[{ value: 'replace', label: 'Replace' }, { value: 'keep', label: 'Keep original' }]} />
      {analysis && !analysis.person && <p className="warn-text small">No person was found to cut out, so the background cannot be replaced.</p>}
      {bg.mode === 'replace' && (
        <>
          <div className="swatches" role="radiogroup" aria-label="Background colour">
            {swatches.map((b) => (
              <button key={b.color + b.name} role="radio" aria-checked={bg.color.toUpperCase() === b.color.toUpperCase()} title={`${b.name} ${b.color}`}
                className={`swatch ${bg.color.toUpperCase() === b.color.toUpperCase() ? 'on' : ''}`} style={{ background: b.color }}
                data-testid={`passport-bg-${b.color.slice(1).toLowerCase()}`}
                onClick={() => st.update({ background: { ...bg, color: b.color.toUpperCase() } })} />
            ))}
            <label className="swatch custom" title="Another colour">
              <input type="color" value={bg.color} aria-label="Custom colour" onChange={(e) => st.update({ background: { ...bg, color: e.target.value.toUpperCase() } }, 'bg-color')} />
            </label>
          </div>
          <label className="slider-row"><span>Edge softness</span>
            <input type="range" min={0} max={5} step={0.25} value={bg.feather} aria-label="Edge softness"
              onChange={(e) => st.update({ background: { ...bg, feather: Number(e.target.value) } }, 'bg-feather')} />
            <output>{bg.feather}</output></label>
          <div className="row tools">
            <Segmented value={tool} onChange={(t) => usePassport.setState({ tool: t })} testId="passport-tool"
              options={[{ value: 'move', label: 'Move' }, { value: 'restore', label: <><Icon name="brush" size={14} /> Restore</> }, { value: 'erase', label: <><Icon name="eraser" size={14} /> Erase</> }]} />
          </div>
          {tool !== 'move' && (
            <>
              <label className="slider-row"><span>Brush</span><input type="range" min={4} max={120} value={brush.size} aria-label="Brush size"
                onChange={(e) => usePassport.setState({ brush: { ...brush, size: Number(e.target.value) } })} /><output>{brush.size}</output></label>
              <label className="slider-row"><span>Hardness</span><input type="range" min={0} max={1} step={0.05} value={brush.hardness} aria-label="Brush hardness"
                onChange={(e) => usePassport.setState({ brush: { ...brush, hardness: Number(e.target.value) } })} /><output>{Math.round(brush.hardness * 100)}%</output></label>
              <p className="muted small">Restore brings back parts of the person the cut-out missed (hair, ears, shoulders); erase removes background left behind.</p>
            </>
          )}
          {doc.strokes.length > 0 && <button className="btn small" onClick={() => st.update({ strokes: [] })}>Clear {doc.strokes.length} brush stroke{doc.strokes.length === 1 ? '' : 's'}</button>}
        </>
      )}
    </div>
  )
}

function AdjustPanel() {
  const doc = usePassport((s) => s.history.present)
  const compare = usePassport((s) => s.compare)
  const st = usePassport.getState()
  const a = doc.adjust
  const set = (patch: Partial<Adjust>, done: boolean, key: string) => st.update({ adjust: { ...a, ...patch } }, done ? null : key)
  const changed = (Object.keys(NO_ADJUST) as (keyof Adjust)[]).filter((k) => a[k] !== NO_ADJUST[k]).length + (doc.upscale ? 1 : 0)
  return (
    <div className="tab-body">
      <div className="row">
        <button className="btn small" onClick={() => void st.autoAdjust('enhance')} data-testid="passport-auto-enhance"><Icon name="wand" size={14} /> Auto enhance</button>
        <button className="btn small" onClick={() => void st.autoAdjust('whiteBalance')} data-testid="passport-auto-wb">Auto white balance</button>
      </div>
      {SLIDERS.map((s) => <Slider key={s.key} label={s.label} min={s.min} value={a[s.key] as number} onChange={(v, done) => set({ [s.key]: v }, done, `adj-${s.key}`)} />)}
      <Toggle label="Fix red eyes" checked={a.redEye} onChange={(v) => set({ redEye: v }, true, '')} testId="passport-redeye" />
      <Slider label="Skin smoothing" min={0} value={a.skinSmoothing} onChange={(v, done) => set({ skinSmoothing: v }, done, 'adj-skin')} />
      {a.skinSmoothing > 0 && <p className="warn-text small">Many authorities refuse retouched photos. Keep skin smoothing off unless you are sure it is allowed.</p>}
      <Toggle label="AI upscaling for small photos" checked={doc.upscale} onChange={(v) => st.update({ upscale: v })} testId="passport-upscale"
        hint="Real-ESRGAN, offline. It invents detail; many authorities refuse altered photos." />
      {doc.upscale && <p className="warn-text small">Upscaling invents detail. Many authorities refuse altered photos; use a sharper original if you can.</p>}
      <div className="row">
        <Toggle label="Before / after" checked={compare !== null} onChange={(v) => { usePassport.setState({ compare: v ? 0.5 : null }); st.scheduleRender(0) }} testId="passport-compare" />
        <span className="spacer" />
        {changed > 0 && <span className="muted small" data-testid="passport-adjust-changed">{changed} changed</span>}
        <button className="btn small ghost" disabled={changed === 0} onClick={() => st.update({ adjust: { ...NO_ADJUST }, upscale: false })}
          data-testid="passport-adjust-reset">Reset</button>
      </div>
    </div>
  )
}

function SizeCanvas() {
  const photo = usePassport((s) => s.photo)!
  const doc = usePassport((s) => s.history.present)
  const analysis = usePassport((s) => s.analysis)
  const render = usePassport((s) => s.render)
  const renderFor = usePassport((s) => s.renderFor)
  const rendering = usePassport((s) => s.rendering)
  const tool = usePassport((s) => s.tool)
  const brush = usePassport((s) => s.brush)
  const compare = usePassport((s) => s.compare)
  const guides = useUi((s) => s.settings?.passport.guides ?? true)
  const st = usePassport.getState()
  const spec = st.spec()
  const [boxRef, box] = useElementSize<HTMLDivElement>()
  const cropped = useHtmlImage(analysis?.image.url)
  const out = useHtmlImage(render?.image.url)
  const before = useHtmlImage(render?.before?.url)
  const [live, setLive] = useState<Place | null>(null)
  const [stroke, setStroke] = useState<[number, number][] | null>(null)
  const [cursor, setCursor] = useState<[number, number] | null>(null)
  const [marker, setMarker] = useState<{ which: 'crown' | 'chin'; y: number } | null>(null)
  const stageRef = useRef<Konva.Stage>(null)
  useShortcutsSafe((dx, dy) => {
    const ps = usePassport.getState()
    const pl = ps.doc().place
    const sp = ps.spec()
    if (!pl || !sp) return
    const { w, h } = specPx(sp)
    ps.update({ place: { ...pl, x: pl.x + dx / w, y: pl.y + dy / h } }, 'place-nudge')
  })
  if (!spec || !analysis) return <div ref={boxRef} className="size-stage" />
  const { w: W, h: H } = specPx(spec)
  const crop = doc.crop ?? fullCrop(photo.width, photo.height)
  const [cw, ch] = analysis.cropSize
  const place = live ?? doc.place
  const dz = box.w ? Math.min((box.w - 120) / W, (box.h - 70) / H) : 1
  const ox = (box.w - W * dz) / 2, oy = (box.h - H * dz) / 2
  const toDisp = (x: number, y: number): [number, number] => [ox + x * dz, oy + y * dz]
  const fromDisp = (x: number, y: number): [number, number] => [(x - ox) / dz, (y - oy) / dz]
  const fresh = render !== null && renderFor === doc && live === null && stroke === null
  // While colours or the background are being redrawn, the last render stays (only the placement shows live).
  const shown = render !== null && renderFor !== null && live === null && stroke === null && renderFor.crop === doc.crop &&
    renderFor.place === doc.place && renderFor.specId === doc.specId && renderFor.customSpec === doc.customSpec
  // Output <-> cropped maps for the current placement.
  const o2c = place ? placeMap(place, cw, ch, W, H) : null
  const c2o = o2c ? invert(o2c) : null
  const face = analysis.face
  const crownC = doc.overrides.crown ?? face?.crown
  const chinC = doc.overrides.chin ?? face?.chin
  const P = (p: [number, number] | undefined | null) => (p && c2o ? apply(c2o, p[0], p[1]) : null)
  const crownO = P(crownC), chinO = P(chinC)
  const eyeO = face && c2o ? (() => { const a = apply(c2o, ...face.eyes[0]), b = apply(c2o, ...face.eyes[1]); return [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2] })() : null
  const ppu = spec.dpi / PER_INCH[spec.unit]
  const s = place ? place.scale * H : 1
  const toSource = (dx: number, dy: number): [number, number] => {
    const [x, y] = fromDisp(dx, dy)
    const c = apply(o2c!, x, y)
    return apply(cropMap(crop), c[0], c[1])
  }

  return (
    <div ref={boxRef} className={`size-stage tool-${tool}`} data-testid="passport-size-stage" data-dz={dz} data-ox={ox} data-oy={oy}
      data-place={JSON.stringify(place)} data-fresh={fresh ? '1' : '0'}
      onWheel={(e) => {
        if (!place || tool !== 'move') return
        const r = (e.currentTarget as HTMLDivElement).getBoundingClientRect()
        const [mx, my] = fromDisp(e.clientX - r.left, e.clientY - r.top)
        const k = Math.exp(-e.deltaY * 0.0012)
        const next = { ...place, scale: place.scale * k, x: (mx + (place.x * W - mx) * k) / W, y: (my + (place.y * H - my) * k) / H }
        st.update({ place: next }, 'place-zoom')
      }}>
      {box.w > 0 && (
        <Stage ref={stageRef} width={box.w} height={box.h}
          onPointerDown={(e) => {
            if (tool === 'move' || !o2c) return
            const p = e.target.getStage()!.getPointerPosition()!
            setStroke([[p.x, p.y]])
          }}
          onPointerMove={(e) => {
            const p = e.target.getStage()!.getPointerPosition()
            if (!p) return
            if (tool !== 'move') setCursor([p.x, p.y])
            if (stroke) setStroke([...stroke, [p.x, p.y]])
          }}
          onPointerLeave={() => setCursor(null)}
          onPointerUp={() => {
            if (!stroke || !o2c) return
            const radius = (brush.size / 2) / dz / s
            st.addStroke({ mode: tool === 'erase' ? 'erase' : 'restore', radius, hardness: brush.hardness, points: stroke.map(([x, y]) => toSource(x, y)) })
            setStroke(null)
          }}>
          <Layer>
            {cropped && place && (
              <Group x={ox + place.x * W * dz} y={oy + place.y * H * dz} offsetX={cw / 2} offsetY={ch / 2} scaleX={s * dz} scaleY={s * dz}
                rotation={place.angle} draggable={tool === 'move'}
                onDragMove={(e) => {
                  const g = e.target
                  setLive({ ...place, x: (g.x() - ox) / (W * dz), y: (g.y() - oy) / (H * dz) })
                }}
                onDragEnd={(e) => {
                  const g = e.target
                  const next = { ...doc.place!, x: (g.x() - ox) / (W * dz), y: (g.y() - oy) / (H * dz) }
                  setLive(null)
                  st.update({ place: next })
                }}>
                <KImage image={cropped} width={cw} height={ch} />
              </Group>
            )}
            {shown && out && <KImage image={out} x={ox} y={oy} width={W * dz} height={H * dz} listening={false} />}
            {shown && before && compare !== null && (
              <Group clipX={ox} clipY={oy} clipWidth={W * dz * compare} clipHeight={H * dz} listening={false}>
                <KImage image={before} x={ox} y={oy} width={W * dz} height={H * dz} />
              </Group>
            )}
            <Shape listening={false} sceneFunc={(ctx) => {
              const c = ctx._context
              c.save()
              c.beginPath()
              c.rect(0, 0, box.w, box.h)
              c.rect(ox, oy, W * dz, H * dz)
              c.fillStyle = 'rgba(20,22,26,0.72)'
              c.fill('evenodd')
              c.restore()
            }} />
            <Rect x={ox} y={oy} width={W * dz} height={H * dz} stroke="#4f8cff" strokeWidth={1.5} listening={false} />
            {compare !== null && shown && (
              <Line points={[ox + W * dz * compare, oy, ox + W * dz * compare, oy + H * dz]} stroke="#fff" strokeWidth={2} hitStrokeWidth={14} draggable
                dragBoundFunc={(p) => ({ x: Math.min(Math.max(p.x, -W * dz * compare), W * dz * (1 - compare)), y: 0 })}
                onDragEnd={(e) => { usePassport.setState({ compare: Math.min(1, Math.max(0, compare + e.target.x() / (W * dz))) }); e.target.x(0) }} />
            )}
            {guides && <Guides spec={spec} W={W} H={H} ppu={ppu} toDisp={toDisp} crownO={crownO} chinO={chinO} eyeO={eyeO as [number, number] | null} />}
            {guides && crownO && chinO && (['crown', 'chin'] as const).map((which) => {
              const pt = which === 'crown' ? crownO : chinO
              const [dx, dy] = toDisp(pt[0], marker?.which === which ? marker.y : pt[1])
              return (
                <Group key={which}>
                  <Circle x={dx} y={dy} radius={7} fill={which === 'crown' ? '#ff9f1c' : '#2ec4b6'} stroke="#fff" strokeWidth={1.5} draggable
                    data-testid={`marker-${which}`}
                    dragBoundFunc={(p) => ({ x: dx, y: p.y })}
                    onDragMove={(e) => setMarker({ which, y: fromDisp(0, e.target.y())[1] })}
                    onDragEnd={(e) => {
                      const y = fromDisp(0, e.target.y())[1]
                      const c = apply(o2c!, pt[0], y)
                      setMarker(null)
                      st.update({ overrides: { ...doc.overrides, [which]: [c[0], c[1]] } })
                    }} />
                  <Text x={dx + 10} y={dy - 7} text={which === 'crown' ? (spec.head.crown === 'hair' ? 'top of hair' : 'top of head') : 'chin'} fontSize={11} fill="#fff" listening={false} />
                </Group>
              )
            })}
            {stroke && <Line points={stroke.flat()} stroke={tool === 'erase' ? 'rgba(255,80,80,0.6)' : 'rgba(80,220,120,0.6)'} strokeWidth={brush.size}
              lineCap="round" lineJoin="round" listening={false} />}
            {cursor && tool !== 'move' && <Circle x={cursor[0]} y={cursor[1]} radius={brush.size / 2} stroke="#fff" strokeWidth={1} dash={[3, 3]} listening={false} />}
          </Layer>
        </Stage>
      )}
      {rendering && <span className="size-rendering"><span className="spinner small" /> Updating…</span>}
    </div>
  )
}

/** Arrow keys nudge the photo by one output pixel (Shift: 10). */
function useShortcutsSafe(nudge: (dx: number, dy: number) => void) {
  const ref = useRef(nudge)
  ref.current = nudge
  useShortcuts([
    { keys: 'arrowleft', run: () => ref.current(-1, 0) }, { keys: 'arrowright', run: () => ref.current(1, 0) },
    { keys: 'arrowup', run: () => ref.current(0, -1) }, { keys: 'arrowdown', run: () => ref.current(0, 1) },
    { keys: 'shift+arrowleft', run: () => ref.current(-10, 0) }, { keys: 'shift+arrowright', run: () => ref.current(10, 0) },
    { keys: 'shift+arrowup', run: () => ref.current(0, -10) }, { keys: 'shift+arrowdown', run: () => ref.current(0, 10) }
  ])
}

function Guides({ spec, W, H, ppu, toDisp, crownO, chinO, eyeO }: {
  spec: PassportSpec; W: number; H: number; ppu: number; toDisp: (x: number, y: number) => [number, number]
  crownO: [number, number] | null; chinO: [number, number] | null; eyeO: [number, number] | null
}) {
  const [x0, y0] = toDisp(0, 0)
  const [x1, y1] = toDisp(W, H)
  const hline = (y: number, color: string, dash?: number[]) => { const [, dy] = toDisp(0, y); return <Line points={[x0, dy, x1, dy]} stroke={color} strokeWidth={1} dash={dash} listening={false} /> }
  const band = (ya: number, yb: number, color: string) => {
    const [, a] = toDisp(0, Math.min(ya, yb)), [, b] = toDisp(0, Math.max(ya, yb))
    return <Rect x={x0} y={a} width={x1 - x0} height={b - a} fill={color} listening={false} />
  }
  const [cx] = toDisp(W / 2, 0)
  return (
    <Group listening={false}>
      <Line points={[cx, y0, cx, y1]} stroke="rgba(255,255,255,0.55)" strokeWidth={1} dash={[4, 4]} />
      {chinO && band(chinO[1] - spec.head.max * ppu, chinO[1] - spec.head.min * ppu, 'rgba(46,196,182,0.18)')}
      {spec.eyeLine && band(H - (spec.eyeLine.min ?? 0) * ppu, H - (spec.eyeLine.max ?? spec.height) * ppu, 'rgba(255,214,10,0.16)')}
      {spec.topMargin && band((spec.topMargin.min ?? 0) * ppu, (spec.topMargin.max ?? 0) * ppu, 'rgba(255,159,28,0.16)')}
      {spec.bottomMargin?.min !== undefined && hline(H - spec.bottomMargin.min * ppu, 'rgba(255,255,255,0.6)', [2, 4])}
      {crownO && hline(crownO[1], '#ff9f1c')}
      {chinO && hline(chinO[1], '#2ec4b6')}
      {eyeO && hline(eyeO[1], '#ffd60a', [6, 3])}
    </Group>
  )
}

export function StepSize() {
  const [tab, setTab] = useState<'background' | 'adjust'>('background')
  const doc = usePassport((s) => s.history.present)
  const guides = useUi((s) => s.settings?.passport.guides ?? true)
  const st = usePassport.getState()
  const place = doc.place
  const measures = usePassport((s) => s.render?.measures)
  const scalePct = useMemo(() => (measures ? Math.round(100 / Number(measures.sourcePixelsPerOutput ?? 1)) : null), [measures])
  return (
    <div className="passport-size">
      <div className="size-main">
        <div className="size-toolbar">
          <button className="btn small primary" onClick={() => void st.autofit()} data-testid="passport-autofit"><Icon name="target" size={14} /> Auto fit</button>
          <label className="field inline"><span className="field-label">Turn</span>
            <input type="number" step={0.1} min={-45} max={45} value={place ? Math.round(place.angle * 10) / 10 : 0} aria-label="Turn the photo" data-testid="passport-turn"
              onChange={(e) => place && st.update({ place: { ...place, angle: Number(e.target.value) } }, 'place-angle')} />°</label>
          {scalePct !== null && <span className="muted small" title="Output pixels per photo pixel">{scalePct}% of the photo&apos;s pixels</span>}
          <span className="spacer" />
          <Toggle label="Guides" checked={guides} onChange={(v) => void updateAppSettings({ passport: { guides: v } })} />
        </div>
        <SizeCanvas />
        <p className="muted small size-help">Drag the photo to move it, scroll to zoom, arrow keys move by 1 pixel. Drag the orange and green markers if the top of the head or the chin is measured wrongly.</p>
      </div>
      <aside className="passport-side wide">
        <SpecPanel />
        <Hints />
        <div className="tabs" role="tablist">
          <button role="tab" aria-selected={tab === 'background'} className={tab === 'background' ? 'on' : ''} onClick={() => setTab('background')} data-testid="passport-tab-background">Background</button>
          <button role="tab" aria-selected={tab === 'adjust'} className={tab === 'adjust' ? 'on' : ''} onClick={() => setTab('adjust')} data-testid="passport-tab-adjust">Adjust</button>
        </div>
        {tab === 'background' ? <BackgroundPanel /> : <AdjustPanel />}
      </aside>
    </div>
  )
}
