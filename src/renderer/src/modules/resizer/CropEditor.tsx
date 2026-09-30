import type Konva from 'konva'
import { useEffect, useRef, useState } from 'react'
import { Image as KImage, Layer, Line, Rect, Shape, Stage, Transformer } from 'react-konva'
import { defaultCrop, normaliseCrop } from '@shared/geometry'
import type { Crop } from '@shared/types'
import { fmtNum } from '@shared/units'
import { type FileEntry, targetPx, useResizer } from './store'

export function useElementSize<T extends HTMLElement>(): [React.RefObject<T | null>, { w: number; h: number }] {
  const ref = useRef<T | null>(null)
  const [size, setSize] = useState({ w: 0, h: 0 })
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const ro = new ResizeObserver(([entry]) => setSize({ w: Math.floor(entry.contentRect.width), h: Math.floor(entry.contentRect.height) }))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  return [ref, size]
}

export function useHtmlImage(url: string | undefined): HTMLImageElement | null {
  const [img, setImg] = useState<HTMLImageElement | null>(null)
  useEffect(() => {
    if (!url) return setImg(null)
    const el = new window.Image()
    el.onload = () => setImg(el)
    el.onerror = () => setImg(null)
    el.src = url
  }, [url])
  return img
}

export function CropEditor({ file }: { file: FileEntry }) {
  const settings = useResizer((s) => s.history.present.settings)
  const stored = useResizer((s) => s.history.present.crops[file.id] ?? null)
  const setCrop = useResizer((s) => s.setCrop)
  const [boxRef, box] = useElementSize<HTMLDivElement>()
  const img = useHtmlImage(file.probe?.preview.url)
  const rectRef = useRef<Konva.Rect>(null)
  const trRef = useRef<Konva.Transformer>(null)
  const [live, setLive] = useState<{ x: number; y: number; w: number; h: number } | null>(null)
  const probe = file.probe!
  const target = targetPx(settings)

  useEffect(() => {
    if (trRef.current && rectRef.current) {
      trRef.current.nodes([rectRef.current])
      trRef.current.getLayer()?.batchDraw()
    }
  }, [img, box.w, box.h])

  if (!target) return <div className="empty-view">Enter a valid size to place the crop window.</div>

  const crop: Crop = stored ? normaliseCrop(stored, probe.width, probe.height, target[0], target[1]) : defaultCrop(probe.width, probe.height, target[0], target[1])
  const pw = probe.preview.width
  const ph = probe.preview.height
  const pad = 16
  const ds = box.w && box.h ? Math.min((box.w - pad * 2) / pw, (box.h - pad * 2) / ph) : 0
  const iw = pw * ds
  const ih = ph * ds
  const ox = (box.w - iw) / 2
  const oy = (box.h - ih) / 2
  const k = probe.preview.scale * ds // display px per source px
  const disp = live ?? { x: ox + crop.x * k, y: oy + crop.y * k, w: crop.w * k, h: crop.h * k }

  const commit = (x: number, y: number, w: number, h: number) => {
    const next = normaliseCrop({ x: (x - ox) / k, y: (y - oy) / k, w: w / k, h: h / k }, probe.width, probe.height, target[0], target[1])
    setLive(null)
    setCrop(file.id, next)
  }

  const nudge = (dx: number, dy: number) => {
    const next = normaliseCrop({ ...crop, x: crop.x + dx, y: crop.y + dy }, probe.width, probe.height, target[0], target[1])
    setCrop(file.id, next, 'nudge')
  }

  const scale = target[0] / crop.w
  return (
    <div className="crop-editor">
      <div ref={boxRef} className="crop-stage" tabIndex={0} data-testid="crop-stage" aria-label="Crop window. Arrow keys move it by 1 pixel, Shift+arrow by 10."
        onKeyDown={(e) => {
          const step = e.shiftKey ? 10 : 1
          const map: Record<string, [number, number]> = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] }
          if (map[e.key]) {
            e.preventDefault()
            nudge(...map[e.key])
          }
        }}>
        {box.w > 0 && img && (
          <Stage width={box.w} height={box.h}>
            <Layer>
              <KImage image={img} x={ox} y={oy} width={iw} height={ih} />
              <Shape listening={false} sceneFunc={(ctx) => {
                const c = ctx._context
                c.save()
                c.beginPath()
                c.rect(ox, oy, iw, ih)
                c.rect(disp.x, disp.y, disp.w, disp.h)
                c.fillStyle = 'rgba(0,0,0,0.55)'
                c.fill('evenodd')
                c.restore()
              }} />
              {[1, 2].map((i) => (
                <Line key={`v${i}`} listening={false} points={[disp.x + (disp.w * i) / 3, disp.y, disp.x + (disp.w * i) / 3, disp.y + disp.h]} stroke="rgba(255,255,255,0.55)" strokeWidth={1} />
              ))}
              {[1, 2].map((i) => (
                <Line key={`h${i}`} listening={false} points={[disp.x, disp.y + (disp.h * i) / 3, disp.x + disp.w, disp.y + (disp.h * i) / 3]} stroke="rgba(255,255,255,0.55)" strokeWidth={1} />
              ))}
              <Rect ref={rectRef} x={disp.x} y={disp.y} width={disp.w} height={disp.h} stroke="#4f8cff" strokeWidth={2} draggable
                dragBoundFunc={(pos) => ({
                  x: Math.min(Math.max(pos.x, ox), ox + iw - disp.w),
                  y: Math.min(Math.max(pos.y, oy), oy + ih - disp.h)
                })}
                onDragMove={(e) => setLive({ x: e.target.x(), y: e.target.y(), w: disp.w, h: disp.h })}
                onDragEnd={(e) => commit(e.target.x(), e.target.y(), disp.w, disp.h)}
                onTransform={(e) => {
                  const n = e.target
                  setLive({ x: n.x(), y: n.y(), w: n.width() * n.scaleX(), h: n.height() * n.scaleY() })
                }}
                onTransformEnd={(e) => {
                  const n = e.target
                  const w = n.width() * n.scaleX()
                  const h = n.height() * n.scaleY()
                  n.scaleX(1)
                  n.scaleY(1)
                  commit(n.x(), n.y(), w, h)
                }} />
              <Transformer ref={trRef} keepRatio rotateEnabled={false} flipEnabled={false}
                enabledAnchors={['top-left', 'top-right', 'bottom-left', 'bottom-right']}
                anchorSize={12} borderStroke="#4f8cff" anchorStroke="#4f8cff"
                boundBoxFunc={(oldBox, newBox) => {
                  const tooSmall = newBox.width < 12 || newBox.height < 12
                  const outside = newBox.x < ox - 0.5 || newBox.y < oy - 0.5 || newBox.x + newBox.width > ox + iw + 0.5 || newBox.y + newBox.height > oy + ih + 0.5
                  return tooSmall || outside ? oldBox : newBox
                }} />
            </Layer>
          </Stage>
        )}
      </div>
      <div className="crop-info" data-testid="crop-info">
        <span>Crop window: {fmtNum(crop.w, 1)} × {fmtNum(crop.h, 1)} source px at ({fmtNum(crop.x, 1)}, {fmtNum(crop.y, 1)})</span>
        <span>→ {target[0]} × {target[1]} px ({scale > 1 ? `enlarged ${fmtNum(scale, 2)}×` : `reduced to ${fmtNum(scale * 100, 1)}%`})</span>
        <span className="spacer" />
        <button className="btn small ghost" onClick={() => setCrop(file.id, null)}>Centre / reset</button>
      </div>
    </div>
  )
}
