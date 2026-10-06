import { useEffect, useState } from 'react'
import type { AppInfo, ConverterCatalog, FullSelfTestReport, SelfTestReport, Theme } from '@shared/types'
import { newJobId, otk } from '../lib/api'
import { updateAppSettings, useUi } from '../lib/ui-store'
import { Section, Segmented, Toggle } from '../components/controls'
import { Icon } from '../components/Icon'

const ENGINE_LABEL: Record<string, string> = {
  soffice: 'LibreOffice', pandoc: 'Pandoc', gs: 'Ghostscript', tesseract: 'Tesseract OCR', java: 'Java (for veraPDF)',
  resvg: 'resvg', verapdf: 'veraPDF'
}

const MODULE_LABEL = { resizer: 'Image Resizer', converter: 'Document Converter', design: 'Image to Design', passport: 'Passport Photo' }

/** Every module does a small real job with the network blocked (about 10–30 s). */
function FullSelfTest() {
  const [report, setReport] = useState<FullSelfTestReport | null>(null)
  const [job, setJob] = useState<{ id: string; fraction: number; message: string } | null>(null)
  const ui = useUi.getState()
  useEffect(() => otk().jobs.onProgress((p) => setJob((j) => (j && p.jobId === j.id ? { ...j, fraction: p.fraction, message: p.message } : j))), [])
  const run = async () => {
    const id = newJobId('selftest')
    setJob({ id, fraction: 0, message: 'Network checks' })
    setReport(null)
    try {
      setReport(await otk().selftest.full(id))
    } catch (e) {
      ui.reportError('The full self-test could not run', e)
    } finally {
      setJob(null)
    }
  }
  const groups = report ? (['resizer', 'converter', 'design', 'passport'] as const).map((m) => [m, report.modules.filter((c) => c.module === m)] as const) : []
  return (
    <div className="full-selftest">
      <div className="row">
        <button className="btn" disabled={job !== null} onClick={() => void run()} data-testid="run-full-selftest">
          <Icon name="check" size={16} /> {job ? 'Checking…' : 'Check every module'}
        </button>
        {job && <button className="btn small ghost" onClick={() => void otk().jobs.cancel(job.id)}>Cancel</button>}
        {report && (
          <span className={`status-chip ${report.passed ? 'good' : 'bad'}`} data-testid="full-selftest-result">
            <Icon name={report.passed ? 'check' : 'x'} size={14} /> {report.passed ? `All passed in ${report.seconds} s` : 'Something failed'}
          </span>
        )}
      </div>
      <p className="muted small">Makes a small file in every module with the network blocked: resizes a photo to a size limit, converts Word to a validated PDF/A, reads text from a picture, makes an EPUB, a PDF and a PNG, reads a poster into layers, enlarges a picture, finds a person and makes a passport photo.</p>
      {job && (
        <div className="progress-row" data-testid="full-selftest-progress">
          <div className="progress"><div className="progress-fill" style={{ width: `${Math.round(job.fraction * 100)}%` }} /></div>
          <span className="muted small">{job.message}</span>
        </div>
      )}
      {report && (
        <div className="selftest-groups" data-testid="full-selftest-checks">
          <h4>No network</h4>
          <ul className="checks">
            {[...report.network.checks, report.quiet].map((c) => (
              <li key={c.name} className={c.passed ? 'good' : 'bad'}><Icon name={c.passed ? 'check' : 'x'} size={14} /> <strong>{c.name}</strong>: <span dir="auto">{c.detail}</span></li>
            ))}
          </ul>
          {groups.map(([m, checks]) => (
            <div key={m}>
              <h4>{MODULE_LABEL[m]}</h4>
              <ul className="checks">
                {checks.map((c) => (
                  <li key={c.name} className={c.passed ? 'good' : 'bad'} data-testid="module-check" data-passed={c.passed ? '1' : '0'}>
                    <Icon name={c.passed ? 'check' : 'x'} size={14} /> <strong>{c.name}</strong>: <span dir="auto">{c.detail}</span> <span className="muted small">({c.seconds} s)</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </div>
  )
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
        <Section title="Home screen">
          <Segmented label="When the app starts, show" testId="start-page" value={s.home.startPage} onChange={(startPage) => void save({ home: { startPage } })}
            options={[{ value: 'home', label: 'The home screen' }, { value: 'last', label: 'Where I left off' }]} />
          <Toggle label="Keep a list of recent files and designs" checked={s.home.rememberRecent} testId="remember-recent"
            onChange={(v) => void save({ home: { rememberRecent: v } }).then(() => v ? undefined : otk().recent.clear())}
            hint="Kept in recent.json in the data folder. Turning this off clears the list." />
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
          <FullSelfTest />
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
