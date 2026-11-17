import { describe, expect, it } from "vitest";
import { CalcError, evaluate, formatResult } from "./calculator";

describe("calculator", () => {
  it("follows operator precedence and brackets", () => {
    expect(evaluate("2 + 3 * 4")).toBe(14);
    expect(evaluate("(2 + 3) * 4")).toBe(20);
    expect(evaluate("2 ^ 3 ^ 2")).toBe(512); // right associative
    expect(evaluate("-2 ^ 2")).toBe(-4);
    expect(evaluate("10 % 4")).toBe(2);
    expect(evaluate("1.5e3 / 3")).toBe(500);
  });

  it("evaluates engineering expressions", () => {
    // Mu,lim of a 230 x 404 section in M25 / Fe 500, kN m
    expect(evaluate("0.36*25*230*184.235*(404-0.42*184.235)/10^6")).toBeCloseTo(124.56, 2);
    expect(evaluate("bar(16, 3)")).toBeCloseTo(603.19, 2);
    expect(evaluate("bar(8)")).toBeCloseTo(50.27, 2);
    expect(evaluate("sqrt(0.8*25)")).toBeCloseTo(4.4721, 4);
    expect(evaluate("sin(30) + cos(60)")).toBeCloseTo(1, 12);
    expect(evaluate("atan(1)")).toBeCloseTo(45, 12);
    expect(evaluate("max(1, 7, 3) - min(4, 2)")).toBe(5);
    expect(evaluate("log(1000) + ln(e)")).toBeCloseTo(4, 12);
    expect(evaluate("2*pi")).toBeCloseTo(6.283185, 6);
  });

  it("recalls the last answer and accepts typed symbols", () => {
    expect(evaluate("ans * 2", { ans: 21 })).toBe(42);
    expect(evaluate("6 × 7 ÷ 2")).toBe(21);
    expect(evaluate("1,250 + 250")).toBe(1500);
  });

  it("rejects what it cannot evaluate, with a reason", () => {
    for (const [expr, message] of [["", "Enter an expression"], ["2 +", "Incomplete expression"], ["(2 + 3", "Missing )"], ["2 / 0", "Division by zero"],
      ["foo(2)", "Unknown function foo"], ["x + 1", "Unknown name x"], ["2 $ 3", "Unexpected '$'"], ["sqrt(-1)", "Result is not a finite number"], ["2 3", "Unexpected '3'"]]) {
      expect(() => evaluate(expr)).toThrowError(new CalcError(message));
    }
  });

  it("never executes code", () => {
    expect(() => evaluate("constructor")).toThrow(CalcError);
    expect(() => evaluate("alert(1)")).toThrow(CalcError);
    expect(() => evaluate("__proto__")).toThrow(CalcError);
  });

  it("formats results without floating-point noise", () => {
    expect(formatResult(0.1 + 0.2)).toBe("0.3");
    expect(formatResult(1 / 3)).toBe("0.333333333333");
    expect(formatResult(1.5e15)).toBe("1.5e+15");
    expect(formatResult(0)).toBe("0");
  });
});
