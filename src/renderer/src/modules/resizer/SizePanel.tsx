import type { FullResizerSettings } from '@shared/resizer-defaults'
import type { FitMode } from '@shared/types'
import { describeAxis, resolveSize, setDpi, setHeight, setUnit, setWidth, type SizeFields, tidy, type Unit } from '@shared/units'
import { NumberField, Section, Segmented, Toggle } from '../../components/controls'
import { Icon } from '../../components/Icon'
import { useResizer } from './store'

const DPI_CHIPS = [72, 96, 150, 200, 300, 600]

function fieldsOf(s: FullResizerSettings): SizeFields {
  return { width: s.width, height: s.height, unit: s.unit, dpi: s.dpi, sizeMode: s.sizeMode, lockAspect: s.lockAspect }
}

export function SizePanel() {
  const s = useResizer((st) => st.history.present.settings)
  const update = useResizer((st) => st.update)
  const selected = useResizer((st) => st.files.find((f) => f.id === st.selectedId))
  const f = fieldsOf(s)
  const aspect = s.width > 0 && s.height > 0 ? s.width / s.height : null
  const apply = (next: SizeFields, key: string) =>
    update({ width: next.width, height: next.height, unit: next.unit, dpi: next.dpi, sizeMode: next.sizeMode, lockAspect: next.lockAspect }, key)

  let resolved: ReturnType<typeof resolveSize> | null = null
  let resolveError: string | null = null
  try {
    resolved = resolveSize(s.width, s.height, s.unit, s.dpi, s.fitDpi)
  } catch (e) {
    resolveError = (e as Error).message
  }

  const srcAspect = selected?.probe ? selected.probe.width / selected.probe.height : null
  const physical = s.unit !== 'px'

  return (
    <Section title="Size" aside={resolved && (
      <span className="badge" data-testid="target-px">{resolved.width.px} × {resolved.height.px} px</span>
    )}>
      <div className="size-row">
        <NumberField label="Width" testId="width" value={s.width} integer={s.unit === 'px'} min={s.unit === 'px' ? 1 : 0.0001}
          step={s.unit === 'px' ? 1 : 0.1} onChange={(v) => v != null && apply(setWidth(f, v, aspect), 'width')} />
        <button className={`icon-btn lock ${s.lockAspect ? 'on' : ''}`} data-testid="lock-aspect"
          title={s.lockAspect ? 'Aspect ratio locked (click to unlock)' : 'Aspect ratio unlocked (click to lock)'}
          aria-pressed={s.lockAspect} onClick={() => update({ lockAspect: !s.lockAspect })}>
          <Icon name={s.lockAspect ? 'lock' : 'unlock'} />
        </button>
        <NumberField label="Height" testId="height" value={s.height} integer={s.unit === 'px'} min={s.unit === 'px' ? 1 : 0.0001}
          step={s.unit === 'px' ? 1 : 0.1} onChange={(v) => v != null && apply(setHeight(f, v, aspect), 'height')} />
      </div>
      <Segmented<Unit> label="Unit" testId="unit" value={s.unit} onChange={(u) => apply(setUnit(f, u), 'unit')}
        options={[{ value: 'px', label: 'px' }, { value: 'cm', label: 'cm' }, { value: 'mm', label: 'mm' }, { value: 'in', label: 'inch' }]} />
      <div className="dpi-row">
        <NumberField label="DPI" testId="dpi" value={s.dpi} min={72} max={1200} step={1}
          hint="Dots per inch, written into the file. 72–1200."
          onChange={(v) => v != null && v >= 72 && v <= 1200 && apply(setDpi(f, v), 'dpi')} />
        <div className="chips" aria-label="Common DPI values">
          {DPI_CHIPS.map((d) => (
            <button key={d} className={`chip ${s.dpi === d ? 'on' : ''}`} onClick={() => apply(setDpi(f, d), 'dpi')}>{d}</button>
          ))}
        </div>
      </div>
      <Segmented label="When DPI changes, keep" value={s.sizeMode}
        onChange={(m) => update({ sizeMode: m })}
        options={[
          { value: 'exactPixels', label: 'Exact pixels', title: 'The pixel size stays; the physical size follows the DPI.' },
          { value: 'exactPhysical', label: 'Exact physical size', title: 'The cm/mm/inch size stays; pixels are recalculated.' }
        ]} />
      {physical && (
        <Toggle label="Store the DPI that makes the physical size exact" checked={s.fitDpi} onChange={(v) => update({ fitDpi: v })}
          hint="Pixels are whole numbers, so 3 cm at 200 DPI is 236 px (2.997 cm). This stores a density like 199.81 DPI so the printed size is exactly 3 cm. JPEG's JFIF header still rounds to whole DPI; EXIF keeps the exact value." />
      )}
      <div className="conversion" data-testid="conversion" aria-live="polite">
        {resolved ? (
          <>
            <div>Width: {describeAxis(resolved.width)}</div>
            <div>Height: {describeAxis(resolved.height)}</div>
            {physical && s.fitDpi && <div className="muted">Stored DPI: {tidy(resolved.width.dpi, 'cm')} × {tidy(resolved.height.dpi, 'cm')}</div>}
          </>
        ) : (
          <div className="error-text">{resolveError}</div>
        )}
      </div>
      {srcAspect && (
        <button className="link-btn" onClick={() => {
          const h = tidy(s.width / srcAspect, s.unit)
          update({ height: s.unit === 'px' ? Math.max(1, Math.round(h)) : h }, 'height')
        }}>
          Use the image’s proportions ({selected!.probe!.width} × {selected!.probe!.height})
        </button>
      )}

      <Segmented<FitMode> label="Fit" testId="fit" value={s.fit} onChange={(fit) => {
        update({ fit })
        useResizer.getState().setView(fit === 'crop' ? 'crop' : 'compare')
      }}
        options={[
          { value: 'crop', label: 'Crop to fill', title: 'Fill the size exactly; drag the crop window to choose what stays.' },
          { value: 'pad', label: 'Fit with padding', title: 'Show the whole image; fill the rest with a colour.' },
          { value: 'stretch', label: 'Stretch', title: 'Change the proportions to fill the size.' }
        ]} />
      {(s.fit === 'pad' || s.format === 'jpeg') && (
        <label className="field">
          <span className="field-label">{s.fit === 'pad' ? 'Padding colour' : 'Background for transparent areas'}</span>
          <span className="color-row">
            <input type="color" value={s.padColor.slice(0, 7)} onChange={(e) => update({ padColor: e.target.value.toUpperCase() }, 'padColor')} />
            <input className="hex" value={s.padColor} maxLength={9} data-testid="pad-color"
              onChange={(e) => /^#([0-9a-fA-F]{6}|[0-9a-fA-F]{8})$/.test(e.target.value) && update({ padColor: e.target.value.toUpperCase() }, 'padColor')} />
            {s.fit === 'pad' && s.format !== 'jpeg' && (
              <button className="chip" onClick={() => update({ padColor: s.padColor.slice(0, 7) + '00' })} title="Transparent padding (PNG/WEBP)">Transparent</button>
            )}
          </span>
        </label>
      )}
    </Section>
  )
}
