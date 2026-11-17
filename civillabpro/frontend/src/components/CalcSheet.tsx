import CheckCircle from "@mui/icons-material/CheckCircle";
import ErrorIcon from "@mui/icons-material/Error";
import InfoOutlined from "@mui/icons-material/InfoOutlined";
import WarningAmberOutlined from "@mui/icons-material/WarningAmberOutlined";
import type { Check, Flag, Sheet } from "../api/types";
import { fmt } from "../lib/format";
import { Fx, fxNodes, Unit } from "./Fx";
import { Utilisation } from "./Status";

export function Flags({ flags }: { flags: Flag[] }) {
  if (flags.length === 0) return null;
  return (
    <div className="flex flex-col gap-1.5">
      {flags.map((f, i) => {
        const tone = f.level === "error" ? "var(--clp-bad)" : f.level === "warning" ? "var(--clp-warn)" : "var(--clp-ink-3)";
        const Icon = f.level === "error" ? ErrorIcon : f.level === "warning" ? WarningAmberOutlined : InfoOutlined;
        return (
          <div key={i} className="flex gap-2 px-2.5 py-1.5 rounded border text-[12.5px]" style={{ borderColor: `color-mix(in srgb, ${tone} 45%, transparent)`, background: `color-mix(in srgb, ${tone} 8%, transparent)` }} role={f.level === "error" ? "alert" : "note"}>
            <Icon sx={{ fontSize: 16, color: tone, mt: "1px" }} />
            <span>{f.message}{f.ref && <span className="text-[var(--clp-ink-3)]"> [{f.ref}]</span>}</span>
          </div>
        );
      })}
    </div>
  );
}

export function Verdict({ ok }: { ok: boolean }) {
  return ok
    ? <span className="inline-flex items-center gap-1 font-semibold text-[var(--clp-ok)]"><CheckCircle sx={{ fontSize: 15 }} />OK</span>
    : <span className="inline-flex items-center gap-1 font-semibold text-[var(--clp-bad)]"><ErrorIcon sx={{ fontSize: 15 }} />Not OK</span>;
}

/** The calculation as the engine recorded it: one row per formula line, with its clause, and one per check. */
export function CalcSheet({ sheet }: { sheet: Sheet }) {
  return (
    <div className="p-3 flex flex-col gap-3">
      <Flags flags={sheet.flags} />
      {sheet.sections.map((section) => (
        <section key={section.title} className="@container">
          <h3 className="m-0 px-2 py-1 text-xs font-semibold bg-[var(--clp-panel-2)] border border-[var(--clp-border)] rounded-t">{section.title}</h3>
          <div className="text-[12.5px] border border-t-0 border-[var(--clp-border)]">
            {section.items.map((it, i) => (
              // Narrow panels stack the clause above the line; from about 600 px it gets its own column.
              <div key={i} className="grid grid-cols-[minmax(0,1fr)_auto] @xl:grid-cols-[168px_minmax(0,1fr)_auto] gap-x-3 px-2 py-1.5 border-b border-[var(--clp-border)] last:border-0">
                <div className="col-span-2 @xl:col-span-1 text-[11px] text-[var(--clp-ink-3)]">{it.ref}</div>
                {it.kind === "step" ? (
                  <>
                    <div className="min-w-0">
                      <div>{fxNodes(it.title, true)}</div>
                      {(it.eq || it.sub) && <div className="mt-0.5 text-[13px] break-words"><Fx>{it.eq && it.sub ? `${it.eq} = ${it.sub}` : it.eq || it.sub}</Fx></div>}
                    </div>
                    <div className="text-right whitespace-nowrap num"><b>{fmt(it.value, it.dp)}</b> <Unit>{it.unit}</Unit></div>
                  </>
                ) : (
                  <>
                    <div className="min-w-0">
                      <div><b>Check:</b> {fxNodes(it.title, true)}</div>
                      <div className="mt-0.5 text-[13px] num break-words">
                        <Fx>{it.lhs_label}</Fx> = {fmt(it.lhs, it.dp)} {it.op === "<=" ? "≤" : "≥"} <Fx>{it.rhs_label}</Fx> = {fmt(it.rhs, it.dp)} <Unit>{it.unit}</Unit>
                      </div>
                    </div>
                    <div className="text-right whitespace-nowrap">
                      <Verdict ok={it.ok} />
                      {it.util !== null && <div className="mt-1"><Utilisation value={it.util} /></div>}
                    </div>
                  </>
                )}
              </div>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}

/** Every limit in one table, worst first. */
export function ChecksTable({ sheet }: { sheet: Sheet }) {
  const checks = sheet.sections.flatMap((s) => s.items.filter((i): i is Check => i.kind === "check"));
  const sorted = [...checks].sort((a, b) => Number(a.ok) - Number(b.ok) || (b.util ?? -1) - (a.util ?? -1));
  if (checks.length === 0) return <div className="p-4 text-[var(--clp-ink-3)]">No checks were reached.</div>;
  return (
    <div className="p-3">
      <table className="w-full border-collapse text-[12.5px]">
        <thead>
          <tr className="text-left text-[11px] text-[var(--clp-ink-3)] border-b border-[var(--clp-border)]">
            <th className="py-1.5 pr-2 font-semibold">Check</th>
            <th className="py-1.5 px-2 font-semibold">Reference</th>
            <th className="py-1.5 px-2 font-semibold text-right">Value</th>
            <th className="py-1.5 px-2 font-semibold text-right">Limit</th>
            <th className="py-1.5 px-2 font-semibold">Utilisation</th>
            <th className="py-1.5 pl-2 font-semibold text-right">Result</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((c) => (
            <tr key={c.id} className="border-b border-[var(--clp-border)] last:border-0">
              <td className="py-1.5 pr-2">{fxNodes(c.title, true)}</td>
              <td className="py-1.5 px-2 text-[11px] text-[var(--clp-ink-3)] whitespace-nowrap">{c.ref}</td>
              <td className="py-1.5 px-2 text-right num whitespace-nowrap">{fmt(c.lhs, c.dp)} <Unit>{c.unit}</Unit></td>
              <td className="py-1.5 px-2 text-right num whitespace-nowrap">{c.op === "<=" ? "≤" : "≥"} {fmt(c.rhs, c.dp)}</td>
              <td className="py-1.5 px-2"><Utilisation value={c.util} /></td>
              <td className="py-1.5 pl-2 text-right"><Verdict ok={c.ok} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
