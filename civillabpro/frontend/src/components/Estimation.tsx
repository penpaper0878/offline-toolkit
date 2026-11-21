import AddOutlined from "@mui/icons-material/AddOutlined";
import DeleteOutlined from "@mui/icons-material/DeleteOutlined";
import UploadFileOutlined from "@mui/icons-material/UploadFileOutlined";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import IconButton from "@mui/material/IconButton";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import { useQuery } from "@tanstack/react-query";
import { Fragment, useEffect, useRef, useState } from "react";
import { api, type ApiError } from "../api/client";
import { useInvalidatingMutation, useSorBooks, useSorItems } from "../api/hooks";
import type { AnalysisKind, AnalysisLine, RateAnalysis, RateAnalysisInput, SorBook, SorImportResult, SorItem } from "../api/types";
import { fmt } from "../lib/format";
import { useUi } from "../stores/ui";

const th = "py-1.5 px-2 font-semibold text-left";
const td = "py-1 px-2 align-top";

/** Search a schedule of rates and pick an item. */
export function SorPicker({ open, onClose, onPick, browseOnly = false }: {
  open: boolean; onClose: () => void; onPick?: (item: SorItem, book: SorBook) => void; browseOnly?: boolean;
}) {
  const books = useSorBooks();
  const [bookId, setBookId] = useState("");
  const [q, setQ] = useState("");
  const [term, setTerm] = useState("");
  useEffect(() => { const t = setTimeout(() => setTerm(q), 250); return () => clearTimeout(t); }, [q]);
  useEffect(() => { if (!bookId && books.data?.length) setBookId(books.data[0].id); }, [books.data, bookId]);
  const items = useSorItems(bookId, term);
  const book = books.data?.find((b) => b.id === bookId);
  return (
    <Dialog open={open} onClose={onClose} maxWidth="lg" fullWidth aria-label="Schedule of rates">
      <DialogTitle>{browseOnly ? "Schedule of rates" : "Add an item from a schedule of rates"}</DialogTitle>
      <DialogContent>
        {books.data?.length === 0 ? <p>No schedule of rates is imported yet: import one on the Quantity estimation page.</p> : (
          <div className="flex flex-col gap-3 pt-1">
            <div className="flex gap-2">
              <TextField select label="Schedule" value={bookId} onChange={(e) => setBookId(e.target.value)} sx={{ minWidth: 320 }}>
                {(books.data ?? []).map((b) => <MenuItem key={b.id} value={b.id}>{b.title} ({b.item_count} items)</MenuItem>)}
              </TextField>
              <TextField label="Search by code or words" value={q} onChange={(e) => setQ(e.target.value)} fullWidth autoFocus />
            </div>
            <div className="text-[12px] text-[var(--clp-ink-3)]">{items.data ? `${items.data.total} item${items.data.total === 1 ? "" : "s"}` : ""}{items.data && items.data.total > 100 ? ", the first 100 shown: narrow the search" : ""}</div>
            <div className="max-h-[55vh] overflow-y-auto border border-[var(--clp-border)] rounded">
              <table className="w-full text-[12.5px] border-collapse">
                <thead className="sticky top-0 bg-[var(--clp-panel-2)]"><tr><th className={th}>Code</th><th className={th}>Description</th><th className={th}>Unit</th><th className={`${th} text-right`}>Rate (Rs)</th>{!browseOnly && <th className={th} />}</tr></thead>
                <tbody>
                  {(items.data?.items ?? []).map((it) => (
                    <tr key={it.id} className="border-t border-[var(--clp-border)] hover:bg-[var(--clp-panel-2)]">
                      <td className={`${td} whitespace-nowrap font-semibold`}>{it.item_code}</td>
                      <td className={td}>{it.description}{it.chapter && <div className="text-[11px] text-[var(--clp-ink-3)]">{it.chapter}</div>}</td>
                      <td className={td}>{it.unit}</td>
                      <td className={`${td} text-right num`}>{fmt(it.rate)}</td>
                      {!browseOnly && <td className={td}><Button size="small" aria-label={`Add item ${it.item_code}`} onClick={() => book && onPick?.(it, book)}>Add</Button></td>}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </DialogContent>
      <DialogActions><Button onClick={onClose}>Close</Button></DialogActions>
    </Dialog>
  );
}

/** Import a schedule of rates from a CSV file or an Excel workbook. */
export function ImportSorDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const notify = useUi((s) => s.notify);
  const [form, setForm] = useState({ title: "", authority: "", state: "", year: "" });
  const [file, setFile] = useState<File | null>(null);
  const [report, setReport] = useState<SorImportResult | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const importIt = useInvalidatingMutation(async () => {
    if (!file) throw new Error("Choose a file.");
    const body: Record<string, unknown> = { title: form.title, authority: form.authority, state: form.state, year: form.year ? Number(form.year) : null, filename: file.name };
    if (/\.xlsx?m?$/i.test(file.name)) {
      const bytes = new Uint8Array(await file.arrayBuffer());
      let bin = "";
      for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
      body.content_base64 = btoa(bin);
    } else body.content = await file.text();
    return api<SorImportResult>("/sor-books/import", { method: "POST", body });
  });
  const close = () => { setReport(null); setFile(null); setForm({ title: "", authority: "", state: "", year: "" }); onClose(); };
  return (
    <Dialog open={open} onClose={close} maxWidth="sm" fullWidth aria-label="Import a schedule of rates">
      <DialogTitle>Import a schedule of rates</DialogTitle>
      <DialogContent>
        {report ? (
          <div className="flex flex-col gap-2 pt-1">
            <p className="m-0">{report.imported} items imported into <b>{report.book.title}</b>{report.headings ? `, under ${report.headings} heading${report.headings === 1 ? "" : "s"}` : ""}.</p>
            {report.skipped.length > 0 && (<>
              <p className="m-0">{report.skipped.length} row{report.skipped.length === 1 ? "" : "s"} skipped:</p>
              <ul className="m-0 pl-5 max-h-40 overflow-y-auto text-[12px]">{report.skipped.map((s) => <li key={s}>{s}</li>)}</ul>
            </>)}
          </div>
        ) : (
          <div className="flex flex-col gap-3 pt-1">
            <p className="m-0 text-[12.5px] text-[var(--clp-ink-2)]">
              A CSV file or an Excel workbook (first sheet) with a header row naming the columns code, description, unit and rate (a chapter
              column is optional). A row with a code and a description but no unit or rate is a heading: it is put before the items whose codes
              start with its code. A row with only a description starts a chapter. Keep item codes as text in Excel, so that 5.10 stays 5.10.
            </p>
            <TextField label="Title" required value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="e.g. CPWD DSR 2023, Gujarat R&B SOR 2024-25" />
            <div className="grid grid-cols-3 gap-2">
              <TextField label="Authority" value={form.authority} onChange={(e) => setForm({ ...form, authority: e.target.value })} />
              <TextField label="State" value={form.state} onChange={(e) => setForm({ ...form, state: e.target.value })} />
              <TextField label="Year" value={form.year} onChange={(e) => setForm({ ...form, year: e.target.value.replace(/\D/g, "").slice(0, 4) })} />
            </div>
            <div className="flex items-center gap-2">
              <input ref={input} type="file" accept=".csv,.txt,.xlsx,.xlsm" hidden aria-label="Schedule of rates file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
              <Button variant="outlined" startIcon={<UploadFileOutlined />} onClick={() => input.current?.click()}>Choose a file</Button>
              <span className="text-[12.5px] text-[var(--clp-ink-2)]">{file?.name ?? "No file chosen"}</span>
            </div>
          </div>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={close}>{report ? "Done" : "Cancel"}</Button>
        {!report && <Button variant="contained" disabled={!form.title.trim() || !file || importIt.isPending}
          onClick={() => importIt.mutate(undefined, { onSuccess: setReport, onError: (e) => notify((e as ApiError).message, "error") })}>
          {importIt.isPending ? "Importing" : "Import"}
        </Button>}
      </DialogActions>
    </Dialog>
  );
}

const KINDS: AnalysisKind[] = ["material", "labour", "plant", "sundries"];
type AnalysisResult = Record<AnalysisKind | "cost" | "water" | "overheads_profit" | "total" | "rate", number> & { lines: number[] };
const KIND_LABEL: Record<AnalysisKind, string> = { material: "Material", labour: "Labour", plant: "Plant, carriage", sundries: "Sundries" };
const blankAnalysis = (): RateAnalysisInput => ({ title: "", unit: "", output_qty: 1, water_pct: 1, overheads_profit_pct: 15,
  lines: [{ kind: "material", description: "", unit: "", quantity: 0, rate: 0 }] });

/** Edit a rate analysis: its constituents, the output quantity and the percentages; the rate is worked out live by the server. */
export function RateAnalysisDialog({ open, onClose, analysis }: { open: boolean; onClose: () => void; analysis: RateAnalysis | null }) {
  const notify = useUi((s) => s.notify);
  const [a, setA] = useState<RateAnalysisInput>(blankAnalysis);
  useEffect(() => {
    if (!open) return;
    setA(analysis ? { title: analysis.title, unit: analysis.unit, output_qty: analysis.output_qty, water_pct: analysis.water_pct,
      overheads_profit_pct: analysis.overheads_profit_pct, lines: analysis.lines } : blankAnalysis());
  }, [open, analysis]);
  const valid = a.output_qty > 0 && a.lines.every((l) => l.description.trim());
  const calc = useQuery({
    queryKey: ["analysis-calc", a], enabled: open && valid,
    queryFn: ({ signal }) => api<AnalysisResult>("/rate-analyses/calculate", { method: "POST", body: { ...a, title: a.title || "x", unit: a.unit || "x" }, signal }),
  });
  const save = useInvalidatingMutation(() => analysis
    ? api<RateAnalysis>(`/rate-analyses/${analysis.id}`, { method: "PUT", body: a })
    : api<RateAnalysis>("/rate-analyses", { method: "POST", body: a }));
  const setLine = (i: number, patch: Partial<AnalysisLine>) => setA({ ...a, lines: a.lines.map((l, k) => (k === i ? { ...l, ...patch } : l)) });
  const num = (v: string) => (v === "" ? 0 : Number(v));
  const r = calc.data;
  return (
    <Dialog open={open} onClose={onClose} maxWidth="lg" fullWidth aria-label="Rate analysis">
      <DialogTitle>{analysis ? "Rate analysis" : "New rate analysis"}</DialogTitle>
      <DialogContent>
        <div className="flex flex-col gap-3 pt-1">
          <div className="grid grid-cols-[1fr_120px] gap-2">
            <TextField label="Item" required value={a.title} onChange={(e) => setA({ ...a, title: e.target.value })} />
            <TextField label="Unit" required value={a.unit} onChange={(e) => setA({ ...a, unit: e.target.value })} />
          </div>
          <table className="w-full text-[12.5px] border-collapse" aria-label="Constituents">
            <thead><tr className="text-[11px] text-[var(--clp-ink-3)]"><th className={th}>Kind</th><th className={th}>Description</th><th className={th}>Unit</th>
              <th className={th}>Quantity</th><th className={th}>Rate (Rs)</th><th className={`${th} text-right`}>Amount</th><th /></tr></thead>
            <tbody>
              {a.lines.map((l, i) => (
                <tr key={i}>
                  <td className={td}><TextField select size="small" value={l.kind} onChange={(e) => setLine(i, { kind: e.target.value as AnalysisKind })} slotProps={{ htmlInput: { "aria-label": `Kind, line ${i + 1}` } }}>
                    {KINDS.map((k) => <MenuItem key={k} value={k}>{KIND_LABEL[k]}</MenuItem>)}</TextField></td>
                  <td className={td}><TextField size="small" fullWidth value={l.description} onChange={(e) => setLine(i, { description: e.target.value })} slotProps={{ htmlInput: { "aria-label": `Description, line ${i + 1}` } }} /></td>
                  <td className={td}><TextField size="small" value={l.unit} onChange={(e) => setLine(i, { unit: e.target.value })} sx={{ width: 80 }} slotProps={{ htmlInput: { "aria-label": `Unit, line ${i + 1}` } }} /></td>
                  <td className={td}><TextField size="small" type="number" value={l.quantity} onChange={(e) => setLine(i, { quantity: num(e.target.value) })} sx={{ width: 110 }} slotProps={{ htmlInput: { "aria-label": `Quantity, line ${i + 1}`, step: "any" } }} /></td>
                  <td className={td}><TextField size="small" type="number" value={l.rate} onChange={(e) => setLine(i, { rate: num(e.target.value) })} sx={{ width: 120 }} slotProps={{ htmlInput: { "aria-label": `Rate, line ${i + 1}`, step: "any" } }} /></td>
                  <td className={`${td} text-right num pt-3`}>{r?.lines?.[i] !== undefined ? fmt(r.lines[i]) : ""}</td>
                  <td className={td}><IconButton size="small" aria-label={`Remove line ${i + 1}`} disabled={a.lines.length <= 1} onClick={() => setA({ ...a, lines: a.lines.filter((_, k) => k !== i) })}><DeleteOutlined fontSize="small" /></IconButton></td>
                </tr>
              ))}
            </tbody>
          </table>
          <div><Button size="small" startIcon={<AddOutlined />} onClick={() => setA({ ...a, lines: [...a.lines, { ...a.lines[a.lines.length - 1], description: "", quantity: 0, rate: 0 }] })}>Add line</Button></div>
          <div className="grid grid-cols-3 gap-2 max-w-[560px]">
            <TextField label="Output quantity" type="number" value={a.output_qty} onChange={(e) => setA({ ...a, output_qty: num(e.target.value) })} slotProps={{ htmlInput: { step: "any" } }} helperText="Of the item, for these lines" />
            <TextField label="Water charges (%)" type="number" value={a.water_pct} onChange={(e) => setA({ ...a, water_pct: num(e.target.value) })} slotProps={{ htmlInput: { step: "any" } }} />
            <TextField label="Overheads and profit (%)" type="number" value={a.overheads_profit_pct} onChange={(e) => setA({ ...a, overheads_profit_pct: num(e.target.value) })} slotProps={{ htmlInput: { step: "any" } }} />
          </div>
          {r && (
            <div className="grid grid-cols-[auto_auto] gap-x-6 gap-y-0.5 w-fit text-[13px]" aria-label="Analysis result">
              {KINDS.map((k) => <Fragment key={k}><span className="text-[var(--clp-ink-2)]">{KIND_LABEL[k]}</span><span className="num text-right">{fmt(r[k])}</span></Fragment>)}
              <span className="text-[var(--clp-ink-2)]">Cost</span><span className="num text-right">{fmt(r.cost)}</span>
              <span className="text-[var(--clp-ink-2)]">Water charges</span><span className="num text-right">{fmt(r.water)}</span>
              <span className="text-[var(--clp-ink-2)]">Overheads and profit</span><span className="num text-right">{fmt(r.overheads_profit)}</span>
              <span className="font-semibold">Rate per {a.unit || "unit"}</span><span className="num text-right font-semibold">{fmt(r.rate)}</span>
            </div>
          )}
        </div>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" disabled={!a.title.trim() || !a.unit.trim() || !valid || save.isPending}
          onClick={() => save.mutate(undefined, { onSuccess: () => { notify("Rate analysis saved", "success"); onClose(); }, onError: (e) => notify((e as ApiError).message, "error") })}>Save</Button>
      </DialogActions>
    </Dialog>
  );
}
