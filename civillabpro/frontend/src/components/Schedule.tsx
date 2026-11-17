import type { Bbs, Quantities } from "../api/types";
import { fmt } from "../lib/format";
import { Unit } from "./Fx";

const th = "py-1.5 px-2 font-semibold text-[11px] text-[var(--clp-ink-3)]";
const td = "py-1.5 px-2";

export function BbsTable({ bbs }: { bbs: Bbs }) {
  return (
    <div className="p-3 overflow-x-auto">
      <table className="w-full min-w-[720px] border-collapse text-[12.5px]">
        <thead>
          <tr className="text-left border-b border-[var(--clp-border)]">
            <th className={th}>Mark</th><th className={th}>Description</th><th className={th}>Shape</th><th className={`${th} text-center`}>Dia</th>
            <th className={`${th} text-center`}>Nos.</th><th className={th}>Dimensions (mm)</th><th className={`${th} text-right`}>Cut length (mm)</th>
            <th className={`${th} text-right`}>Total (m)</th><th className={`${th} text-right`}>Mass (kg)</th>
          </tr>
        </thead>
        <tbody>
          {bbs.items.map((it) => (
            <tr key={it.mark} className="border-b border-[var(--clp-border)] align-top" title={`Cutting length: ${it.formula}`}>
              <td className={`${td} font-semibold`}>{it.mark}</td>
              <td className={td}>{it.description}</td>
              <td className={`${td} text-[var(--clp-ink-2)]`}>{it.shape}</td>
              <td className={`${td} text-center num`}>T{it.dia}</td>
              <td className={`${td} text-center num`}>{it.count}</td>
              <td className={`${td} num text-[var(--clp-ink-2)]`}>{Object.entries(it.dims).map(([k, v]) => `${k} ${fmt(v, 0)}`).join(", ")}</td>
              <td className={`${td} text-right num`}>{fmt(it.cutting_length_mm, 0)}</td>
              <td className={`${td} text-right num`}>{fmt(it.total_length_m, 2)}</td>
              <td className={`${td} text-right num`}>{fmt(it.weight_kg, 2)}</td>
            </tr>
          ))}
          <tr className="font-semibold">
            <td className={td} /><td className={td}>Total</td><td className={td} colSpan={6} />
            <td className={`${td} text-right num`}>{fmt(bbs.total_weight_kg, 2)}</td>
          </tr>
        </tbody>
      </table>
      <div className="mt-3 flex flex-wrap gap-2">
        {bbs.summary.map((s) => (
          <div key={s.dia} className="px-2.5 py-1 rounded border border-[var(--clp-border)] bg-[var(--clp-panel-2)] text-xs num">
            <b>T{s.dia}</b> {fmt(s.length_m, 2)} m, {fmt(s.weight_kg, 2)} kg
          </div>
        ))}
      </div>
      <ul className="mt-3 pl-4 text-[11.5px] text-[var(--clp-ink-3)] leading-relaxed">{bbs.notes.map((n) => <li key={n}>{n}</li>)}</ul>
    </div>
  );
}

export function QuantitiesPanel({ q }: { q: Quantities }) {
  const rows: [string, number | null, number, string][] = [
    ["Concrete", q.concrete_m3, 3, "m3"],
    ["Formwork", q.formwork_m2, 2, "m2"],
    ["Reinforcement", q.steel_kg, 1, "kg"],
    ["Steel per volume of concrete", q.steel_kg_per_m3, 1, "kg/m3"],
  ];
  return (
    <div className="p-3">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-2">
        {rows.map(([label, value, dp, unit]) => (
          <div key={label} className="px-3 py-2 rounded border border-[var(--clp-border)] bg-[var(--clp-panel-2)]">
            <div className="text-[11px] text-[var(--clp-ink-3)]">{label}</div>
            <div className="text-lg font-semibold num leading-tight">{fmt(value, dp)} <span className="text-xs font-normal text-[var(--clp-ink-2)]"><Unit>{unit}</Unit></span></div>
          </div>
        ))}
      </div>
      <ul className="mt-3 pl-4 text-[11.5px] text-[var(--clp-ink-3)] leading-relaxed">{q.basis.map((n) => <li key={n}>{n}</li>)}</ul>
    </div>
  );
}
