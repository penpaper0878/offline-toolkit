import { type ReactNode, useEffect, useId, useRef, useState } from 'react'

/** Number input that keeps what you type ("3." or "") until it parses, then reports it. */
export function NumberField(props: {
  label: string
  value: number | null
  onChange: (v: number | null) => void
  min?: number
  max?: number
  step?: number
  integer?: boolean
  suffix?: ReactNode
  allowEmpty?: boolean
  width?: number
  disabled?: boolean
  testId?: string
  hint?: string
}) {
  const id = useId()
  const [text, setText] = useState(props.value == null ? '' : String(props.value))
  const focused = useRef(false)
  useEffect(() => {
    if (!focused.current) setText(props.value == null ? '' : String(props.value))
  }, [props.value])
  const parse = (t: string): number | null | undefined => {
    const clean = t.trim().replace(',', '.')
    if (clean === '') return props.allowEmpty ? null : undefined
    const n = Number(clean)
    if (!Number.isFinite(n)) return undefined
    if (props.integer && !Number.isInteger(n)) return undefined
    return n
  }
  const n = parse(text)
  const invalid = n === undefined || (n !== null && ((props.min !== undefined && n < props.min) || (props.max !== undefined && n > props.max)))
  return (
    <label className={`field ${invalid ? 'invalid' : ''}`} htmlFor={id} title={props.hint}>
      <span className="field-label">{props.label}</span>
      <span className="field-input">
        <input
          id={id}
          data-testid={props.testId}
          inputMode="decimal"
          value={text}
          disabled={props.disabled}
          style={props.width ? { width: props.width } : undefined}
          onFocus={() => (focused.current = true)}
          onBlur={() => {
            focused.current = false
            setText(props.value == null ? '' : String(props.value))
          }}
          onChange={(e) => {
            setText(e.target.value)
            const v = parse(e.target.value)
            if (v !== undefined) props.onChange(v)
          }}
          onKeyDown={(e) => {
            if (e.key !== 'ArrowUp' && e.key !== 'ArrowDown') return
            e.preventDefault()
            const cur = parse(text) ?? 0
            const step = (props.step ?? 1) * (e.shiftKey ? 10 : 1)
            let v = cur + (e.key === 'ArrowUp' ? step : -step)
            if (props.min !== undefined) v = Math.max(props.min, v)
            if (props.max !== undefined) v = Math.min(props.max, v)
            v = props.integer ? Math.round(v) : Math.round(v * 10000) / 10000
            setText(String(v))
            props.onChange(v)
          }}
        />
        {props.suffix && <span className="field-suffix">{props.suffix}</span>}
      </span>
    </label>
  )
}

export function Segmented<T extends string>(props: {
  label?: string
  value: T
  options: { value: T; label: ReactNode; title?: string }[]
  onChange: (v: T) => void
  testId?: string
}) {
  return (
    <div className="field">
      {props.label && <span className="field-label">{props.label}</span>}
      <div className="segmented" role="radiogroup" aria-label={props.label} data-testid={props.testId}>
        {props.options.map((o) => (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={props.value === o.value}
            className={props.value === o.value ? 'on' : ''}
            title={o.title}
            data-value={o.value}
            onClick={() => props.onChange(o.value)}
          >
            {o.label}
          </button>
        ))}
      </div>
    </div>
  )
}

export function Toggle(props: { label: ReactNode; checked: boolean; onChange: (v: boolean) => void; hint?: string; testId?: string; disabled?: boolean }) {
  return (
    <label className={`toggle ${props.disabled ? 'disabled' : ''}`} title={props.hint}>
      <input type="checkbox" checked={props.checked} disabled={props.disabled} data-testid={props.testId}
        onChange={(e) => props.onChange(e.target.checked)} />
      <span className="toggle-track" aria-hidden />
      <span className="toggle-label">{props.label}</span>
    </label>
  )
}

export function Select<T extends string>(props: { label?: string; value: T; options: { value: T; label: string }[]; onChange: (v: T) => void; testId?: string }) {
  const id = useId()
  return (
    <label className="field" htmlFor={id}>
      {props.label && <span className="field-label">{props.label}</span>}
      <select id={id} value={props.value} data-testid={props.testId} onChange={(e) => props.onChange(e.target.value as T)}>
        {props.options.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    </label>
  )
}

export function Section(props: { title: string; children: ReactNode; aside?: ReactNode }) {
  return (
    <section className="panel-section">
      <header>
        <h3>{props.title}</h3>
        {props.aside}
      </header>
      {props.children}
    </section>
  )
}

export function ProgressBar(props: { value: number; label?: string }) {
  const pct = Math.round(Math.max(0, Math.min(1, props.value)) * 100)
  return (
    <div className="progress" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label={props.label}>
      <div className="progress-fill" style={{ width: `${pct}%` }} />
    </div>
  )
}

export function Modal(props: { title: string; onClose?: () => void; children: ReactNode; footer?: ReactNode; wide?: boolean; testId?: string }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && props.onClose) props.onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [props.onClose])
  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && props.onClose?.()}>
      <div className={`modal ${props.wide ? 'wide' : ''}`} role="dialog" aria-modal="true" aria-label={props.title} data-testid={props.testId}>
        <header className="modal-head">
          <h2>{props.title}</h2>
          {props.onClose && <button className="icon-btn" aria-label="Close" onClick={props.onClose}>✕</button>}
        </header>
        <div className="modal-body">{props.children}</div>
        {props.footer && <footer className="modal-foot">{props.footer}</footer>}
      </div>
    </div>
  )
}
