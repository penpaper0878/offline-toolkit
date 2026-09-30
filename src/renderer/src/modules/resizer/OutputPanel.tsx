import type { OutputFormat, SizeRange } from '@shared/types'
import { otk } from '../../lib/api'
import { useUi } from '../../lib/ui-store'
import { NumberField, Section, Segmented, Select, Toggle } from '../../components/controls'
import { useResizer } from './store'

export function OutputPanel() {
  const s = useResizer((st) => st.history.present.settings)
  const update = useResizer((st) => st.update)
  const outputDir = useResizer((st) => st.outputDir)
  const zip = useResizer((st) => st.zip)
  const base = useUi((st) => st.settings?.sizeUnitBase ?? 1024)
  const range = s.sizeRange
  const setRange = (patch: Partial<SizeRange> | null, key?: string) =>
    update({ sizeRange: patch === null ? null : { unit: 'KB', ...(range ?? {}), ...patch } as SizeRange }, key)

  return (
    <>
      <Section title="Format and file size">
        <Segmented<OutputFormat> label="Format" testId="format" value={s.format} onChange={(format) => update({ format })}
          options={[{ value: 'jpeg', label: 'JPG' }, { value: 'png', label: 'PNG' }, { value: 'webp', label: 'WEBP' }]} />
        <Toggle label="Target file size" testId="target-size" checked={!!range}
          onChange={(on) => setRange(on ? { min: null, max: 50, unit: 'KB' } : null)} />
        {range && (
          <div className="range-row">
            <NumberField label="Min" testId="size-min" value={range.min ?? null} allowEmpty min={0} step={1}
              onChange={(v) => setRange({ min: v }, 'min')} />
            <span className="range-dash">–</span>
            <NumberField label="Max" testId="size-max" value={range.max ?? null} allowEmpty min={0.001} step={1}
              onChange={(v) => setRange({ max: v }, 'max')} />
            <Segmented value={range.unit} onChange={(unit) => setRange({ unit })}
              options={[{ value: 'KB', label: 'KB' }, { value: 'MB', label: 'MB' }]} />
          </div>
        )}
        {range && (
          <p className="muted small">
            1 KB = {base} bytes (change in Settings). Dimensions never change to meet the size: the app tells you if the range can’t be reached.
          </p>
        )}
        {(!range || range.max == null) && s.format !== 'png' && (
          <label className="field">
            <span className="field-label">Quality {range ? '(lower bound for the search)' : ''}: {s.quality}</span>
            <input type="range" min={1} max={100} value={s.quality} data-testid="quality"
              onChange={(e) => update({ quality: Number(e.target.value) }, 'quality')} />
          </label>
        )}
        <details className="advanced">
          <summary>Advanced</summary>
          {s.format === 'jpeg' && (
            <Select label="Chroma subsampling" value={s.subsampling} onChange={(v) => update({ subsampling: v })}
              options={[{ value: 'auto', label: 'Auto (best-looking that fits)' }, { value: '4:4:4', label: '4:4:4 (sharp colour edges)' }, { value: '4:2:0', label: '4:2:0 (smaller)' }]} />
          )}
          {s.format === 'webp' && (
            <Select label="WEBP lossless" value={s.webpLossless} onChange={(v) => update({ webpLossless: v })}
              options={[{ value: 'auto', label: 'Use lossless when it fits' }, { value: 'never', label: 'Always lossy' }]} />
          )}
          {s.format === 'png' && (
            <Toggle label="Allow colour reduction to fit the maximum (lossy)" checked={s.allowQuantize} onChange={(v) => update({ allowQuantize: v })}
              hint="PNG is lossless. If the file is too big, this lets the app reduce it to a palette of up to 256 colours." />
          )}
          <Toggle label="Pad to minimum size (pixels unchanged)" testId="allow-padding" checked={s.allowPadding}
            onChange={(v) => update({ allowPadding: v })}
            hint="If even the best quality is smaller than the minimum, add a harmless comment block so the file reaches it. Some upload forms reject files below a minimum size." />
          <Toggle label="Save the closest result even if the range can’t be met" checked={s.saveOutOfRange}
            onChange={(v) => update({ saveOutOfRange: v })} />
        </details>
      </Section>

      <Section title="Metadata">
        <Toggle label="Strip metadata (camera, GPS, comments)" testId="strip" checked={s.stripMetadata}
          onChange={(v) => update({ stripMetadata: v })}
          hint="DPI is always written. EXIF orientation is always applied to the pixels and reset to 'normal'." />
      </Section>

      <Section title="Save to">
        <div className="path-row">
          <span className="path" dir="auto" title={outputDir ?? ''} data-testid="output-dir">{outputDir ?? 'Ask when processing'}</span>
          <button className="btn small" onClick={async () => {
            const dir = await otk().dialogs.chooseDir(outputDir)
            if (dir) useResizer.getState().setOutputDir(dir)
          }}>Choose…</button>
        </div>
        <label className="field">
          <span className="field-label">File name pattern</span>
          <input value={s.naming} data-testid="naming" onChange={(e) => update({ naming: e.target.value }, 'naming')} />
          <span className="muted small">Tokens: {'{name} {w} {h} {dpi} {n}'}. Existing files are never overwritten.</span>
        </label>
        <Toggle label="Also create a ZIP of all results" testId="zip" checked={zip} onChange={(v) => useResizer.getState().setZip(v)} />
      </Section>
    </>
  )
}
