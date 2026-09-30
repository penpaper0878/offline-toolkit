import { useEffect, useRef } from 'react'
import type { PreviewResult } from '@shared/types'
import { useElementSize, useHtmlImage } from './CropEditor'
import { type FileEntry, useResizer } from './store'

function checkerboard(ctx: CanvasRenderingContext2D, w: number, h: number): void {
  const s = 8
  for (let y = 0; y < h; y += s) {
    for (let x = 0; x < w; x += s) {
      ctx.fillStyle = ((x / s + y / s) & 1) === 0 ? '#d9dbe0' : '#f4f5f7'
      ctx.fillRect(x, y, s, s)
    }
  }
}

/** Before (source, uncompressed) | After (the actual encoded file) with a split handle and zoom. */
export function PreviewView({ file, result }: { file: FileEntry; result: PreviewResult }) {
  const zoom = useResizer((s) => s.zoom)
  const split = useResizer((s) => s.split)
  const padColor = useResizer((s) => s.history.present.settings.padColor)
  const src = useHtmlImage(file.probe?.preview.url)
  const after = useHtmlImage(result.previewUrl)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [boxRef, box] = useElementSize<HTMLDivElement>()
  const w = result.output!.width
  const h = result.output!.height
  const fitScale = box.w && box.h ? Math.min((box.w - 32) / w, (box.h - 32) / h) : 1
  const scale = zoom === 'fit' ? fitScale : zoom

  useEffect(() => {
    const c = canvasRef.current
    if (!c || !src || !after) return
    c.width = w
    c.height = h
    const ctx = c.getContext('2d')!
    ctx.imageSmoothingQuality = 'high'
    const fit = result.fit!
    const ps = file.probe!.preview.scale
    checkerboard(ctx, w, h)
    // Before: the source placed exactly as the worker placed it, without compression.
    if (fit.mode === 'crop' && fit.crop) {
      const cr = fit.crop
      ctx.drawImage(src, cr.x * ps, cr.y * ps, cr.w * ps, cr.h * ps, 0, 0, w, h)
    } else if (fit.mode === 'pad') {
      const { inner, offset } = fit
      ctx.fillStyle = padColor.slice(0, 7)
      ctx.globalAlpha = padColor.length === 9 ? parseInt(padColor.slice(7, 9), 16) / 255 : 1
      ctx.fillRect(0, 0, w, h)
      ctx.globalAlpha = 1
      ctx.drawImage(src, 0, 0, src.width, src.height, offset[0], offset[1], inner[0], inner[1])
    } else {
      ctx.drawImage(src, 0, 0, src.width, src.height, 0, 0, w, h)
    }
    // After: the real output file, right of the split.
    const sx = Math.round((split / 100) * w)
    ctx.save()
    ctx.beginPath()
    ctx.rect(sx, 0, w - sx, h)
    ctx.clip()
    checkerboard(ctx, w, h)
    ctx.drawImage(after, 0, 0, w, h)
    ctx.restore()
  }, [src, after, w, h, split, result, file, padColor])

  return (
    <div className="compare" ref={boxRef}>
      <div className="compare-scroll">
        <div className="compare-canvas-wrap" style={{ width: w * scale, height: h * scale }}>
          <canvas ref={canvasRef} data-testid="compare-canvas"
            style={{ width: w * scale, height: h * scale, imageRendering: scale >= 2 ? 'pixelated' : 'auto' }} />
          <div className="split-line" style={{ left: `${split}%` }} aria-hidden />
          <span className="compare-tag left">Before (source)</span>
          <span className="compare-tag right">After (actual file)</span>
        </div>
      </div>
    </div>
  )
}
