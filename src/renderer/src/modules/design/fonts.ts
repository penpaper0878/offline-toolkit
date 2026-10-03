/**
 * Fonts for the design canvas: the same static font files the exporters use, loaded as FontFaces under the
 * family's own name, so what the canvas draws is what PowerPoint, Word and the SVG show.
 */

import { faceKey, type FontMetrics, snapWeight } from '@shared/design'
import { otk } from '../../lib/api'

const pending = new Map<string, Promise<FontMetrics>>()
const ready = new Map<string, FontMetrics>()
const listeners = new Set<() => void>()

const FALLBACK: FontMetrics = { ascent: 0.93, descent: 0.25, lineGap: 0 }

/** Load one face (once); resolves to its vertical metrics. */
export function ensureFace(family: string, weight: number, italic: boolean): Promise<FontMetrics> {
  const key = faceKey(family, weight, italic)
  let p = pending.get(key)
  if (!p) {
    p = (async () => {
      let url = ''
      try {
        const r = await otk().design.fontFace({ family, weight: snapWeight(weight), italic })
        url = r.url
        const face = new FontFace(family, `url("${r.url}")`, { weight: String(r.weight), style: r.italic ? 'italic' : 'normal' })
        await face.load()
        document.fonts.add(face)
        ready.set(key, r.metrics)
        for (const cb of listeners) cb()
        return r.metrics
      } catch (e) {
        // A face that cannot load falls back to a default font on the canvas; the exports still name it.
        pending.delete(key)
        void otk().log.add('warn', `Font ${family} ${weight}${italic ? ' italic' : ''} could not be loaded for the canvas: ${(e as Error)?.message ?? e}`, { url })
        return FALLBACK
      }
    })()
    pending.set(key, p)
  }
  return p
}

/** Metrics of a loaded face (or a neutral guess while it loads). */
export function metricsFor(family: string, weight: number, italic: boolean): FontMetrics {
  return ready.get(faceKey(family, weight, italic)) ?? FALLBACK
}

export function isLoaded(family: string, weight: number, italic: boolean): boolean {
  return ready.has(faceKey(family, weight, italic))
}

/** Called whenever another face finishes loading (the canvas redraws). */
export function onFontsLoaded(cb: () => void): () => void {
  listeners.add(cb)
  return () => listeners.delete(cb)
}

let measureCtx: CanvasRenderingContext2D | null = null

/** Advance width of a line of text in a face at a size (px). */
export function measure(text: string, font: string): number {
  if (!measureCtx) measureCtx = document.createElement('canvas').getContext('2d')
  if (!measureCtx) return text.length * 8
  measureCtx.font = font
  return measureCtx.measureText(text).width
}
