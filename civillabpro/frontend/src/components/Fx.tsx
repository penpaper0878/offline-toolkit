import { Fragment, type ReactNode } from "react";

const GREEK: Record<string, string> = { tau: "τ", gamma: "γ", eps: "ε" };
// base_subscript, with optional primes: f_ck, x_u,max, d_b', tau_c,max
const TOKEN = /\b(tau|gamma|eps|[A-Za-z]+)('?)_([A-Za-z0-9]+(?:,[A-Za-z0-9]+)*)('?)|\^(\d+)|\b(mm|m)([23])\b|\bgamma\b|sqrt|<=|>=| x /g;

/** Renders calculation-sheet markup: subscripts, powers, Greek letters and maths signs. */
export function fxNodes(text: string): ReactNode[] {
  const out: ReactNode[] = [];
  let last = 0;
  let k = 0;
  for (const m of text.matchAll(TOKEN)) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const [all, base, p1, sub, p2, pow, unit, unitPow] = m;
    if (base) out.push(<Fragment key={k++}>{GREEK[base] ?? base}{p1}<sub>{sub}</sub>{p2}</Fragment>);
    else if (pow) out.push(<sup key={k++}>{pow}</sup>);
    else if (unit) out.push(<Fragment key={k++}>{unit}<sup>{unitPow}</sup></Fragment>);
    else if (all === "gamma") out.push("γ");
    else if (all === "sqrt") out.push("√");
    else if (all === "<=") out.push("≤");
    else if (all === ">=") out.push("≥");
    else out.push(" × ");
    last = m.index + all.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

export function Fx({ children, className = "" }: { children: string; className?: string }) {
  return <span className={`fx ${className}`}>{fxNodes(children)}</span>;
}

/** Units and plain labels: same markup, upright type. */
export function Unit({ children }: { children: string }) {
  return <span>{fxNodes(children)}</span>;
}
