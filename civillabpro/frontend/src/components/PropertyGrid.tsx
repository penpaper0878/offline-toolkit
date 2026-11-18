import Switch from "@mui/material/Switch";
import Tooltip from "@mui/material/Tooltip";
import { useEffect, useState } from "react";
import type { SchemaProp } from "../api/types";
import { Unit } from "./Fx";

export type Values = Record<string, unknown>;

/** The non-null branch of an optional field, or the field itself. */
function core(p: SchemaProp): SchemaProp {
  return p.anyOf?.find((o) => o.type !== "null") ?? p;
}
export const isOptional = (p: SchemaProp) => !!p.anyOf?.some((o) => o.type === "null");
// A row shows when every condition holds; a condition is one value or a list of allowed values.
export const isVisible = (p: SchemaProp, values: Values) =>
  !p.show_if || Object.entries(p.show_if).every(([k, v]) => (Array.isArray(v) ? v.includes(values[k]) : values[k] === v));

/** Client-side check against the limits the schema declares; the server remains the authority. */
export function validateField(p: SchemaProp, value: unknown): string | null {
  const c = core(p);
  if (value === null || value === undefined || value === "") return isOptional(p) ? null : "Enter a value.";
  if (c.type === "number" || c.type === "integer") {
    if (typeof value !== "number" || !Number.isFinite(value)) return "Enter a number.";
    if (c.minimum !== undefined && value < c.minimum) return `Not less than ${c.minimum}.`;
    if (c.exclusiveMinimum !== undefined && value <= c.exclusiveMinimum) return `Greater than ${c.exclusiveMinimum}.`;
    if (c.maximum !== undefined && value > c.maximum) return `Not more than ${c.maximum}.`;
  }
  if (c.type === "string" && typeof value === "string") {
    if (c.minLength !== undefined && value.length < c.minLength) return "Enter a value.";
    if (c.maxLength !== undefined && value.length > c.maxLength) return `At most ${c.maxLength} characters.`;
  }
  return null;
}

export function validateAll(props: Record<string, SchemaProp>, values: Values): Record<string, string> {
  const errors: Record<string, string> = {};
  for (const [key, p] of Object.entries(props)) {
    if (!isVisible(p, values)) continue;
    const e = validateField(p, values[key]);
    if (e) errors[key] = e;
  }
  return errors;
}

const cell = "h-7 w-full px-1.5 bg-transparent border-0 outline-none text-[12.5px] text-[var(--clp-ink)] num focus:bg-[color-mix(in_srgb,var(--clp-accent)_9%,transparent)]";

function NumberCell({ id, value, onChange, placeholder, disabled }: { id: string; value: number | null; onChange: (v: number | null) => void; placeholder?: string; disabled?: boolean }) {
  // Text state lets a half-typed number ("12.", "-") stay on screen; the parsed value goes up on every valid keystroke.
  const [text, setText] = useState(value === null ? "" : String(value));
  const [focused, setFocused] = useState(false);
  useEffect(() => { if (!focused) setText(value === null ? "" : String(value)); }, [value, focused]);
  return (
    <input
      id={id}
      inputMode="decimal"
      disabled={disabled}
      value={text}
      placeholder={placeholder}
      onFocus={() => setFocused(true)}
      onBlur={() => setFocused(false)}
      onChange={(e) => {
        const t = e.target.value.replace(",", ".");
        setText(t);
        if (t.trim() === "") onChange(null);
        else if (/^-?\d*\.?\d+$/.test(t.trim())) onChange(Number(t));
        else onChange(Number.NaN);
      }}
      className={`${cell} text-right`}
    />
  );
}

interface Props { properties: Record<string, SchemaProp>; values: Values; errors: Record<string, string>; onChange: (key: string, value: unknown) => void; disabled?: boolean }

/** Two-column property grid generated from an element's input schema: grouped, with units, limits and conditional rows. */
export function PropertyGrid({ properties, values, errors, onChange, disabled }: Props) {
  const groups = new Map<string, [string, SchemaProp][]>();
  for (const [key, p] of Object.entries(properties)) {
    if (!isVisible(p, values)) continue;
    const g = p.group ?? "Input";
    groups.set(g, [...(groups.get(g) ?? []), [key, p]]);
  }
  return (
    <div className="text-[12.5px]" role="form" aria-label="Design inputs">
      {[...groups].map(([group, fields]) => (
        <fieldset key={group} className="m-0 p-0 border-0" disabled={disabled}>
          <legend className="w-full px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-[var(--clp-ink-2)] bg-[var(--clp-panel-2)] border-y border-[var(--clp-border)]">{group}</legend>
          {fields.map(([key, p]) => {
            const c = core(p);
            const value = values[key];
            const error = errors[key];
            const id = `pg-${key}`;
            const options = c.enum;
            let control;
            if (c.type === "boolean") {
              control = <div className="flex justify-end pr-1"><Switch id={id} size="small" checked={!!value} onChange={(e) => onChange(key, e.target.checked)} /></div>;
            } else if (options) {
              control = (
                <select id={id} value={value === null || value === undefined ? "" : String(value)} onChange={(e) => {
                  const raw = e.target.value;
                  onChange(key, raw === "" ? null : typeof options[0] === "number" ? Number(raw) : raw);
                }} className={`${cell} cursor-pointer`}>
                  {isOptional(p) && <option value="">Auto</option>}
                  {options.map((o) => <option key={String(o)} value={String(o)}>{p.labels?.[String(o)] ?? String(o)}</option>)}
                </select>
              );
            } else if (c.type === "number" || c.type === "integer") {
              control = <NumberCell id={id} value={typeof value === "number" ? value : null} onChange={(v) => onChange(key, v)} placeholder={isOptional(p) ? "auto" : undefined} disabled={disabled} />;
            } else {
              control = <input id={id} value={typeof value === "string" ? value : ""} onChange={(e) => onChange(key, e.target.value)} className={cell} />;
            }
            return (
              <div key={key} className={`grid grid-cols-[minmax(0,1fr)_136px_46px] items-center border-b border-[var(--clp-border)] ${error ? "bg-[color-mix(in_srgb,var(--clp-bad)_8%,transparent)]" : ""}`}>
                <Tooltip title={p.description ?? ""} placement="left">
                  <label htmlFor={id} className="px-2.5 py-1 truncate">{p.title ?? key}</label>
                </Tooltip>
                <div className="border-l border-[var(--clp-border)]">{control}</div>
                <div className="px-1.5 text-[11px] text-[var(--clp-ink-3)] border-l border-[var(--clp-border)] h-7 flex items-center"><Unit>{p.unit ?? ""}</Unit></div>
                {error && <div className="col-span-3 px-2.5 pb-1 text-[11px] text-[var(--clp-bad)]" role="alert">{error}</div>}
              </div>
            );
          })}
        </fieldset>
      ))}
    </div>
  );
}
