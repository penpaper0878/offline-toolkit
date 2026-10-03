import type Konva from 'konva'
import { type ReactElement, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { Ellipse, Group, Image as KImage, Layer as KLayer, Line, Path, Rect, Shape, Stage, Transformer } from 'react-konva'
import { create } from 'zustand'
import {
  type Box, bounds, cellEdges, cellText, cssFont, type DesignScene, type ImageLayer, type Layer, type ShapeLayer, shapeOutline,
  snapBox, type TableLayer, tableCells, type TextGeometry, type TextLayer, textGeometry, textHeight, type VectorLayer,
  vectorScale
} from '@shared/design'
import { measure, metricsFor, onFontsLoaded } from './fonts'
import { useDesign } from './store'

/** View state shared with the toolbar: zoom and pan (screen = page * zoom + pan). */
interface ViewState {
  zoom: number
  x: number
  y: number
  fitToken: number
  set(v: Partial<Omit<ViewState, 'set' | 'fit' | 'zoomBy'>>): void
  fit(): void
  zoomBy(f: number): void
}

export const useView = create<ViewState>((set, get) => ({
  zoom: 1,
  x: 0,
  y: 0,
  fitToken: 0,
  set: (v) => set(v),
  fit: () => set({ fitToken: get().fitToken + 1 }),
  zoomBy: (f) => set({ zoom: Math.max(0.05, Math.min(16, get().zoom * f)) })
}))

function useImageEl(url: string | null): HTMLImageElement | null {
  const [img, setImg] = useState<HTMLImageElement | null>(null)
  useEffect(() => {
    if (!url) {
      setImg(null)
      return
    }
    let alive = true
    const el = new window.Image()
    el.onload = () => alive && setImg(el)
    el.src = url
    return () => {
      alive = false
    }
  }, [url])
  return img
}

function useAsset(rel: string | undefined): HTMLImageElement | null {
  const url = useDesign((s) => (rel ? s.assetUrls[rel] : undefined))
  const assetUrl = useDesign((s) => s.assetUrl)
  useEffect(() => {
    if (rel && !url) void assetUrl(rel).catch(() => undefined)
  }, [rel, url, assetUrl])
  return useImageEl(url ?? null)
}

/** Text lines drawn at their baselines, as the exporters place them. */
function drawLines(c: CanvasRenderingContext2D, g: TextGeometry, font: string, color: string, ox: number, oy: number,
  underline: boolean, size: number): void {
  c.font = font
  c.fillStyle = color
  c.textBaseline = 'alphabetic'
  c.direction = g.rtl ? 'rtl' : 'ltr'
  const align = g.align === 'center' ? 'center' : g.align === 'right' ? 'right' : 'left'
  c.textAlign = g.rtl ? (align === 'left' ? 'right' : align === 'right' ? 'left' : 'center') : align
  g.lines.forEach((t, i) => {
    c.fillText(t, g.anchor - ox, g.baselines[i] - oy)
    if (underline && t) {
      const w = c.measureText(t).width
      const x0 = c.textAlign === 'center' ? g.anchor - ox - w / 2 : c.textAlign === 'right' ? g.anchor - ox - w : g.anchor - ox
      c.fillRect(x0, g.baselines[i] - oy + size * 0.1, w, Math.max(1, size * 0.06))
    }
  })
}

function ImageContent({ layer }: { layer: ImageLayer }) {
  const img = useAsset(layer.asset)
  return <KImage image={img ?? undefined} width={layer.box[2]} height={layer.box[3]} />
}

function ShapeContent({ layer }: { layer: ShapeLayer }) {
  const [x, y] = layer.box
  if (layer.shape === 'line') {
    const p = layer.points ?? [0, layer.box[3] / 2, layer.box[2], layer.box[3] / 2]
    return <Line points={[...p]} stroke={layer.stroke ?? '#000'} strokeWidth={layer.strokeWidth || 1} hitStrokeWidth={Math.max(12, layer.strokeWidth)} />
  }
  const [ox, oy, ow, oh, r] = shapeOutline(layer)
  const common = { fill: layer.fill ?? undefined, stroke: layer.stroke ?? undefined, strokeWidth: layer.stroke ? layer.strokeWidth : 0 }
  if (layer.shape === 'ellipse') return <Ellipse x={ox - x + ow / 2} y={oy - y + oh / 2} radiusX={ow / 2} radiusY={oh / 2} {...common} />
  return <Rect x={ox - x} y={oy - y} width={ow} height={oh} cornerRadius={layer.shape === 'rounded' ? r : 0} {...common}
    hitFunc={(ctx, shape) => { ctx.beginPath(); ctx.rect(0, 0, ow, oh); ctx.closePath(); ctx.fillStrokeShape(shape) }} />
}

function VectorContent({ layer }: { layer: VectorLayer }) {
  const [sx, sy] = vectorScale(layer)
  return (
    <Group scaleX={sx} scaleY={sy}>
      <Rect width={layer.box[2] / sx} height={layer.box[3] / sy} fill="transparent" />
      {layer.paths.map((p, i) => <Path key={i} data={p.d} fill={p.fill} />)}
    </Group>
  )
}

function TextContent({ layer, hidden }: { layer: TextLayer; hidden: boolean }) {
  const st = layer.style
  const [x, y, w, h] = layer.box
  return (
    <Shape width={w} height={h} visible={!hidden}
      sceneFunc={(ctx) => {
        const m = metricsFor(st.family, st.weight, st.italic)
        const g = textGeometry(layer, m)
        drawLines(ctx._context, g, cssFont(st.family, st.weight, st.italic, st.size), st.color, x, y, st.underline, st.size)
      }}
      hitFunc={(ctx, shape) => { ctx.beginPath(); ctx.rect(0, 0, w, h); ctx.closePath(); ctx.fillStrokeShape(shape) }} />
  )
}

function TableContent({ layer }: { layer: TableLayer }) {
  const [x, y, w, h] = layer.box
  const cells = tableCells(layer)
  return (
    <>
      {cells.filter(({ cell }) => cell.fill).map(({ cell, box: [x0, y0, x1, y1] }) => (
        <Rect key={`f${cell.row}-${cell.col}`} x={x0 - x} y={y0 - y} width={x1 - x0} height={y1 - y0} fill={cell.fill!} />
      ))}
      {cellEdges(layer).map(([x0, y0, x1, y1], i) => (
        <Line key={`e${i}`} points={[x0 - x, y0 - y, x1 - x, y1 - y]} stroke={layer.border.color} strokeWidth={layer.border.width} lineCap="square" />
      ))}
      <Shape width={w} height={h}
        sceneFunc={(ctx) => {
          for (const { cell, box } of cells) {
            if (!cell.text) continue
            const m = metricsFor(layer.style.family, cell.weight, cell.italic)
            const g = cellText(layer, cell, box, m)
            drawLines(ctx._context, g, cssFont(layer.style.family, cell.weight, cell.italic, layer.style.size), cell.color ?? layer.style.color, x, y, false, layer.style.size)
          }
        }}
        hitFunc={(ctx, shape) => { ctx.beginPath(); ctx.rect(0, 0, w, h); ctx.closePath(); ctx.fillStrokeShape(shape) }} />
    </>
  )
}

interface NodeProps {
  layer: Layer
  selected: boolean
  editing: boolean
  onSelect(e: Konva.KonvaEventObject<MouseEvent>, id: string): void
  onDragMove(e: Konva.KonvaEventObject<DragEvent>): void
  onDragEnd(): void
  onTransformEnd(e: Konva.KonvaEventObject<Event>, layer: Layer): void
  onDblClick(layer: Layer): void
}

function LayerNode({ layer, selected, editing, onSelect, onDragMove, onDragEnd, onTransformEnd, onDblClick }: NodeProps) {
  const [x, y, w, h] = layer.box
  const isBackground = layer.type === 'image' && layer.role === 'background'
  return (
    <Group id={layer.id} name="layer" x={x + w / 2} y={y + h / 2} offsetX={w / 2} offsetY={h / 2} rotation={layer.rotation}
      opacity={layer.opacity} visible={layer.visible} listening={!layer.locked && !isBackground}
      draggable={selected && !layer.locked}
      onMouseDown={(e) => onSelect(e, layer.id)} onTap={(e) => onSelect(e as unknown as Konva.KonvaEventObject<MouseEvent>, layer.id)}
      onDragMove={onDragMove} onDragEnd={onDragEnd} onTransformEnd={(e) => onTransformEnd(e, layer)}
      onDblClick={() => onDblClick(layer)}>
      {layer.type === 'image' && <ImageContent layer={layer} />}
      {layer.type === 'shape' && <ShapeContent layer={layer} />}
      {layer.type === 'vector' && <VectorContent layer={layer} />}
      {layer.type === 'text' && <TextContent layer={layer} hidden={editing} />}
      {layer.type === 'table' && <TableContent layer={layer} />}
    </Group>
  )
}

function lowConfidenceBoxes(scene: DesignScene): { key: string; box: Box }[] {
  const out: { key: string; box: Box }[] = []
  for (const l of scene.layers) {
    if (l.type !== 'text' || !l.visible || !l.words?.length || !l.lowConfidence?.length) continue
    const ref = l.analysisBox ?? l.box
    const dx = l.box[0] - ref[0]
    const dy = l.box[1] - ref[1]
    for (const i of l.lowConfidence) {
      const wd = l.words[i]
      if (!wd) continue
      const [x0, y0, x1, y1] = wd.box
      out.push({ key: `${l.id}-${i}`, box: [x0 + dx - 2, y0 + dy - 2, x1 - x0 + 4, y1 - y0 + 4] })
    }
  }
  return out
}

/** The textarea that edits a text layer in place, lined up with the canvas text. */
function TextEditor({ layer }: { layer: TextLayer }) {
  const { zoom, x: px, y: py } = useView()
  const ref = useRef<HTMLTextAreaElement>(null)
  const st = layer.style
  const m = metricsFor(st.family, st.weight, st.italic)
  const pitch = st.lineHeight * st.size
  const [bx, by, bw] = layer.box
  const firstBaseline = by + m.ascent * st.size
  // CSS puts a line's baseline half the leading plus the ascent below the line top.
  const top = firstBaseline - (pitch - (m.ascent + m.descent) * st.size) / 2 - m.ascent * st.size
  const [value, setValue] = useState(layer.text)
  useEffect(() => {
    ref.current?.focus()
    ref.current?.select()
  }, [])
  const commit = () => {
    const s = useDesign.getState()
    if (value !== layer.text) {
      s.patchLayer<TextLayer>(layer.id, { text: value })
      s.fitTextBox(layer.id)
    }
    s.setEditingText(null)
  }
  const lines = value.split('\n').length
  return (
    <textarea ref={ref} className="design-text-editor" data-testid="design-text-editor" value={value} spellCheck={false}
      dir={layer.script === 'arabic' || layer.script === 'hebrew' ? 'rtl' : 'ltr'}
      style={{
        left: bx * zoom + px, top: top * zoom + py, width: Math.max(bw, 20) * zoom + 4, height: Math.max(lines, 1) * pitch * zoom + 4,
        font: cssFont(st.family, st.weight, st.italic, st.size * zoom), lineHeight: `${pitch * zoom}px`, color: st.color,
        textAlign: st.align === 'justify' ? 'left' : st.align, textDecoration: st.underline ? 'underline' : 'none',
        transform: layer.rotation ? `rotate(${layer.rotation}deg)` : undefined, transformOrigin: 'center center'
      }}
      onChange={(e) => setValue(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === 'Escape') {
          e.preventDefault()
          useDesign.getState().setEditingText(null)
        } else if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
          e.preventDefault()
          commit()
        }
        e.stopPropagation()
      }} />
  )
}

