import { type ReactElement, useEffect, useMemo, useRef, useState } from 'react'
import {
  type Box, cssFont, type FontFamilyInfo, type ImageLayer, type Layer, type ShapeLayer, type TableCell, type TableLayer,
  type TextLayer, type TextStyle, type VectorLayer, WEIGHT_NAMES
} from '@shared/design'
import { Icon } from '../../components/Icon'
import { NumberField, Section, Segmented, Select, Toggle } from '../../components/controls'
import { useView } from './CanvasView'
import { ensureFace } from './fonts'
import { useDesign } from './store'

const TYPE_ICON: Record<string, string> = { image: 'image', shape: 'square', vector: 'design', text: 'text', table: 'layers' }

// ------------------------------------------------------------------ layers
export function LayersPanel(): ReactElement {
  const scene = useDesign((s) => s.history?.present ?? null)
  const selection = useDesign((s) => s.selection)
  const st = useDesign.getState()
  const [renaming, setRenaming] = useState<string | null>(null)
  const [dragId, setDragId] = useState<string | null>(null)
  if (!scene) return <aside className="design-layers" />
  const rows = [...scene.layers].reverse()
  const move = (id: string, beforeId: string) => {
    if (id === beforeId) return
    const layers = scene.layers.filter((l) => l.id !== id)
    const moving = scene.layers.find((l) => l.id === id)!
    const target = layers.findIndex((l) => l.id === beforeId)
    // Rows are shown top-first, so dropping on a row puts the layer just above it.
    layers.splice(target + 1, 0, moving)
    st.commit({ ...scene, layers })
  }
  return (
    <aside className="design-layers" aria-label="Layers" data-testid="design-layers">
      <header className="design-panel-head"><Icon name="layers" size={16} /> Layers <span className="muted small">{scene.layers.length}</span></header>
      <ul className="layer-list" role="listbox" aria-multiselectable>
        {rows.map((l) => (
          <li key={l.id} role="option" aria-selected={selection.includes(l.id)} data-testid={`layer-row-${l.id}`}
            className={`layer-row ${selection.includes(l.id) ? 'selected' : ''} ${l.visible ? '' : 'hidden'} ${dragId === l.id ? 'dragging' : ''}`}
            draggable={!(l.type === 'image' && l.role === 'background')}
            onDragStart={(e) => { setDragId(l.id); e.dataTransfer.effectAllowed = 'move' }}
            onDragOver={(e) => { if (dragId) e.preventDefault() }}
            onDrop={(e) => { e.preventDefault(); if (dragId) move(dragId, l.id); setDragId(null) }}
            onDragEnd={() => setDragId(null)}
            onClick={(e) => {
              if (e.shiftKey) st.select(selection.includes(l.id) ? selection.filter((x) => x !== l.id) : [...selection, l.id])
              else st.select([l.id])
            }}
            onDoubleClick={() => setRenaming(l.id)}>
            <Icon name={TYPE_ICON[l.type]} size={15} />
            {renaming === l.id ? (
              <input className="layer-name-input" autoFocus defaultValue={l.name}
                onBlur={(e) => { st.patchLayer(l.id, { name: e.target.value.trim() || l.name }); setRenaming(null) }}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === 'Escape') (e.target as HTMLInputElement).blur(); e.stopPropagation() }} />
            ) : (
              <span className="layer-name" title={l.name}>{l.name}</span>
            )}
            {l.type === 'text' && (l.lowConfidence?.length ?? 0) > 0 && <span className="dot warn" title="Has words to check" />}
            <button className="icon-btn tiny" aria-label={l.visible ? 'Hide' : 'Show'} title={l.visible ? 'Hide' : 'Show'}
              onClick={(e) => { e.stopPropagation(); st.patchLayer(l.id, { visible: !l.visible }) }}>
              <Icon name={l.visible ? 'eye' : 'eye-off'} size={14} />
            </button>
            <button className={`icon-btn tiny ${l.locked ? 'on' : ''}`} aria-label={l.locked ? 'Unlock' : 'Lock'} title={l.locked ? 'Unlock' : 'Lock'}
              onClick={(e) => { e.stopPropagation(); st.patchLayer(l.id, { locked: !l.locked }) }}>
              <Icon name={l.locked ? 'lock' : 'unlock'} size={14} />
            </button>
          </li>
        ))}
      </ul>
      <footer className="layer-actions">
        <button className="icon-btn" title="Bring forward (Ctrl+])" aria-label="Bring forward" disabled={!selection.length} onClick={() => st.reorderSelected(1)}><Icon name="up" size={16} /></button>
        <button className="icon-btn" title="Send backward (Ctrl+[)" aria-label="Send backward" disabled={!selection.length} onClick={() => st.reorderSelected(-1)}><Icon name="down" size={16} /></button>
        <button className="icon-btn" title="Duplicate (Ctrl+D)" aria-label="Duplicate" disabled={!selection.length} onClick={() => st.duplicateSelected()}><Icon name="copy" size={16} /></button>
        <button className="icon-btn" title="Delete (Del)" aria-label="Delete" disabled={!selection.length} onClick={() => st.removeSelected()}><Icon name="trash" size={16} /></button>
      </footer>
    </aside>
  )
}

