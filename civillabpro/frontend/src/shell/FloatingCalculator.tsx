import CloseOutlined from "@mui/icons-material/CloseOutlined";
import DragIndicatorOutlined from "@mui/icons-material/DragIndicatorOutlined";
import IconButton from "@mui/material/IconButton";
import { AnimatePresence, motion, useDragControls } from "framer-motion";
import { useRef, useState } from "react";
import { CalcError, evaluate, formatResult } from "../lib/calculator";
import { useUi } from "../stores/ui";

interface Line { expr: string; result: string }
const KEYS = ["7", "8", "9", "/", "sqrt(", "4", "5", "6", "*", "^", "1", "2", "3", "-", "(", "0", ".", "ans", "+", ")"];

/** A calculator that floats over any workspace. Drag it by its title bar; "ans" recalls the last result. */
export function FloatingCalculator() {
  const { calculatorOpen, setCalculatorOpen } = useUi();
  const [input, setInput] = useState("");
  const [lines, setLines] = useState<Line[]>([]);
  const [error, setError] = useState("");
  const [ans, setAns] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const constraints = useRef<HTMLDivElement>(null);
  const drag = useDragControls();

  function compute() {
    try {
      const value = evaluate(input, { ans });
      const result = formatResult(value);
      setLines((l) => [...l.slice(-5), { expr: input, result }]);
      setAns(value);
      setInput("");
      setError("");
    } catch (e) {
      setError(e instanceof CalcError ? e.message : "Cannot evaluate");
    }
  }
  const press = (k: string) => { setInput((v) => v + k); setError(""); inputRef.current?.focus(); };

  return (
    <div ref={constraints} className="no-print pointer-events-none fixed inset-2 z-[1250]">
      <AnimatePresence>
        {calculatorOpen && (
          <motion.div
            drag
            dragControls={drag}
            dragListener={false}
            dragMomentum={false}
            dragConstraints={constraints}
            initial={{ opacity: 0, scale: 0.96, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: 8 }}
            transition={{ duration: 0.14 }}
            role="dialog"
            aria-label="Calculator"
            className="pointer-events-auto absolute right-4 bottom-10 w-[264px] rounded-md border border-[var(--clp-border)] bg-[var(--clp-panel)] shadow-xl"
          >
            <div onPointerDown={(e) => drag.start(e)} className="flex items-center h-8 pl-1.5 pr-1 gap-1 border-b border-[var(--clp-border)] bg-[var(--clp-panel-2)] rounded-t-md cursor-move select-none">
              <DragIndicatorOutlined sx={{ fontSize: 16 }} className="text-[var(--clp-ink-3)]" />
              <span className="text-xs font-semibold flex-1">Calculator</span>
              <IconButton aria-label="Close calculator" onClick={() => setCalculatorOpen(false)} sx={{ p: 0.25 }}><CloseOutlined sx={{ fontSize: 15 }} /></IconButton>
            </div>
            <div className="px-2.5 pt-2 h-[86px] overflow-y-auto flex flex-col justify-end text-right num" aria-live="polite">
              {lines.length === 0 && <div className="text-[11px] text-[var(--clp-ink-3)] text-left">Functions: sqrt, sin, cos, tan (degrees), log, ln, min, max, bar(dia, n) for bar area, pi.</div>}
              {lines.map((l, i) => (
                <div key={i} className="leading-tight mb-1">
                  <div className="text-[11px] text-[var(--clp-ink-3)] truncate">{l.expr}</div>
                  <button type="button" onClick={() => press(l.result)} className="text-[13px] font-semibold bg-transparent border-0 p-0 cursor-pointer text-[var(--clp-ink)]" title="Insert this result">= {l.result}</button>
                </div>
              ))}
            </div>
            <div className="px-2.5 pb-2">
              <input
                ref={inputRef}
                autoFocus
                value={input}
                onChange={(e) => { setInput(e.target.value); setError(""); }}
                onKeyDown={(e) => { if (e.key === "Enter") compute(); if (e.key === "Escape") setCalculatorOpen(false); }}
                placeholder="0.87*500*603/1000"
                aria-label="Expression"
                aria-invalid={!!error}
                className={`w-full h-8 px-2 rounded border bg-[var(--clp-bg)] text-right text-sm num outline-none text-[var(--clp-ink)] ${error ? "border-[var(--clp-bad)]" : "border-[var(--clp-border)] focus:border-[var(--clp-accent)]"}`}
              />
              <div className="h-4 text-[11px] text-[var(--clp-bad)]" role="alert">{error}</div>
              <div className="grid grid-cols-5 gap-1">
                {KEYS.map((k) => (
                  <button key={k} type="button" onClick={() => press(k)} className="h-7 rounded border border-[var(--clp-border)] bg-[var(--clp-panel-2)] hover:bg-[var(--clp-border)] text-xs cursor-pointer text-[var(--clp-ink)]">
                    {k === "*" ? "×" : k === "/" ? "÷" : k === "sqrt(" ? "√" : k}
                  </button>
                ))}
                <button type="button" onClick={() => { setInput(""); setError(""); }} className="col-span-2 h-7 rounded border border-[var(--clp-border)] bg-[var(--clp-panel-2)] text-xs cursor-pointer text-[var(--clp-ink)]">Clear</button>
                <button type="button" onClick={compute} className="col-span-3 h-7 rounded border-0 bg-[var(--clp-accent)] text-white dark:text-slate-900 text-xs font-semibold cursor-pointer">=</button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
