/**
 * Expression evaluator for the floating calculator.
 * A small recursive-descent parser: no eval, no Function. Angles are in degrees.
 *   expr   := term (('+' | '-') term)*
 *   term   := unary (('*' | '/' | '%') unary)*
 *   unary  := ('+' | '-') unary | power
 *   power  := atom ('^' unary)?
 *   atom   := number | name | name '(' args ')' | '(' expr ')'
 */

const RAD = Math.PI / 180;
const FUNCTIONS: Record<string, (...a: number[]) => number> = {
  sqrt: Math.sqrt, abs: Math.abs, ln: Math.log, log: Math.log10, exp: Math.exp, round: Math.round, floor: Math.floor, ceil: Math.ceil,
  sin: (x) => Math.sin(x * RAD), cos: (x) => Math.cos(x * RAD), tan: (x) => Math.tan(x * RAD),
  asin: (x) => Math.asin(x) / RAD, acos: (x) => Math.acos(x) / RAD, atan: (x) => Math.atan(x) / RAD,
  min: Math.min, max: Math.max,
  /** Area of n bars of diameter d (mm): bar(16) or bar(16, 3). */
  bar: (d, n = 1) => (n * Math.PI * d * d) / 4,
};
const CONSTANTS: Record<string, number> = { pi: Math.PI, e: Math.E };

export class CalcError extends Error {}

export function evaluate(input: string, variables: Record<string, number> = {}): number {
  const src = input.replace(/×/g, "*").replace(/÷/g, "/").replace(/,(?=\d{3}\b)/g, "");
  let i = 0;

  const peek = () => { while (src[i] === " ") i++; return src[i]; };
  const fail = (msg: string): never => { throw new CalcError(msg); };

  function expr(): number {
    let v = term();
    for (;;) {
      const c = peek();
      if (c === "+") { i++; v += term(); } else if (c === "-") { i++; v -= term(); } else return v;
    }
  }
  function term(): number {
    let v = unary();
    for (;;) {
      const c = peek();
      if (c === "*") { i++; v *= unary(); }
      else if (c === "/") { i++; const d = unary(); if (d === 0) fail("Division by zero"); v /= d; }
      else if (c === "%") { i++; v %= unary(); }
      else return v;
    }
  }
  function unary(): number {
    const c = peek();
    if (c === "-") { i++; return -unary(); }
    if (c === "+") { i++; return unary(); }
    return power();
  }
  function power(): number {
    const base = atom();
    if (peek() === "^") { i++; return Math.pow(base, unary()); }
    return base;
  }
  function atom(): number {
    const c = peek();
    if (c === undefined) fail("Incomplete expression");
    if (c === "(") { i++; const v = expr(); if (peek() !== ")") fail("Missing )"); i++; return v; }
    const num = /^\d*\.?\d+(?:[eE][+-]?\d+)?/.exec(src.slice(i));
    if (num) { i += num[0].length; return Number(num[0]); }
    const name = /^[A-Za-z_][A-Za-z0-9_]*/.exec(src.slice(i));
    if (name) {
      i += name[0].length;
      const key = name[0].toLowerCase();
      if (peek() === "(") {
        i++;
        const fn = FUNCTIONS[key] ?? fail(`Unknown function ${name[0]}`);
        const args: number[] = [];
        if (peek() !== ")") { args.push(expr()); while (peek() === ",") { i++; args.push(expr()); } }
        if (peek() !== ")") fail("Missing )");
        i++;
        return fn(...args);
      }
      if (key in variables) return variables[key];
      if (key in CONSTANTS) return CONSTANTS[key];
      fail(`Unknown name ${name[0]}`);
    }
    return fail(`Unexpected '${c}'`);
  }

  if (!src.trim()) fail("Enter an expression");
  const value = expr();
  if (peek() !== undefined) fail(`Unexpected '${src[i]}'`);
  if (!Number.isFinite(value)) fail("Result is not a finite number");
  return value;
}

export function formatResult(v: number): string {
  if (v !== 0 && (Math.abs(v) >= 1e12 || Math.abs(v) < 1e-6)) return v.toExponential(6).replace(/\.?0+e/, "e");
  return String(Number(v.toPrecision(12)));
}