// ------------------------------------------------------------------ inspector
function ColorField(props: { label: string; value: string | null; onChange: (v: string | null) => void; allowNone?: boolean; testId?: string }) {
  const [text, setText] = useState(props.value ?? '')
  useEffect(() => setText(props.value ?? ''), [props.value])
  return (
    <div className="field">
      <span className="field-label">{props.label}</span>
      <div className="color-row">
        <input type="color" value={props.value ?? '#ffffff'} aria-label={props.label} data-testid={props.testId}
          onChange={(e) => props.onChange(e.target.value)} />
        <input className="hex" value={text} placeholder={props.allowNone ? 'none' : '#000000'} aria-label={`${props.label} hex`}
          onChange={(e) => {
            setText(e.target.value)
            const v = e.target.value.trim()
            if (/^#[0-9a-f]{6}$/i.test(v)) props.onChange(v.toLowerCase())
            else if (props.allowNone && v === '') props.onChange(null)
          }} />
        {props.allowNone && props.value && <button className="link-btn" onClick={() => props.onChange(null)}>None</button>}
      </div>
    </div>
  )
}

function FontPicker(props: { value: string; script?: string; suggestions: string[]; onChange: (family: string) => void }) {
  const fonts = useDesign((s) => s.fonts)
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [allScripts, setAllScripts] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const close = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false) }
    window.addEventListener('mousedown', close)
    return () => window.removeEventListener('mousedown', close)
  }, [open])
  const list = useMemo(() => {
    const q = query.trim().toLowerCase()
    const all = (fonts ?? []).filter((f) => (allScripts || !props.script || f.scripts.includes(props.script)) && (!q || f.family.toLowerCase().includes(q)))
    return all
  }, [fonts, query, allScripts, props.script])
  const sugg = props.suggestions.filter((f, i, a) => a.indexOf(f) === i && (fonts ?? []).some((x) => x.family === f))
  const pick = (f: string) => {
    props.onChange(f)
    setOpen(false)
    setQuery('')
  }
  return (
    <div className="field font-picker" ref={ref}>
      <span className="field-label">Font</span>
      <button className="font-picker-btn" data-testid="design-font-picker" onClick={() => setOpen(!open)} aria-expanded={open}>
        <span style={{ fontFamily: `"${props.value}"` }}>{props.value}</span> <span className="muted">▾</span>
      </button>
      {open && (
        <div className="font-menu" role="listbox">
          <input autoFocus className="font-search" placeholder="Search fonts" value={query} onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => { e.stopPropagation(); if (e.key === 'Escape') setOpen(false); if (e.key === 'Enter' && list[0]) pick(list[0].family) }} />
          {sugg.length > 0 && !query && (
            <>
              <div className="font-group">Closest matches</div>
              {sugg.map((f) => <button key={`s-${f}`} role="option" className={`font-item ${f === props.value ? 'on' : ''}`} onClick={() => pick(f)}>{f}</button>)}
              <div className="font-group">All fonts</div>
            </>
          )}
          {list.map((f) => (
            <button key={f.family} role="option" className={`font-item ${f.family === props.value ? 'on' : ''}`} onClick={() => pick(f.family)}
              title={`${f.category ?? ''} — ${f.licence ?? ''}`}>
              {f.family} <span className="muted small">{f.category?.toLowerCase().replace('_', ' ')}</span>
            </button>
          ))}
          {props.script && props.script !== 'latin' && (
            <label className="font-all"><input type="checkbox" checked={allScripts} onChange={(e) => setAllScripts(e.target.checked)} /> Show fonts without {props.script} letters</label>
          )}
        </div>
      )}
    </div>
  )
}

