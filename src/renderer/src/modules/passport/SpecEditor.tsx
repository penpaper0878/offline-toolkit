import { useState } from 'react'
import type { LengthUnit, PassportSpec, Range } from '@shared/passport'
import { Modal, NumberField, Segmented } from '../../components/controls'
import { useUi } from '../../lib/ui-store'
import { CUSTOM_ID, usePassport } from './store'

function slug(name: string): string {
  return (name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'my-photo').slice(0, 48)
}

function RangeFields({ label, value, onChange, unit, minOnly }: { label: string; value?: Range; onChange: (r?: Range) => void; unit: string; minOnly?: boolean }) {
  const on = value !== undefined
  return (
    <div className="row range-fields">
      <label className="toggle"><input type="checkbox" checked={on} onChange={(e) => onChange(e.target.checked ? { min: 0, ...(minOnly ? {} : { max: 0 }) } : undefined)} /> <span>{label}</span></label>
      {on && <NumberField label="from" value={value.min ?? null} allowEmpty step={0.5} suffix={unit} width={80} onChange={(v) => onChange({ ...value, min: v ?? undefined })} />}
      {on && !minOnly && <NumberField label="to" value={value.max ?? null} allowEmpty step={0.5} suffix={unit} width={80} onChange={(v) => onChange({ ...value, max: v ?? undefined })} />}
    </div>
  )
}

/** Edit the rules: use them for this photo only, save them as your own preset, or delete a preset. */
export function SpecEditor({ spec, onClose }: { spec: PassportSpec; onClose: () => void }) {
  const [s, setS] = useState<PassportSpec>(structuredClone(spec))
  const defaults = usePassport((x) => x.specDefaults)
  const specs = usePassport((x) => x.specs)
  const st = usePassport.getState()
  const u = s.unit
  const valid = s.width > 0 && s.height > 0 && s.head.min > 0 && s.head.max > s.head.min && s.head.max < s.height && s.dpi >= 72 && s.dpi <= 1200
  const existing = specs.some((x) => x.id === s.id)
  const save = async (asNew: boolean) => {
    const id = asNew || s.id === CUSTOM_ID ? uniqueId(slug(s.name)) : s.id
    const changed = JSON.stringify({ ...s, source: undefined }) !== JSON.stringify({ ...spec, source: undefined })
    const source = s.source.status === 'user' || changed ? { status: 'user' as const, checked: new Date().toISOString().slice(0, 10) } : s.source
    try {
      await st.saveSpec({ ...s, id, source })
      useUi.getState().toast('success', 'Preset saved', `"${s.name}" is in presets/passport-specs.json.`)
      onClose()
    } catch (e) {
      useUi.getState().reportError('The preset could not be saved', e)
    }
  }
  const uniqueId = (base: string): string => {
    let id = base, i = 2
    while (specs.some((x) => x.id === id)) id = `${base}-${i++}`
    return id
  }
  return (
    <Modal title="Photo rules" onClose={onClose} wide testId="passport-spec-editor" footer={
      <>
        {existing && s.id !== CUSTOM_ID && <button className="btn danger" onClick={() => {
          if (!window.confirm(`Delete the preset "${spec.name}"?${defaults.includes(spec.id) ? ' It is one of the presets that came with the app; it will not come back with updates.' : ''}`)) return
          void st.removeSpec(spec.id).then(onClose, (e) => useUi.getState().reportError('The preset could not be deleted', e))
        }}>Delete preset</button>}
        <span className="spacer" />
        <button className="btn" disabled={!valid} onClick={() => { st.update({ specId: CUSTOM_ID, customSpec: { ...s, id: CUSTOM_ID, source: { status: 'user' } }, place: null }); onClose() }}
          data-testid="passport-spec-use">Use for this photo</button>
        {existing && s.id !== CUSTOM_ID && <button className="btn" disabled={!valid} onClick={() => void save(false)}>Save changes</button>}
        <button className="btn primary" disabled={!valid} onClick={() => void save(true)} data-testid="passport-spec-save">Save as new preset</button>
      </>
    }>
      <div className="spec-editor">
        <label className="field"><span className="field-label">Name</span>
          <input value={s.name} maxLength={120} onChange={(e) => setS({ ...s, name: e.target.value })} data-testid="passport-spec-name" /></label>
        <div className="row">
          <NumberField label="Width" value={s.width} min={1} step={0.5} width={90} onChange={(v) => v && setS({ ...s, width: v })} testId="passport-spec-width" />
          <NumberField label="Height" value={s.height} min={1} step={0.5} width={90} onChange={(v) => v && setS({ ...s, height: v })} testId="passport-spec-height" />
          <Segmented label="Unit" value={u} onChange={(unit: LengthUnit) => setS({ ...s, unit })} options={[{ value: 'mm', label: 'mm' }, { value: 'cm', label: 'cm' }, { value: 'in', label: 'in' }]} />
          <NumberField label="DPI" value={s.dpi} min={72} max={1200} integer width={80} onChange={(v) => v && setS({ ...s, dpi: v })} testId="passport-spec-dpi" />
        </div>
        <div className="row">
          <NumberField label="Head from" value={s.head.min} min={0.1} step={0.5} suffix={u} width={90} onChange={(v) => v && setS({ ...s, head: { ...s.head, min: v } })} />
          <NumberField label="to" value={s.head.max} min={0.1} step={0.5} suffix={u} width={90} onChange={(v) => v && setS({ ...s, head: { ...s.head, max: v } })} />
          <Segmented label="Measured from the chin to" value={s.head.crown} onChange={(crown) => setS({ ...s, head: { ...s.head, crown } })}
            options={[{ value: 'hair', label: 'top of the hair' }, { value: 'skull', label: 'top of the head' }]} />
        </div>
        <RangeFields label="Eye line above the bottom" value={s.eyeLine} unit={u} onChange={(eyeLine) => setS({ ...s, eyeLine })} />
        <RangeFields label="Space above the head" value={s.topMargin} unit={u} onChange={(topMargin) => setS({ ...s, topMargin })} />
        <RangeFields label="Space below the chin, at least" value={s.bottomMargin} unit={u} minOnly onChange={(bottomMargin) => setS({ ...s, bottomMargin })} />
        <label className="field"><span className="field-label">Notes</span>
          <textarea rows={3} maxLength={2000} value={s.notes ?? ''} onChange={(e) => setS({ ...s, notes: e.target.value || undefined })} /></label>
        {!valid && <p className="bad-text small">Check the numbers: the head range must fit inside the photo height, and the DPI must be 72–1200.</p>}
        <p className="muted small">Presets are kept in presets/passport-specs.json in the app&apos;s data folder; you can also edit that file.</p>
      </div>
    </Modal>
  )
}
