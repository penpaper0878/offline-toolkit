import { useState } from 'react'
import { toStoredSettings, withDefaults } from '@shared/resizer-defaults'
import type { Preset } from '@shared/types'
import { otk } from '../../lib/api'
import { useUi } from '../../lib/ui-store'
import { Modal } from '../../components/controls'
import { useResizer } from './store'

function same(a: Preset['settings'], b: Preset['settings']): boolean {
  return JSON.stringify(toStoredSettings(withDefaults(a))) === JSON.stringify(toStoredSettings(withDefaults(b)))
}

function slug(name: string): string {
  const base = name.toLowerCase().normalize('NFKD').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 40) || 'preset'
  return `${base}-${Date.now().toString(36)}`
}

export function PresetBar() {
  const presets = useResizer((s) => s.presets)
  const presetId = useResizer((s) => s.presetId)
  const settings = useResizer((s) => s.history.present.settings)
  const [manage, setManage] = useState(false)
  const [naming, setNaming] = useState<null | { mode: 'new' | 'rename'; name: string }>(null)
  const ui = useUi.getState()
  const current = presets?.presets.find((p) => p.id === presetId) ?? null
  const modified = current ? !same(current.settings, toStoredSettings(settings)) : false

  const saveNew = async (name: string) => {
    const preset: Preset = { id: slug(name), name, settings: toStoredSettings(settings) }
    try {
      useResizer.getState().setPresets(await otk().presets.save(preset))
      useResizer.setState({ presetId: preset.id })
      ui.toast('success', 'Preset saved', name)
    } catch (e) {
      ui.reportError('Could not save the preset', e)
    }
  }

  const updateCurrent = async () => {
    if (!current) return
    try {
      useResizer.getState().setPresets(await otk().presets.save({ ...current, settings: toStoredSettings(settings) }))
      ui.toast('success', 'Preset updated', current.name)
    } catch (e) {
      ui.reportError('Could not update the preset', e)
    }
  }

  return (
    <div className="preset-bar">
      <label className="preset-select">
        <span className="sr-only">Preset</span>
        <select data-testid="preset-select" value={presetId ?? ''} onChange={(e) => {
          const p = presets?.presets.find((x) => x.id === e.target.value)
          if (p) useResizer.getState().applyPreset(p)
        }}>
          <option value="" disabled>Choose a preset…</option>
          {presets?.presets.map((p) => (
            <option key={p.id} value={p.id}>{p.name}{p.id === presetId && modified ? ' (modified)' : ''}</option>
          ))}
        </select>
      </label>
      {current && modified && <button className="btn small" onClick={updateCurrent} title="Save the current settings into this preset">Update</button>}
      <button className="btn small" onClick={() => setNaming({ mode: 'new', name: '' })} data-testid="preset-save-as">Save as…</button>
      <button className="btn small ghost" onClick={() => setManage(true)}>Manage…</button>

      {naming && (
        <Modal title="Save preset" onClose={() => setNaming(null)} footer={
          <>
            <button className="btn ghost" onClick={() => setNaming(null)}>Cancel</button>
            <button className="btn primary" disabled={!naming.name.trim()} data-testid="preset-name-ok"
              onClick={() => { void saveNew(naming.name.trim()); setNaming(null) }}>Save</button>
          </>
        }>
          <label className="field">
            <span className="field-label">Name</span>
            <input autoFocus dir="auto" value={naming.name} data-testid="preset-name" maxLength={120}
              onChange={(e) => setNaming({ ...naming, name: e.target.value })}
              onKeyDown={(e) => { if (e.key === 'Enter' && naming.name.trim()) { void saveNew(naming.name.trim()); setNaming(null) } }} />
          </label>
        </Modal>
      )}
      {manage && <PresetManager onClose={() => setManage(false)} />}
    </div>
  )
}

function PresetManager({ onClose }: { onClose: () => void }) {
  const presets = useResizer((s) => s.presets)
  const [editing, setEditing] = useState<{ id: string; name: string; description: string } | null>(null)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const ui = useUi.getState()
  const setPresets = useResizer.getState().setPresets

  const run = async (title: string, fn: () => Promise<void>) => {
    try {
      await fn()
    } catch (e) {
      ui.reportError(title, e)
    }
  }

  return (
    <Modal title="Presets" wide onClose={onClose} testId="preset-manager" footer={
      <>
        <button className="btn ghost" onClick={() => run('Import failed', async () => {
          const r = await otk().presets.importFile()
          if (r) {
            setPresets(r.state)
            ui.toast('success', `Imported ${r.imported} preset(s)`)
          }
        })}>Import…</button>
        <button className="btn ghost" onClick={() => run('Export failed', async () => {
          const path = await otk().presets.exportFile([...selected])
          if (path) ui.toast('success', `Exported ${selected.size || 'all'} preset(s)`, path)
        })}>Export {selected.size ? `${selected.size} selected` : 'all'}…</button>
        <span className="spacer" />
        <button className="btn primary" onClick={onClose}>Done</button>
      </>
    }>
      <p className="muted small">
        Presets are stored as editable JSON in your data folder ({'presets/resizer.json'}). Changes you make there are picked up on the next start.
      </p>
      <table className="table">
        <thead>
          <tr><th /><th>Name</th><th>Size</th><th>Format</th><th>File size</th><th /></tr>
        </thead>
        <tbody>
          {presets?.presets.map((p) => {
            const s = p.settings
            const r = s.sizeRange
            return (
              <tr key={p.id}>
                <td><input type="checkbox" aria-label={`Select ${p.name}`} checked={selected.has(p.id)} onChange={(e) => {
                  const next = new Set(selected)
                  if (e.target.checked) next.add(p.id)
                  else next.delete(p.id)
                  setSelected(next)
                }} /></td>
                <td dir="auto">
                  {editing?.id === p.id ? (
                    <div className="stack">
                      <input value={editing.name} onChange={(e) => setEditing({ ...editing, name: e.target.value })} />
                      <input placeholder="Description" value={editing.description} onChange={(e) => setEditing({ ...editing, description: e.target.value })} />
                    </div>
                  ) : (
                    <>
                      <strong>{p.name}</strong>
                      {p.description && <div className="muted small">{p.description}</div>}
                    </>
                  )}
                </td>
                <td>{s.width} × {s.height} {s.unit} @ {s.dpi} DPI · {s.fit}</td>
                <td>{s.format.toUpperCase()}</td>
                <td>{r ? `${r.min ?? 0}–${r.max ?? '∞'} ${r.unit}` : '—'}</td>
                <td className="row-actions">
                  {editing?.id === p.id ? (
                    <>
                      <button className="btn small" disabled={!editing.name.trim()} onClick={() => run('Rename failed', async () => {
                        setPresets(await otk().presets.save({ ...p, name: editing.name.trim(), description: editing.description.trim() || undefined }))
                        setEditing(null)
                      })}>Save</button>
                      <button className="btn small ghost" onClick={() => setEditing(null)}>Cancel</button>
                    </>
                  ) : (
                    <>
                      <button className="btn small ghost" onClick={() => useResizer.getState().applyPreset(p)}>Apply</button>
                      <button className="btn small ghost" onClick={() => setEditing({ id: p.id, name: p.name, description: p.description ?? '' })}>Rename</button>
                      <button className="btn small danger" onClick={() => {
                        if (window.confirm(`Delete the preset “${p.name}”?`)) void run('Delete failed', async () => setPresets(await otk().presets.remove(p.id)))
                      }}>Delete</button>
                    </>
                  )}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </Modal>
  )
}