function familyInfo(fonts: FontFamilyInfo[] | null, family: string): FontFamilyInfo | undefined {
  return fonts?.find((f) => f.family === family)
}

function nearestWeight(info: FontFamilyInfo | undefined, weight: number, italic: boolean): number {
  const ws = info?.styles.filter((s) => s.italic === italic).map((s) => s.weight) ?? []
  if (!ws.length) return weight
  return ws.reduce((a, b) => (Math.abs(b - weight) < Math.abs(a - weight) ? b : a))
}

function TextProps({ layer }: { layer: TextLayer }) {
  const st = useDesign.getState()
  const fonts = useDesign((s) => s.fonts)
  const s = layer.style
  const info = familyInfo(fonts, s.family)
  const weights = [...new Set(info?.styles.filter((x) => x.italic === s.italic).map((x) => x.weight) ?? [s.weight])].sort((a, b) => a - b)
  const hasItalic = info?.styles.some((x) => x.italic) ?? false
  const setStyle = (patch: Partial<TextStyle>, key?: string) => {
    const next = { ...s, ...patch }
    void ensureFace(next.family, next.weight, next.italic).then(() => st.fitTextBox(layer.id))
    st.patchLayer<TextLayer>(layer.id, (l) => ({ ...l, style: next }), key ?? null)
    st.fitTextBox(layer.id)
  }
  const low = (layer.lowConfidence ?? []).map((i) => layer.words?.[i]).filter(Boolean)
  return (
    <>
      <Section title="Text">
        <label className="field">
          <span className="field-label">Content</span>
          <textarea className="text-content" data-testid="design-text-content" rows={Math.min(8, layer.text.split('\n').length + 1)} value={layer.text}
            dir={layer.script === 'arabic' || layer.script === 'hebrew' ? 'rtl' : 'ltr'}
            onChange={(e) => { st.patchLayer<TextLayer>(layer.id, { text: e.target.value }, `text-${layer.id}`); st.fitTextBox(layer.id) }}
            onKeyDown={(e) => e.stopPropagation()} />
        </label>
        {low.length > 0 && (
          <div className="low-words" data-testid="design-low-words">
            <Icon name="warn" size={14} /> Check: {low.map((w, i) => <span key={i} className="low-word" title={`${Math.round(w!.conf * 100)}% sure`}>{w!.text}</span>)}
            <button className="link-btn" onClick={() => st.patchLayer<TextLayer>(layer.id, { lowConfidence: [] })}>Mark as checked</button>
          </div>
        )}
        <FontPicker value={s.family} script={layer.script} suggestions={(layer.fontCandidates ?? []).map((c) => c.family)}
          onChange={(family) => {
            const fi = familyInfo(fonts, family)
            const italic = s.italic && (fi?.styles.some((x) => x.italic) ?? false)
            setStyle({ family, italic, weight: nearestWeight(fi, s.weight, italic) })
          }} />
        <div className="grid-2">
          <Select label="Weight" value={String(s.weight)} options={weights.map((w) => ({ value: String(w), label: `${w} ${WEIGHT_NAMES[w] ?? ''}` }))}
            onChange={(v) => setStyle({ weight: Number(v) })} testId="design-weight" />
          <NumberField label="Size" value={Math.round(s.size * 100) / 100} min={1} max={2000} step={1} suffix="px"
            onChange={(v) => v && setStyle({ size: v }, `size-${layer.id}`)} testId="design-size" />
        </div>
        <div className="row-gap">
          <Toggle label="Italic" checked={s.italic} disabled={!hasItalic} onChange={(v) => setStyle({ italic: v, weight: nearestWeight(info, s.weight, v) })} />
          <Toggle label="Underline" checked={s.underline} onChange={(v) => setStyle({ underline: v })} />
        </div>
        <ColorField label="Colour" value={s.color} onChange={(v) => v && setStyle({ color: v }, `color-${layer.id}`)} testId="design-text-color" />
        <Segmented label="Alignment" value={s.align} onChange={(v) => setStyle({ align: v })} testId="design-align"
          options={[{ value: 'left', label: 'Left' }, { value: 'center', label: 'Centre' }, { value: 'right', label: 'Right' }, { value: 'justify', label: 'Justify' }]} />
        <NumberField label="Line spacing" value={Math.round(s.lineHeight * 1000) / 1000} min={0.5} max={5} step={0.05} suffix="× size"
          onChange={(v) => v && setStyle({ lineHeight: v }, `lh-${layer.id}`)} />
        {(layer.fontCandidates?.length ?? 0) > 0 && (
          <div className="muted small">Matched: {layer.fontCandidates!.slice(0, 3).map((c) => `${c.family} ${c.weight}${c.italic ? ' italic' : ''} (${Math.round(c.score * 100)}%)`).join(' · ')}</div>
        )}
        <div className="font-preview" style={{ font: cssFont(s.family, s.weight, s.italic, 20), color: s.color }}>{layer.text.split('\n')[0].slice(0, 40) || 'Aa'}</div>
      </Section>
    </>
  )
}

