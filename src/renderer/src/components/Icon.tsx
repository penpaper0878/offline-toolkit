/** A small inline icon set (no icon fonts or CDNs). 24px grid, stroke icons. */

const PATHS: Record<string, string> = {
  resize: 'M4 14v6h6M20 10V4h-6M4 20l7-7M20 4l-7 7',
  convert: 'M4 7h13l-3-3M20 17H7l3 3',
  design: 'M3 21l3-1 11-11-2-2L4 18l-1 3zM14 6l2-2 4 4-2 2',
  passport: 'M6 3h12v18H6zM12 13a3 3 0 100-6 3 3 0 000 6zM8.5 17.5c1-2 6-2 7 0',
  log: 'M5 4h14v16H5zM8 8h8M8 12h8M8 16h5',
  settings: 'M12 15a3 3 0 100-6 3 3 0 000 6zM19.4 15a1.7 1.7 0 00.3 1.8l.1.1a2 2 0 11-2.8 2.8l-.1-.1a1.7 1.7 0 00-1.8-.3 1.7 1.7 0 00-1 1.5V21a2 2 0 11-4 0v-.1a1.7 1.7 0 00-1.1-1.5 1.7 1.7 0 00-1.8.3l-.1.1a2 2 0 11-2.8-2.8l.1-.1a1.7 1.7 0 00.3-1.8 1.7 1.7 0 00-1.5-1H3a2 2 0 110-4h.1a1.7 1.7 0 001.5-1.1 1.7 1.7 0 00-.3-1.8l-.1-.1a2 2 0 112.8-2.8l.1.1a1.7 1.7 0 001.8.3H9a1.7 1.7 0 001-1.5V3a2 2 0 114 0v.1a1.7 1.7 0 001 1.5 1.7 1.7 0 001.8-.3l.1-.1a2 2 0 112.8 2.8l-.1.1a1.7 1.7 0 00-.3 1.8V9a1.7 1.7 0 001.5 1H21a2 2 0 110 4h-.1a1.7 1.7 0 00-1.5 1z',
  add: 'M12 5v14M5 12h14',
  folder: 'M3 6h6l2 2h10v11H3z',
  play: 'M7 5l12 7-12 7z',
  undo: 'M9 14L4 9l5-5M4 9h11a5 5 0 010 10h-3',
  redo: 'M15 14l5-5-5-5M20 9H9a5 5 0 000 10h3',
  trash: 'M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13',
  lock: 'M6 11h12v9H6zM8 11V8a4 4 0 118 0v3',
  unlock: 'M6 11h12v9H6zM8 11V8a4 4 0 017.5-2',
  zip: 'M6 3h9l3 3v15H6zM11 3v2h2v2h-2v2h2v2h-2',
  check: 'M5 12l5 5 9-10',
  warn: 'M12 4l9 16H3zM12 10v4M12 17h.01',
  x: 'M6 6l12 12M18 6L6 18',
  shield: 'M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z',
  swap: 'M7 4v16M3 16l4 4 4-4M17 20V4M21 8l-4-4-4 4',
  save: 'M5 3h12l2 2v16H5zM8 3v6h8V3M8 21v-7h8v7'
}

export function Icon({ name, size = 18, title }: { name: keyof typeof PATHS | string; size?: number; title?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8}
      strokeLinecap="round" strokeLinejoin="round" aria-hidden={title ? undefined : true} role={title ? 'img' : undefined}>
      {title && <title>{title}</title>}
      <path d={PATHS[name] ?? PATHS.x} />
    </svg>
  )
}
