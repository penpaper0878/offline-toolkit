import { Fragment, type ReactNode } from "react";

const GREEK: Record<string, string> = { tau: "τ", gamma: "γ", eps: "ε", alpha: "α" };
// base_subscript, with optional primes: f_ck, x_u,max, d_b', tau_c,max
const TOKEN = /\b(tau|gamma|eps|[A-Za-z]+)('?)_([A-Za-z0-9]+(?:,[A-Za-z0-9]+)*)('?)|\^(\d+(?:\.\d+)?|[A-Za-z]+_[A-Za-z0-9]+)|\b(mm|m)([23])\b|\bgamma\b|sqrt|<=|>=| x /g;

/**
 * Renders calculation-sheet markup: subscripts, powers, Greek letters and maths signs.
 * With ``prose`` (titles, notes) " x " and "sqrt" stay words: "about the x axis" is not a product.
 */
export function fxNodes(text: string, prose = false): ReactNode[] {
  const out: ReactNode[] = [];
  let last = 0;
  let k = 0;
  for (const m of text.matchAll(TOKEN)) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const [all, base, p1, sub, p2, pow, unit, unitPow] = m;
    if (base) out.push(<Fragment key={k++}>{GREEK[base] ?? base}{p1}<sub>{sub}</sub>{p2}</Fragment>);
    else if (pow) {
      const [pb, ps] = pow.split("_"); // ^alpha_n: a symbol with its own subscript as the power
      out.push(<sup key={k++}>{ps === undefined ? pb : <>{GREEK[pb] ?? pb}<sub>{ps}</sub></>}</sup>);
    }
    else if (unit) out.push(<Fragment key={k++}>{unit}<sup>{unitPow}</sup></Fragment>);
    else if (all === "gamma") out.push("γ");
    else if (all === "sqrt") out.push(prose ? "sqrt" : "√");
    else if (all === "<=") out.push("≤");
    else if (all === ">=") out.push("≥");
    else out.push(prose ? " x " : " × ");
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

/** Titles and notes: symbols rendered, upright type, words left as words. */
export function Prose({ children }: { children: string }) {
  return <span>{fxNodes(children, true)}</span>;
}