function ShapeProps({ layer }: { layer: ShapeLayer }) {
  const st = useDesign.getState()
  const line = layer.shape === 'line'
  return (
    <Section title={line ? 'Line' : 'Shape'}>
      {!line && (
        <Segmented label="Shape" value={layer.shape} onChange={(v) => st.patchLayer<ShapeLayer>(layer.id, { shape: v, radius: v === 'rounded' ? (layer.radius || Math.min(layer.box[2], layer.box[3]) / 8) : layer.radius })}
          options={[{ value: 'rect', label: 'Rectangle' }, { value: 'rounded', label: 'Rounded' }, { value: 'ellipse', label: 'Ellipse' }]} />
      )}
      {!line && <ColorField label="Fill" value={layer.fill} allowNone onChange={(v) => st.patchLayer<ShapeLayer>(layer.id, { fill: v }, `fill-${layer.id}`)} testId="design-fill" />}
      <ColorField label={line ? 'Colour' : 'Outline'} value={layer.stroke} allowNone={!line}
        onChange={(v) => st.patchLayer<ShapeLayer>(layer.id, { stroke: v, strokeWidth: v && !layer.strokeWidth ? 2 : layer.strokeWidth }, `stroke-${layer.id}`)} />
      <div className="grid-2">
        <NumberField label={line ? 'Thickness' : 'Outline width'} value={Math.round(layer.strokeWidth * 10) / 10} min={0} max={500} step={1} suffix="px"
          onChange={(v) => v !== null && st.patchLayer<ShapeLayer>(layer.id, { strokeWidth: v }, `sw-${layer.id}`)} />
        {layer.shape === 'rounded' && (
          <NumberField label="Corner radius" value={Math.round((layer.radius ?? 0) * 10) / 10} min={0} max={5000} step={1} suffix="px"
            onChange={(v) => v !== null && st.patchLayer<ShapeLayer>(layer.id, { radius: v }, `r-${layer.id}`)} />
        )}
      </div>
    </Section>
  )
}

function VectorProps({ layer }: { layer: VectorLayer }) {
  const st = useDesign.getState()
  const colors = [...new Set(layer.paths.map((p) => p.fill.toLowerCase()))]
  return (
    <Section title="Graphic">
      <p className="muted small">Traced into {layer.paths.length} vector shape(s). Change a colour to recolour every part that uses it.</p>
      {colors.map((c) => (
        <ColorField key={c} label={`Colour ${c}`} value={c}
          onChange={(v) => v && st.patchLayer<VectorLayer>(layer.id, (l) => ({ ...l, paths: l.paths.map((p) => (p.fill.toLowerCase() === c ? { ...p, fill: v } : p)) }), `vc-${layer.id}-${c}`)} />
      ))}
      {layer.source?.pixels && (
        <button className="btn small" onClick={() => void st.vectorToPixels(layer.id)} title="Use the original pixels instead of the traced shapes (for gradients and photos)">Use original pixels instead</button>
      )}
    </Section>
  )
}

