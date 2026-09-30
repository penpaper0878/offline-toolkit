/** Crop-window maths. Mirrors worker/otk_worker/resizer/geometry.py (tested with the same cases). */

import type { Crop } from './types'

/** Largest centred window with the target aspect ratio. */
export function defaultCrop(srcW: number, srcH: number, tgtW: number, tgtH: number): Crop {
  const aspect = tgtW / tgtH
  let w: number
  let h: number
  if (srcW / srcH > aspect) {
    h = srcH
    w = srcH * aspect
  } else {
    w = srcW
    h = srcW / aspect
  }
  return { x: (srcW - w) / 2, y: (srcH - h) / 2, w, h }
}

/** Clamp to the image and force the exact aspect, keeping the centre and width. */
export function normaliseCrop(c: Crop | null | undefined, srcW: number, srcH: number, tgtW: number, tgtH: number): Crop {
  if (!c || !(c.w > 0) || !(c.h > 0)) return defaultCrop(srcW, srcH, tgtW, tgtH)
  const aspect = tgtW / tgtH
  const cx = c.x + c.w / 2
  const cy = c.y + c.h / 2
  let w = Math.min(c.w, srcW)
  let h = w / aspect
  if (h > srcH) {
    h = srcH
    w = h * aspect
  }
  const x = Math.min(Math.max(cx - w / 2, 0), srcW - w)
  const y = Math.min(Math.max(cy - h / 2, 0), srcH - h)
  return { x, y, w, h }
}

/** Output pixels per source pixel for a crop (> 1 means the image is enlarged). */
export function cropScale(c: Crop, tgtW: number): number {
  return tgtW / c.w
}
