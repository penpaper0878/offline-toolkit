import { useEffect, useState } from 'react'
import type { AppInfo, ConverterCatalog, SelfTestReport, Theme } from '@shared/types'
import { otk } from '../lib/api'
import { updateAppSettings, useUi } from '../lib/ui-store'
import { Section, Segmented, Toggle } from '../components/controls'
import { Icon } from '../components/Icon'

const ENGINE_LABEL: Record<string, string> = {
  soffice: 'LibreOffice', pandoc: 'Pandoc', gs: 'Ghostscript', tesseract: 'Tesseract OCR', java: 'Java (for veraPDF)',
  resvg: 'resvg', verapdf: 'veraPDF'
}

export function SettingsPage() {
  const state = useUi((s) => s.settingsState)
  const [info, setInfo] = useState<AppInfo | null>(null)
  const [report, setReport] = useState<SelfTestReport | null>(null)
  const [testing, setTesting] = useState(false)
  const [catalog, setCatalog] = useState<ConverterCatalog | null>(null)
  const ui = useUi.getState()

  useEffect(() => {
    void otk().app.info().then(setInfo).catch((e) => ui.reportError('Could not read app info', e))
    void otk().converter.catalog().then(setCatalog).catch(() => undefined)
  }, [])

  if (!state) return null
  const s = state.settings
  const save = (patch: Parameters<typeof updateAppSettings>[0]) =>
    updateAppSettings(patch).catch((e) => ui.reportError('Could not save settings', e))

  return (
    <div className="simple-page settings-page">
      <header className="page-head"><h1>Settings</h1></header>
      {state.error && <p className="error-text">{state.error}</p>}
      <div className="settings-grid">
        <Section title="Appearance">
          <Segmented<Theme> label="Theme" testId="theme" value={s.theme} onChange={(theme) => void save({ theme })}
            options={[{ value: 'system', label: 'System' }, { value: 'light', label: 'Light' }, { value: 'dark', label: 'Dark' }]} />
        </Section>
        <Section title="File sizes">
          <Segmented label="1 KB equals" value={String(s.sizeUnitBase) as '1024' | '1000'}
            onChange={(v) => void save({ sizeUnitBase: Number(v) as 1000 | 1024 })}
            options={[{ value: '1024', label: '1024 bytes (as Windows shows)' }, { value: '1000', label: '1000 bytes' }]} />
        </Section>
        <Section title="Privacy">
          <Toggle label="Hide file paths in the event log" checked={s.logging.hashPaths}
            onChange={(v) => void save({ logging: { hashPaths: v } })}
            hint="Paths are replaced by short hashes in new log entries." />
        </Section>
        <Section title="Offline self-test" aside={report && (
          <span className={`status-chip ${report.passed ? 'good' : 'bad'}`} data-testid="selftest-result">
            <Icon name={report.passed ? 'check' : 'x'} size={14} /> {report.passed ? 'Passed' : 'Failed'}
          </span>
        )}>
          <p className="muted small">Tries to reach example.com from every part of the app. It passes only if every attempt is blocked.</p>
          <button className="btn" disabled={testing} data-testid="run-selftest" onClick={async () => {
            setTesting(true)
            try {
              setReport(await otk().selftest.offline())
            } catch (e) {
              ui.reportError('Self-test could not run', e)
            } finally {
              setTesting(false)
            }
          }}><Icon name="shield" size={16} /> {testing ? 'Testing…' : 'Run offline self-test'}</button>
          {report && (
            <ul className="checks">
              {report.checks.map((c) => (
                <li key={c.name} className={c.passed ? 'good' : 'bad'}>
                  <Icon name={c.passed ? 'check' : 'x'} size={14} /> <strong>{c.name}</strong>: <span dir="auto">{c.detail}</span>
                </li>
              ))}
            </ul>
          )}
        </Section>
        <Section title="Your data">
          <p className="muted small">Settings and presets are plain JSON files you can edit. Invalid files are reported and never overwritten.</p>
          <dl className="facts">
            <div><dt>Data folder</dt><dd dir="auto">{state.paths.data}</dd></div>
            <div><dt>Settings</dt><dd dir="auto">{state.paths.settingsFile}</dd></div>
            <div><dt>Presets</dt><dd dir="auto">{state.paths.presetsFile}</dd></div>
          </dl>
          <button className="btn small" onClick={() => void otk().shell.openPath(state.paths.data)}>Open data folder</button>
        </Section>
        <Section title="Diagnostics">
          {info ? (
            <dl className="facts" data-testid="diagnostics">
              <div><dt>App</dt><dd>{info.version}{info.portable ? ' (portable)' : ''}</dd></div>
              <div><dt>Electron / Chromium / Node</dt><dd>{info.electron} / {info.chrome} / {info.node}</dd></div>
              <div><dt>Platform</dt><dd>{info.platform}</dd></div>
              <div><dt>Python used</dt><dd dir="auto" data-testid="python-path">{info.pythonPath}</dd></div>
              <div><dt>Python worker</dt><dd>{info.worker ? `Python ${String(info.worker.python)}, Pillow ${String(info.worker.pillow)}, HEIC ${info.worker.heif ? 'yes' : 'no'}, network guard ${info.worker.netguard ? 'on' : 'OFF'}` : <span className="error-text">{info.workerError}</span>}</dd></div>
            </dl>
          ) : <span className="spinner small" />}
        </Section>
        <Section title="Conversion engines">
          {catalog ? (
            <ul className="checks" data-testid="engines">
              {Object.entries(catalog.engines).map(([name, e]) => (
                <li key={name} className={e.available ? 'good' : 'bad'} data-engine={name} data-bundled={e.bundled ? 'yes' : 'no'}>
                  <Icon name={e.available ? 'check' : 'x'} size={14} /> <strong>{ENGINE_LABEL[name] ?? name}</strong>:{' '}
                  <span dir="auto">{e.available ? `${e.version ? `${e.version}, ` : ''}${e.bundled ? 'bundled' : 'from this computer'} (${e.path})` : 'missing'}</span>
                </li>
              ))}
              <li className={catalog.ocrLanguages.length ? 'good' : 'bad'}>
                <Icon name={catalog.ocrLanguages.length ? 'check' : 'x'} size={14} /> <strong>OCR languages</strong>:{' '}
                <span>{catalog.ocrLanguages.join(', ') || 'none'}</span>
              </li>
            </ul>
          ) : <span className="spinner small" />}
        </Section>
      </div>
    </div>
  )
}