function ImageProps({ layer }: { layer: ImageLayer }) {
  const st = useDesign.getState()
  const busy = useDesign((s) => s.busy)
  const bg = layer.role === 'background'
  return (
    <Section title={bg ? 'Background' : 'Picture'}>
      {bg && <p className="muted small">The page with every text, shape and picture removed. It is locked so it does not move while you edit; unlock it to change it.</p>}
      <div className="row-gap wrap">
        <button className="btn small" onClick={() => void st.replaceImage(layer.id)}><Icon name="image" size={14} /> Replace…</button>
        {!bg && (
          <>
            <button className="btn small" disabled={!!busy} data-testid="design-cutout" onClick={() => void st.cutout(layer.id, 'auto')} title="Remove the background around the person or object">
              <Icon name="scissors" size={14} /> Remove background
            </button>
            {layer.originalAsset && <button className="btn small ghost" onClick={() => st.restoreImage(layer.id)}>Restore original</button>}
          </>
        )}
      </div>
      {!bg && (
        <div className="row-gap wrap small">
          <button className="link-btn" disabled={!!busy} onClick={() => void st.cutout(layer.id, 'person')}>Cut out a person</button>
          <button className="link-btn" disabled={!!busy} onClick={() => void st.cutout(layer.id, 'subject')}>Cut out the main object</button>
        </div>
      )}
    </Section>
  )
}

