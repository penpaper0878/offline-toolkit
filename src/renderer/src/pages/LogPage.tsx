import { useEffect, useMemo, useState } from 'react'
import type { LogEntry, LogLevel } from '@shared/types'
import { otk } from '../lib/api'
import { useUi } from '../lib/ui-store'
import { Segmented } from '../components/controls'

const LEVELS: (LogLevel | 'all')[] = ['all', 'info', 'warn', 'error']

export function LogPage() {
  const [entries, setEntries] = useState<LogEntry[]>([])
  const [level, setLevel] = useState<LogLevel | 'all'>('all')
  const [query, setQuery] = useState('')
  const logsDir = useUi((s) => s.settingsState?.paths.logs)

  useEffect(() => {
    void otk().log.recent().then(setEntries)
    return otk().log.onEntry((e) => setEntries((cur) => [...cur.slice(-999), e]))
  }, [])

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase()
    return entries
      .filter((e) => level === 'all' || e.level === level || (level === 'info' && e.level === 'debug'))
      .filter((e) => !q || `${e.source} ${e.message}`.toLowerCase().includes(q))
      .reverse()
  }, [entries, level, query])

  return (
    <div className="simple-page">
      <header className="page-head">
        <h1>Event log</h1>
        <span className="spacer" />
        {logsDir && <button className="btn small" onClick={() => void otk().shell.openPath(logsDir)}>Open logs folder</button>}
      </header>
      <div className="toolbar">
        <Segmented value={level} onChange={setLevel} options={LEVELS.map((l) => ({ value: l, label: l === 'all' ? 'All' : l[0].toUpperCase() + l.slice(1) }))} />
        <input className="search" placeholder="Filter…" value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Filter the log" />
        <span className="muted small">{shown.length} of {entries.length} entries (this session; older days are in the logs folder)</span>
      </div>
      <div className="table-wrap">
        <table className="table log-table" data-testid="log-table">
          <thead><tr><th>Time</th><th>Level</th><th>Source</th><th>Message</th></tr></thead>
          <tbody>
            {shown.map((e, i) => (
              <tr key={`${e.ts}-${i}`} className={`lvl-${e.level}`}>
                <td className="mono small">{new Date(e.ts).toLocaleTimeString()}</td>
                <td><span className={`lvl ${e.level}`}>{e.level}</span></td>
                <td className="small">{e.source}</td>
                <td dir="auto">{e.message}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