export function CanvasView(): ReactElement {
  const scene = useDesign((s) => s.history?.present ?? null)
  const selection = useDesign((s) => s.selection)
  const editingText = useDesign((s) => s.editingText)
  const overlay = useDesign((s) => s.overlay)
  const split = useDesign((s) => s.split)
  const highlight = useDesign((s) => s.settings.highlightLowConfidence)
  const accuracy = useDesign((s) => (s.accuracyFor === s.history?.present ? s.accuracy : null))
  const { zoom, x: panX, y: panY, fitToken } = useView()
  const wrapRef = useRef<HTMLDivElement>(null)
  const stageRef = useRef<Konva.Stage>(null)
  const trRef = useRef<Konva.Transformer>(null)
  const [size, setSize] = useState({ w: 800, h: 600 })
  const [guides, setGuides] = useState<{ x: number[]; y: number[] }>({ x: [], y: [] })
  const [, setFontTick] = useState(0)
  const [space, setSpace] = useState(false)
  const gesture = useRef(0)
  const original = useAsset(scene?.assets?.prepared)

  useEffect(() => onFontsLoaded(() => {
    setFontTick((t) => t + 1)
    stageRef.current?.batchDraw()
  }), [])

  useLayoutEffect(() => {
    const el = wrapRef.current
    if (!el) return
    const ro = new ResizeObserver(() => setSize({ w: el.clientWidth, h: el.clientHeight }))
    ro.observe(el)
    setSize({ w: el.clientWidth, h: el.clientHeight })
    return () => ro.disconnect()
  }, [])

  const pageW = scene?.page.width ?? 1
  const pageH = scene?.page.height ?? 1
  useEffect(() => {
    if (!size.w || !size.h) return
    const z = Math.min((size.w - 48) / pageW, (size.h - 48) / pageH, 4)
    useView.getState().set({ zoom: z, x: (size.w - pageW * z) / 2, y: (size.h - pageH * z) / 2 })
  }, [fitToken, pageW, pageH, size.w > 0 && size.h > 0, scene?.source.sha256]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.code === 'Space' && !(e.target as HTMLElement)?.closest('input, textarea, select, [contenteditable]')) {
        e.preventDefault()
        setSpace(true)
      }
    }
    const up = (e: KeyboardEvent) => e.code === 'Space' && setSpace(false)
    window.addEventListener('keydown', down)
    window.addEventListener('keyup', up)
    return () => {
      window.removeEventListener('keydown', down)
      window.removeEventListener('keyup', up)
    }
  }, [])

  // Attach the transform handles to the selected layers.
  useEffect(() => {
    const stage = stageRef.current
    const tr = trRef.current
    if (!stage || !tr) return
    const nodes = selection.map((id) => stage.findOne(`#${id}`)).filter((n): n is Konva.Node => !!n && n.listening())
    tr.nodes(editingText ? [] : nodes)
    tr.getLayer()?.batchDraw()
  }, [selection, scene, editingText])

  const selectedLayers = useMemo(() => scene?.layers.filter((l) => selection.includes(l.id)) ?? [], [scene, selection])
  const keepRatio = selectedLayers.length > 0 && selectedLayers.every((l) => l.type === 'image' || l.type === 'vector')

  const onSelect = useCallback((e: Konva.KonvaEventObject<MouseEvent>, id: string) => {
    if (space) return
    e.cancelBubble = true
    const s = useDesign.getState()
    if (e.evt.shiftKey) s.select(s.selection.includes(id) ? s.selection.filter((x) => x !== id) : [...s.selection, id])
    else if (!s.selection.includes(id)) s.select([id])
  }, [space])

  const onDragMove = useCallback((e: Konva.KonvaEventObject<DragEvent>) => {
    const s = useDesign.getState()
    const sc = s.history?.present
    if (!sc || !s.settings.snap || s.selection.length !== 1 || e.evt.altKey) {
      setGuides({ x: [], y: [] })
      return
    }
    const node = e.target
    const layer = sc.layers.find((l) => l.id === node.id())
    if (!layer) return
    const [, , w, h] = layer.box
    const b = bounds([node.x() - w / 2, node.y() - h / 2, w, h], layer.rotation)
    const others = sc.layers.filter((l) => l.id !== layer.id && l.visible && !(l.type === 'image' && l.role === 'background')).map((l) => bounds(l.box, l.rotation))
    const snapped = snapBox(b, others, [sc.page.width, sc.page.height], 6 / useView.getState().zoom)
    node.x(node.x() + snapped.box[0] - b[0])
    node.y(node.y() + snapped.box[1] - b[1])
    setGuides(snapped.guides)
  }, [])

  const onDragEnd = useCallback(() => {
    setGuides({ x: [], y: [] })
    const s = useDesign.getState()
    const sc = s.history?.present
    const stage = stageRef.current
    if (!sc || !stage) return
    let next = sc
    for (const id of s.selection) {
      const node = stage.findOne(`#${id}`)
      const l = next.layers.find((x) => x.id === id)
      if (!node || !l) continue
      const [, , w, h] = l.box
      const box: Box = [node.x() - w / 2, node.y() - h / 2, w, h]
      if (box[0] !== l.box[0] || box[1] !== l.box[1]) next = { ...next, layers: next.layers.map((x) => (x.id === id ? { ...x, box } : x)) }
    }
    s.commit(next)
  }, [])

  const onTransformEnd = useCallback((e: Konva.KonvaEventObject<Event>, layer: Layer) => {
    const node = e.target
    const sx = node.scaleX()
    const sy = node.scaleY()
    node.scaleX(1)
    node.scaleY(1)
    const [, , w0, h0] = layer.box
    let w = Math.max(2, w0 * sx)
    let h = Math.max(2, h0 * sy)
    const cx = node.x()
    const cy = node.y()
    let next: Layer = { ...layer, rotation: Math.round(node.rotation() * 100) / 100 }
    if (layer.type === 'text') {
      const uniform = Math.abs(sx - sy) < 0.01
      const style = uniform ? { ...layer.style, size: Math.max(1, layer.style.size * sy) } : layer.style
      const t = { ...layer, style } as TextLayer
      h = textHeight(t, metricsFor(style.family, style.weight, style.italic))
      w = uniform ? w0 * sx : w
      next = { ...t, rotation: next.rotation }
    } else if (layer.type === 'table' && Math.abs(sx - sy) < 0.01) {
      next = { ...layer, rotation: next.rotation, style: { ...layer.style, size: layer.style.size * sy } }
    } else if (layer.type === 'shape' && layer.shape === 'line' && layer.points) {
      const [a, b, c, d] = layer.points
      next = { ...layer, rotation: next.rotation, points: [a * sx, b * sy, c * sx, d * sy] }
    }
    next = { ...next, box: [cx - w / 2, cy - h / 2, w, h] }
    const s = useDesign.getState()
    s.patchLayer<Layer>(layer.id, () => next, `transform-${gesture.current}`)
  }, [])

  const onDblClick = useCallback((layer: Layer) => {
    if (layer.type === 'text' && !layer.locked) useDesign.getState().setEditingText(layer.id)
  }, [])

  if (!scene) return <div className="design-canvas" ref={wrapRef} />
  const editingLayer = editingText ? scene.layers.find((l) => l.id === editingText && l.type === 'text') as TextLayer | undefined : undefined
  const lowBoxes = highlight ? lowConfidenceBoxes(scene) : []
  const z = zoom

  return (
    <div className={`design-canvas ${space ? 'panning' : ''}`} ref={wrapRef} data-testid="design-canvas"
      onWheel={(e) => {
        const v = useView.getState()
        if (e.ctrlKey || e.metaKey) {
          const rect = wrapRef.current!.getBoundingClientRect()
          const mx = e.clientX - rect.left
          const my = e.clientY - rect.top
          const nz = Math.max(0.05, Math.min(16, v.zoom * Math.exp(-e.deltaY * 0.0015)))
          v.set({ zoom: nz, x: mx - ((mx - v.x) * nz) / v.zoom, y: my - ((my - v.y) * nz) / v.zoom })
        } else {
          v.set({ x: v.x - (e.shiftKey ? e.deltaY : e.deltaX), y: v.y - (e.shiftKey ? 0 : e.deltaY) })
        }
      }}>
      <Stage ref={stageRef} width={size.w} height={size.h} x={panX} y={panY} scaleX={z} scaleY={z}
        draggable={space}
        onDragEnd={(e) => {
          if (e.target === stageRef.current) useView.getState().set({ x: e.target.x(), y: e.target.y() })
        }}
        onMouseDown={(e) => {
          if (space) return
          if (e.target === e.target.getStage() || e.target.getParent()?.name() === 'page') useDesign.getState().select([])
        }}>
        <KLayer>
          <Group name="page">
            <Rect width={scene.page.width} height={scene.page.height} fill={scene.page.background} shadowColor="#000" shadowBlur={12 / z} shadowOpacity={0.25} />
          </Group>
          {scene.layers.map((l) => (
            <LayerNode key={l.id} layer={l} selected={selection.includes(l.id)} editing={editingText === l.id}
              onSelect={onSelect} onDragMove={onDragMove} onDragEnd={onDragEnd} onTransformEnd={onTransformEnd} onDblClick={onDblClick} />
          ))}
          {overlay === 'split' && original && (
            <Group clipX={0} clipY={0} clipWidth={scene.page.width * split} clipHeight={scene.page.height} listening={false}>
              <KImage image={original} width={scene.page.width} height={scene.page.height} />
            </Group>
          )}
          {overlay === 'diff' && original && (
            <KImage image={original} width={scene.page.width} height={scene.page.height} globalCompositeOperation="difference" listening={false} />
          )}
        </KLayer>
        <KLayer>
          {lowBoxes.map((b) => (
            <Rect key={b.key} x={b.box[0]} y={b.box[1]} width={b.box[2]} height={b.box[3]} stroke="#f59e0b" strokeWidth={2 / z} dash={[5 / z, 3 / z]} listening={false} />
          ))}
          {highlight && scene.unreadable?.map((u, i) => (
            <Rect key={`u${i}`} x={u.box[0] - 3} y={u.box[1] - 3} width={u.box[2] + 6} height={u.box[3] + 6} stroke="#7c3aed" strokeWidth={2 / z} dash={[8 / z, 4 / z]} listening={false} />
          ))}
          {accuracy?.regions.map((r, i) => (
            <Rect key={`r${i}`} x={r.x - 3} y={r.y - 3} width={r.w + 6} height={r.h + 6} stroke="#dc2626" strokeWidth={2 / z} listening={false} />
          ))}
          {guides.x.map((gx) => <Line key={`gx${gx}`} points={[gx, -10000, gx, 10000]} stroke="#ec4899" strokeWidth={1 / z} listening={false} />)}
          {guides.y.map((gy) => <Line key={`gy${gy}`} points={[-10000, gy, 10000, gy]} stroke="#ec4899" strokeWidth={1 / z} listening={false} />)}
          {overlay === 'split' && (
            <Group x={scene.page.width * split} draggable dragBoundFunc={(p) => ({ x: Math.max(panX, Math.min(panX + scene.page.width * z, p.x)), y: panY })}
              onDragMove={(e) => useDesign.getState().setSplit(e.target.x() / scene.page.width)}>
              <Line points={[0, 0, 0, scene.page.height]} stroke="#2f6feb" strokeWidth={2 / z} />
              <Rect x={-10 / z} y={scene.page.height / 2 - 18 / z} width={20 / z} height={36 / z} cornerRadius={4 / z} fill="#2f6feb" />
            </Group>
          )}
          <Transformer ref={trRef} keepRatio={keepRatio} rotationSnaps={[0, 45, 90, 135, 180, 225, 270, 315]} rotationSnapTolerance={4}
            ignoreStroke flipEnabled={false}
            boundBoxFunc={(oldB, newB) => (Math.abs(newB.width) < 4 || Math.abs(newB.height) < 2 ? oldB : newB)}
            onTransformStart={() => { gesture.current += 1 }} />
        </KLayer>
      </Stage>
      {overlay === 'split' && <div className="split-labels"><span>Original</span><span>Rebuilt</span></div>}
      {editingLayer && <TextEditor key={editingLayer.id} layer={editingLayer} />}
    </div>
  )
}

/** Width of a text layer's widest line (px), for sizing new boxes. */
export function widestLine(layer: TextLayer): number {
  const st = layer.style
  return Math.max(...layer.text.split('\n').map((t) => measure(t, cssFont(st.family, st.weight, st.italic, st.size))))
}