function TableProps({ layer }: { layer: TableLayer }) {
  const st = useDesign.getState()
  const fonts = useDesign((s) => s.fonts)
  const [cellKey, setCellKey] = useState<string | null>(null)
  const rows = layer.rowHeights.length
  const cols = layer.colWidths.length
  const at = (r: number, c: number) => layer.cells.find((x) => x.row === r && x.col === c)
  const cell = cellKey ? layer.cells.find((x) => `${x.row}-${x.col}` === cellKey) : undefined
  const setCell = (patch: Partial<TableCell>, key?: string) => {
    if (!cell) return
    st.patchLayer<TableLayer>(layer.id, (l) => ({ ...l, cells: l.cells.map((x) => (x.row === cell.row && x.col === cell.col ? { ...x, ...patch } : x)) }), key ?? null)
    if (patch.weight !== undefined || patch.italic !== undefined) void ensureFace(layer.style.family, patch.weight ?? cell.weight, patch.italic ?? cell.italic)
  }
  const addRow = () => st.patchLayer<TableLayer>(layer.id, (l) => {
    const h = l.rowHeights[l.rowHeights.length - 1]
    const k = l.box[3] / l.rowHeights.reduce((a, b) => a + b, 0)
    const cells = [...l.cells, ...l.colWidths.map((_, c) => ({ row: rows, col: c, rowSpan: 1, colSpan: 1, text: '', fill: null, weight: 400, italic: false, align: 'left' as const, valign: 'middle' as const }))]
    return { ...l, rowHeights: [...l.rowHeights, h], cells, box: [l.box[0], l.box[1], l.box[2], l.box[3] + h * k] as Box }
  })
  const addCol = () => st.patchLayer<TableLayer>(layer.id, (l) => {
    const w = l.colWidths[l.colWidths.length - 1]
    const k = l.box[2] / l.colWidths.reduce((a, b) => a + b, 0)
    const cells = [...l.cells, ...l.rowHeights.map((_, r) => ({ row: r, col: cols, rowSpan: 1, colSpan: 1, text: '', fill: null, weight: 400, italic: false, align: 'left' as const, valign: 'middle' as const }))]
    return { ...l, colWidths: [...l.colWidths, w], cells, box: [l.box[0], l.box[1], l.box[2] + w * k, l.box[3]] as Box }
  })
  const dropLast = (what: 'row' | 'col') => st.patchLayer<TableLayer>(layer.id, (l) => {
    const n = what === 'row' ? l.rowHeights.length : l.colWidths.length
    if (n <= 1) return l
    const sizes = what === 'row' ? l.rowHeights : l.colWidths
    const k = (what === 'row' ? l.box[3] : l.box[2]) / sizes.reduce((a, b) => a + b, 0)
    const cut = sizes[n - 1] * k
    const cells = l.cells.filter((c) => (what === 'row' ? c.row : c.col) < n - 1).map((c) => (
      what === 'row' ? { ...c, rowSpan: Math.min(c.rowSpan, n - 1 - c.row) } : { ...c, colSpan: Math.min(c.colSpan, n - 1 - c.col) }))
    return what === 'row'
      ? { ...l, rowHeights: l.rowHeights.slice(0, -1), cells, box: [l.box[0], l.box[1], l.box[2], l.box[3] - cut] as Box }
      : { ...l, colWidths: l.colWidths.slice(0, -1), cells, box: [l.box[0], l.box[1], l.box[2] - cut, l.box[3]] as Box }
  })
  return (
    <Section title={`Table (${rows} × ${cols})`}>
      <FontPicker value={layer.style.family} suggestions={(layer.fontCandidates ?? []).map((c) => c.family)}
        onChange={(family) => {
          st.patchLayer<TableLayer>(layer.id, (l) => ({ ...l, style: { ...l.style, family }, cells: l.cells.map((c) => ({ ...c, weight: nearestWeight(familyInfo(fonts, family), c.weight, c.italic) })) }))
          for (const c of layer.cells) void ensureFace(family, c.weight, c.italic)
        }} />
      <div className="grid-2">
        <NumberField label="Text size" value={Math.round(layer.style.size * 100) / 100} min={1} max={500} suffix="px"
          onChange={(v) => v && st.patchLayer<TableLayer>(layer.id, (l) => ({ ...l, style: { ...l.style, size: v } }), `tsz-${layer.id}`)} />
        <NumberField label="Rule width" value={layer.border.width} min={0} max={50} step={0.5} suffix="px"
          onChange={(v) => v !== null && st.patchLayer<TableLayer>(layer.id, (l) => ({ ...l, border: { ...l.border, width: v } }), `tbw-${layer.id}`)} />
      </div>
      <ColorField label="Text colour" value={layer.style.color} onChange={(v) => v && st.patchLayer<TableLayer>(layer.id, (l) => ({ ...l, style: { ...l.style, color: v } }), `tc-${layer.id}`)} />
      <ColorField label="Rule colour" value={layer.border.color} onChange={(v) => v && st.patchLayer<TableLayer>(layer.id, (l) => ({ ...l, border: { ...l.border, color: v } }), `tbc-${layer.id}`)} />
      <div className="table-editor" style={{ gridTemplateColumns: `repeat(${cols}, minmax(60px, 1fr))` }} data-testid="design-table-editor">
        {Array.from({ length: rows }).flatMap((_, r) => Array.from({ length: cols }).map((__, c) => {
          const x = at(r, c)
          if (!x) return <div key={`${r}-${c}`} className="cell-merged" />
          return (
            <textarea key={`${r}-${c}`} rows={1} value={x.text} className={`cell-input ${cellKey === `${r}-${c}` ? 'on' : ''}`}
              style={{ fontWeight: x.weight >= 600 ? 700 : 400, textAlign: x.align, background: x.fill ?? undefined, gridColumn: `span ${x.colSpan}` }}
              onFocus={() => setCellKey(`${r}-${c}`)} onKeyDown={(e) => e.stopPropagation()}
              onChange={(e) => st.patchLayer<TableLayer>(layer.id, (l) => ({ ...l, cells: l.cells.map((y) => (y.row === r && y.col === c ? { ...y, text: e.target.value } : y)) }), `cell-${layer.id}-${r}-${c}`)} />
          )
        }))}
      </div>
      <div className="row-gap wrap small">
        <button className="link-btn" onClick={addRow}>+ Row</button>
        <button className="link-btn" onClick={addCol}>+ Column</button>
        <button className="link-btn" disabled={rows <= 1} onClick={() => dropLast('row')}>− Last row</button>
        <button className="link-btn" disabled={cols <= 1} onClick={() => dropLast('col')}>− Last column</button>
      </div>
      {cell && (
        <div className="stack">
          <div className="muted small">Cell {cell.row + 1}, {cell.col + 1}</div>
          <div className="row-gap">
            <Toggle label="Bold" checked={cell.weight >= 600} onChange={(v) => setCell({ weight: nearestWeight(familyInfo(fonts, layer.style.family), v ? 700 : 400, cell.italic) })} />
            <Toggle label="Italic" checked={cell.italic} onChange={(v) => setCell({ italic: v })} />
          </div>
          <Segmented label="Alignment" value={cell.align} onChange={(v) => setCell({ align: v })}
            options={[{ value: 'left', label: 'Left' }, { value: 'center', label: 'Centre' }, { value: 'right', label: 'Right' }]} />
          <ColorField label="Cell fill" value={cell.fill} allowNone onChange={(v) => setCell({ fill: v }, `cf-${cellKey}`)} />
        </div>
      )}
    </Section>
  )
}

export function Inspector(): ReactElement {
  const scene = useDesign((s) => s.history?.present ?? null)
  const selection = useDesign((s) => s.selection)
  const st = useDesign.getState()
  const layer = selection.length === 1 ? scene?.layers.find((l) => l.id === selection[0]) : undefined
  if (!scene) return <div />
  if (!layer) {
    return (
      <div className="inspector-empty muted">
        {selection.length > 1 ? `${selection.length} layers selected. Drag to move them together, or use the layer buttons.` :
          'Click a text, shape or picture to edit it. Double-click text to type in place.'}
      </div>
    )
  }
  const [x, y, w, h] = layer.box
  const setBox = (i: number, v: number | null) => {
    if (v === null) return
    const b = [...layer.box] as Box
    b[i] = v
    st.patchLayer<Layer>(layer.id, { box: b }, `box-${layer.id}-${i}`)
  }
  return (
    <div className="inspector" data-testid="design-inspector">
      <Section title={layer.name} aside={<span className="badge">{layer.type}</span>}>
        <div className="grid-4">
          <NumberField label="X" value={Math.round(x * 10) / 10} onChange={(v) => setBox(0, v)} testId="design-x" />
          <NumberField label="Y" value={Math.round(y * 10) / 10} onChange={(v) => setBox(1, v)} testId="design-y" />
          <NumberField label="W" value={Math.round(w * 10) / 10} min={1} onChange={(v) => setBox(2, v)} testId="design-w" />
          <NumberField label="H" value={Math.round(h * 10) / 10} min={1} onChange={(v) => setBox(3, v)} testId="design-h" />
        </div>
        <div className="grid-2">
          <NumberField label="Rotation" value={Math.round(layer.rotation * 100) / 100} min={-360} max={360} suffix="°"
            onChange={(v) => v !== null && st.patchLayer<Layer>(layer.id, { rotation: v }, `rot-${layer.id}`)} />
          <NumberField label="Opacity" value={Math.round(layer.opacity * 100)} min={0} max={100} suffix="%" integer
            onChange={(v) => v !== null && st.patchLayer<Layer>(layer.id, { opacity: v / 100 }, `op-${layer.id}`)} />
        </div>
        <div className="row-gap">
          <Toggle label="Visible" checked={layer.visible} onChange={(v) => st.patchLayer<Layer>(layer.id, { visible: v })} />
          <Toggle label="Locked" checked={layer.locked} onChange={(v) => st.patchLayer<Layer>(layer.id, { locked: v })} />
        </div>
      </Section>
      {layer.type === 'text' && <TextProps layer={layer} />}
      {layer.type === 'shape' && <ShapeProps layer={layer} />}
      {layer.type === 'vector' && <VectorProps layer={layer} />}
      {layer.type === 'image' && <ImageProps layer={layer} />}
      {layer.type === 'table' && <TableProps layer={layer} />}
    </div>
  )
}

// ------------------------------------------------------------------ check
export function CheckPanel(): ReactElement {
  const scene = useDesign((s) => s.history?.present ?? null)
  const accuracy = useDesign((s) => s.accuracy)
  const stale = useDesign((s) => s.accuracy !== null && s.accuracyFor !== s.history?.present)
  const state = useDesign((s) => s.accuracyState)
  const st = useDesign.getState()
  if (!scene) return <div />
  const focus = (box: Box) => {
    const v = useView.getState()
    const el = document.querySelector('[data-testid="design-canvas"]') as HTMLElement | null
    if (!el) return
    const z = Math.min(4, Math.max(v.zoom, Math.min(el.clientWidth / (box[2] * 3), el.clientHeight / (box[3] * 3))))
    v.set({ zoom: z, x: el.clientWidth / 2 - (box[0] + box[2] / 2) * z, y: el.clientHeight / 2 - (box[1] + box[3] / 2) * z })
  }
  const lowLayers = scene.layers.filter((l): l is TextLayer => l.type === 'text' && (l.lowConfidence?.length ?? 0) > 0)
  const score = accuracy ? Math.round(accuracy.ssim * 1000) / 10 : null
  return (
    <div className="check-panel" data-testid="design-check">
      <Section title="Rebuilt vs original" aside={
        <button className="btn small" disabled={state === 'running'} onClick={() => void st.checkAccuracy()}>{state === 'running' ? <><span className="spinner" /> Checking</> : 'Check again'}</button>
      }>
        {accuracy ? (
          <>
            <div className={`score ${stale ? 'stale' : accuracy.ssim >= 0.98 && !accuracy.regions.length ? 'good' : accuracy.ssim >= 0.95 ? 'warn' : 'bad'}`}
              data-testid="design-score" data-stale={stale ? '1' : '0'}>
              {score}% similar {accuracy.regions.length ? `· ${accuracy.regions.length} area(s) differ` : '· no missing or extra marks'}
            </div>
            {stale && <p className="small warn-text" data-testid="design-score-stale">The design has changed since this check. Check again to compare the current layers.</p>}
            <p className="muted small">Structural similarity of the rebuilt design (drawn from its layers) to the straightened picture. Red boxes on the canvas mark areas where one side has marks and the other has none.</p>
            {accuracy.regions.slice(0, 8).map((r, i) => (
              <button key={i} className="link-btn" onClick={() => focus([r.x, r.y, r.w, r.h])}>Area {i + 1} at {r.x}, {r.y} ({r.pixels} px)</button>
            ))}
          </>
        ) : (
          <p className="muted small">{state === 'error' ? 'The check could not run (see the event log).' : state === 'running' ? 'Drawing the layers and comparing…' : 'Not checked yet.'}</p>
        )}
        <p className="muted small">Use Compare in the toolbar to slide between the original and the rebuilt design, or show the difference.</p>
      </Section>
      {(scene.unreadable?.length ?? 0) > 0 && (
        <Section title="Not read">
          <p className="muted small">These lines could not be read with the chosen languages, so they were left in the picture exactly as they are (not turned into text). Add their language under Reading options and analyse the picture again, or type them in a new text box.</p>
          {scene.unreadable!.map((u, i) => (
            <button key={i} className="low-row" data-testid="design-unreadable" onClick={() => focus(u.box)}>
              <span className="dot bad" /> Line at {Math.round(u.box[0])}, {Math.round(u.box[1])} <span className="muted small">({Math.round(u.box[2])} × {Math.round(u.box[3])} px)</span>
            </button>
          ))}
        </Section>
      )}
      {lowLayers.length > 0 && (
        <Section title="Words to check">
          {lowLayers.map((l) => (
            <button key={l.id} className="low-row" onClick={() => { st.select([l.id]); focus(l.box) }}>
              <span className="dot warn" /> {l.lowConfidence!.map((i) => l.words?.[i]?.text).filter(Boolean).join(', ')} <span className="muted small">in “{l.text.slice(0, 24)}”</span>
            </button>
          ))}
        </Section>
      )}
      {scene.notes.length > 0 && (
        <Section title="Notes">
          <ul className="notes">{scene.notes.map((n, i) => <li key={i}>{n}</li>)}</ul>
        </Section>
      )}
      <Section title="Known limits">
        <ul className="notes">{scene.limits.map((l) => <li key={l.id}>{l.text}</li>)}</ul>
        <p className="muted small">Anything the automation missed can be fixed by hand: edit or retype text, pick another font, delete a layer and draw a shape or text box in its place.</p>
      </Section>
    </div>
  )
}
