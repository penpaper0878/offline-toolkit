import AddOutlined from "@mui/icons-material/AddOutlined";
import DeleteOutlined from "@mui/icons-material/DeleteOutlined";
import PictureAsPdfOutlined from "@mui/icons-material/PictureAsPdfOutlined";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import IconButton from "@mui/material/IconButton";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type ApiError, download } from "../api/client";
import { useEstimate, useInvalidatingMutation, useMeasurementBook, useProject } from "../api/hooks";
import type { ItemProgress, MbEntry, MbEntryInput, Measurement } from "../api/types";
import { Card, Empty, PageHeader } from "../components/Card";
import { EstimateStatus, input, Num } from "../components/EstimateCommon";
import { fmt, fmtDate } from "../lib/format";
import { useTab } from "../shell/hooks";
import { useAuth } from "../stores/auth";
import { useUi } from "../stores/ui";

const th = "py-2 px-2 font-semibold";
const td = "py-1.5 px-2";
const blankLine = (): Measurement => ({ description: "", nos: 1, length: null, breadth: null, depth: null, deduct: false });
const today = () => new Date().toLocaleDateString("en-CA"); // YYYY-MM-DD in the user's own time zone

/** Record or correct an entry, or read a checked one: the quantities come from the server as the lines are typed. */
function EntryDialog({ open, onClose, estimateId, items, entry, readOnly }: {
  open: boolean; onClose: () => void; estimateId: string; items: ItemProgress[]; entry: MbEntry | null; readOnly: boolean;
}) {
  const notify = useUi((s) => s.notify);
  const [form, setForm] = useState<MbEntryInput>({ item_id: "", measured_on: today(), location: "", lines: [blankLine()] });
  useEffect(() => {
    if (!open) return;
    setForm(entry ? { item_id: entry.item_id, measured_on: entry.measured_on, location: entry.location, lines: entry.lines }
      : { item_id: items[0]?.item_id ?? "", measured_on: today(), location: "", lines: [blankLine()] });
  }, [open, entry, items]);
  const calc = useQuery({
    queryKey: ["mb-calc", form.lines], enabled: open, placeholderData: keepPreviousData, retry: false,
    queryFn: ({ signal }) => api<{ lines: number[]; quantity: number }>("/measurement-book/calculate", { method: "POST", body: { lines: form.lines }, signal }),
  });
  const save = useInvalidatingMutation(() => entry
    ? api<MbEntry>(`/mb-entries/${entry.id}`, { method: "PUT", body: form })
    : api<MbEntry>(`/estimates/${estimateId}/measurement-book`, { method: "POST", body: form }));
  const setLine = (i: number, patch: Partial<Measurement>) => setForm({ ...form, lines: form.lines.map((l, k) => (k === i ? { ...l, ...patch } : l)) });
  const item = items.find((x) => x.item_id === form.item_id);
  return (
    <Dialog open={open} onClose={onClose} maxWidth="lg" fullWidth aria-label="Measurement book entry">
      <DialogTitle>{entry ? `Entry ${entry.entry_no}${readOnly ? "" : ": correct it"}` : "Record a measurement"}</DialogTitle>
      <DialogContent>
        <div className="flex flex-col gap-3 pt-1">
          <div className="grid grid-cols-1 md:grid-cols-[1fr_170px] gap-2">
            <TextField select label="Item" value={form.item_id} disabled={readOnly} onChange={(e) => setForm({ ...form, item_id: e.target.value })}>
              {items.filter((x) => x.in_estimate || x.item_id === form.item_id).map((x) => (
                <MenuItem key={x.item_id} value={x.item_id}>{x.no}. {x.description.slice(0, 110)} ({x.unit})</MenuItem>))}
            </TextField>
            <TextField label="Measured on" type="date" value={form.measured_on} disabled={readOnly} onChange={(e) => setForm({ ...form, measured_on: e.target.value })}
              slotProps={{ inputLabel: { shrink: true } }} />
          </div>
          <TextField label="Location, or the work measured" value={form.location} disabled={readOnly} onChange={(e) => setForm({ ...form, location: e.target.value })}
            placeholder="e.g. Footings F1 to F4, grid A1 to A4" />
          <table className="w-full text-[12.5px] border-collapse" aria-label="Measurement lines">
            <thead><tr className="text-[11px] text-[var(--clp-ink-3)]">
              <th className={`${th} text-left`}>Measurement</th><th className={`${th} text-right`}>Nos</th><th className={`${th} text-right`}>Length</th>
              <th className={`${th} text-right`}>Breadth</th><th className={`${th} text-right`}>Depth</th><th className={`${th} text-left`}>Deduct</th>
              <th className={`${th} text-right`}>Quantity</th>{!readOnly && <th />}</tr></thead>
            <tbody>
              {form.lines.map((m, k) => {
                const tag = `line ${k + 1}`;
                const q = calc.data?.lines[k];
                return (
                  <tr key={k}>
                    <td className="py-1 px-1"><input className={input} disabled={readOnly} aria-label={`Measurement, ${tag}`} value={m.description} onChange={(e) => setLine(k, { description: e.target.value })} /></td>
                    <td className="py-1 px-1 text-right"><Num value={m.nos} disabled={readOnly} label={`Nos, ${tag}`} onChange={(v) => setLine(k, { nos: v ?? 0 })} width="w-[64px]" /></td>
                    <td className="py-1 px-1 text-right"><Num value={m.length} disabled={readOnly} blank label={`Length, ${tag}`} onChange={(v) => setLine(k, { length: v })} /></td>
                    <td className="py-1 px-1 text-right"><Num value={m.breadth} disabled={readOnly} blank label={`Breadth, ${tag}`} onChange={(v) => setLine(k, { breadth: v })} /></td>
                    <td className="py-1 px-1 text-right"><Num value={m.depth} disabled={readOnly} blank label={`Depth, ${tag}`} onChange={(v) => setLine(k, { depth: v })} /></td>
                    <td className="py-1 px-1"><input type="checkbox" disabled={readOnly} aria-label={`Deduct, ${tag}`} checked={m.deduct} onChange={(e) => setLine(k, { deduct: e.target.checked })} className="mt-1.5" /></td>
                    <td className={`py-1 px-1 text-right num pt-2 ${q !== undefined && q < 0 ? "text-[var(--clp-bad)]" : ""}`}>{q !== undefined ? fmt(q) : ""}</td>
                    {!readOnly && <td className="py-1 px-1 text-right"><IconButton size="small" aria-label={`Remove ${tag}`} disabled={form.lines.length <= 1}
                      onClick={() => setForm({ ...form, lines: form.lines.filter((_, x) => x !== k) })}><DeleteOutlined fontSize="small" /></IconButton></td>}
                  </tr>
                );
              })}
            </tbody>
          </table>
          <div className="flex items-center gap-4">
            {!readOnly && <Button size="small" startIcon={<AddOutlined />} onClick={() => setForm({ ...form, lines: [...form.lines, { ...form.lines[form.lines.length - 1], description: "", deduct: false }] })}>Add line</Button>}
            <span className="ml-auto text-[13px]">Quantity of the entry <b className="num">{calc.data ? fmt(calc.data.quantity) : "-"} {item?.unit ?? ""}</b></span>
          </div>
          {entry && (
            <div className="text-[12px] text-[var(--clp-ink-3)]">Measured by {entry.measured_by_name}{entry.status === "checked" ? `; checked by ${entry.checked_by_name} on ${fmtDate(entry.checked_at)}.` : "; not yet checked."}</div>
          )}
        </div>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{readOnly ? "Close" : "Cancel"}</Button>
        {!readOnly && <Button variant="contained" disabled={!form.item_id || !form.measured_on || save.isPending}
          onClick={() => save.mutate(undefined, { onSuccess: (m) => { notify(`Entry ${m.entry_no} ${entry ? "corrected" : "recorded"}`, "success"); onClose(); },
            onError: (e) => notify((e as ApiError).message, "error") })}>{entry ? "Save" : "Record"}</Button>}
      </DialogActions>
    </Dialog>
  );
}

export function MeasurementBookPage() {
  const { estimateId } = useParams();
  const est = useEstimate(estimateId);
  const book = useMeasurementBook(estimateId);
  const project = useProject(est.data?.project_id);
  const can = useAuth((s) => s.can);
  const notify = useUi((s) => s.notify);
  useTab(est.data ? `Measurement book ${est.data.title}` : undefined);
  const [dialog, setDialog] = useState<{ entry: MbEntry | null } | null>(null);
  const check = useInvalidatingMutation((id: string) => api<MbEntry>(`/mb-entries/${id}/check`, { method: "POST" }));
  const remove = useInvalidatingMutation((id: string) => api<void>(`/mb-entries/${id}`, { method: "DELETE" }));
  const fail = (e: unknown) => notify((e as ApiError).message, "error");

  if (est.error || book.error) return <div className="p-6 text-[var(--clp-bad)]" role="alert">{((est.error ?? book.error) as Error).message} <Link to="/estimation">Back to estimation</Link></div>;
  if (!est.data || !book.data) return <div className="p-6 text-[var(--clp-ink-3)]">Loading the measurement book</div>;
  const e = est.data;
  const b = book.data;
  const items = new Map(b.items.map((x) => [x.item_id, x]));
  const canRecord = b.open && can("estimate:write") && b.items.some((x) => x.in_estimate);

  return (
    <div className="p-5 max-w-[1500px] mx-auto flex flex-col gap-3">
      <PageHeader title={`Measurement book: ${e.title}`} subtitle={project.data ? `${project.data.code}  ${project.data.name}` : undefined}>
        <EstimateStatus status={e.status} revision={e.revision} />
        <Button component={Link} to={`/estimates/${e.id}`}>The estimate</Button>
        <Button startIcon={<PictureAsPdfOutlined />} onClick={() => download(`/estimates/${e.id}/measurement-book.pdf`, "measurement_book.pdf").catch(fail)}>PDF</Button>
        {canRecord && <Button variant="contained" startIcon={<AddOutlined />} onClick={() => setDialog({ entry: null })}>Record a measurement</Button>}
      </PageHeader>
      {!b.open && <Alert severity="info">Work is measured against an issued estimate. This one is a draft that has not been issued yet.</Alert>}

      <Card title="Progress against the estimate">
        <div className="overflow-x-auto">
          <table className="w-full text-[12.5px] border-collapse" aria-label="Progress">
            <thead><tr className="text-left text-[11px] text-[var(--clp-ink-3)] border-b border-[var(--clp-border)]">
              <th className={th}>No.</th><th className={th}>Description</th><th className={th}>Unit</th>
              {["Estimated", "Measured", "Checked", "Balance", "Done %", "Excess", "Value measured (Rs)"].map((h) => <th key={h} className={`${th} text-right`}>{h}</th>)}
            </tr></thead>
            <tbody>
              {b.items.map((x) => (
                <tr key={x.item_id} className="border-b border-[var(--clp-border)] last:border-0">
                  <td className={`${td} font-semibold`}>{x.no}</td>
                  <td className={td}><div className="line-clamp-2">{x.description}</div>{!x.in_estimate && <div className="text-[11px] text-[var(--clp-warn)]">not in the estimate's current revision</div>}</td>
                  <td className={td}>{x.unit}</td>
                  <td className={`${td} text-right num`}>{fmt(x.estimated)}</td>
                  <td className={`${td} text-right num font-semibold`}>{fmt(x.measured)}</td>
                  <td className={`${td} text-right num`}>{fmt(x.checked)}</td>
                  <td className={`${td} text-right num`}>{fmt(x.balance)}</td>
                  <td className={`${td} text-right num`}>{x.percent === null ? "-" : fmt(x.percent, 1)}</td>
                  <td className={`${td} text-right num ${x.excess > 0 ? "font-semibold text-[var(--clp-warn)]" : ""}`}>{x.excess > 0 ? fmt(x.excess) : ""}</td>
                  <td className={`${td} text-right num`}>{fmt(x.value_measured)}</td>
                </tr>
              ))}
              <tr className="border-t border-[var(--clp-border)] font-semibold">
                <td className={td} /><td className={td}>Total</td><td colSpan={7} className={`${td} text-right text-[12px] font-normal text-[var(--clp-ink-2)]`}>
                  checked Rs {fmt(b.value_checked)}{b.value_excess > 0 ? `; beyond the estimated quantities Rs ${fmt(b.value_excess)}` : ""}</td>
                <td className={`${td} text-right num`}>{fmt(b.value_measured)}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div className="px-3 py-2 text-[11.5px] text-[var(--clp-ink-3)]">Values at the estimate's rates. The excess is the work measured beyond the estimated quantity; whether it is within the department's deviation limit is for the engineer in charge.</div>
      </Card>

      <Card title={`Entries (${b.entries.length})`}>
        {b.entries.length === 0 ? (
          <Empty title="No entries yet">{b.open && <span>Record the work done on an item: its lines are measured as in the estimate, and a second person checks the entry.</span>}</Empty>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-[12.5px] border-collapse" aria-label="Entries">
              <thead><tr className="text-left text-[11px] text-[var(--clp-ink-3)] border-b border-[var(--clp-border)]">
                <th className={th}>Entry</th><th className={th}>Date</th><th className={th}>Item</th><th className={th}>Location</th><th className={`${th} text-right`}>Quantity</th>
                <th className={th}>Measured by</th><th className={th}>Checked</th><th className={th} /></tr></thead>
              <tbody>
                {b.entries.map((m) => {
                  const it = items.get(m.item_id);
                  const recorded = m.status === "recorded";
                  return (
                    <tr key={m.id} className="border-b border-[var(--clp-border)] last:border-0 hover:bg-[var(--clp-panel-2)]">
                      <td className={td}><button type="button" className="font-semibold text-[var(--clp-accent)] bg-transparent border-0 p-0 cursor-pointer hover:underline"
                        aria-label={`Open entry ${m.entry_no}`} onClick={() => setDialog({ entry: m })}>{m.entry_no}</button></td>
                      <td className={`${td} whitespace-nowrap`}>{fmtDate(m.measured_on)}</td>
                      <td className={td}>{it ? `${it.no}. ${it.description.slice(0, 60)}${it.description.length > 60 ? "..." : ""}` : m.item_id}</td>
                      <td className={`${td} text-[var(--clp-ink-2)]`}>{m.location}</td>
                      <td className={`${td} text-right num font-semibold`}>{fmt(m.quantity)} {it?.unit}</td>
                      <td className={`${td} text-[var(--clp-ink-2)]`}>{m.measured_by_name}</td>
                      <td className={td}>{recorded ? <span className="text-[var(--clp-ink-3)]">not yet</span>
                        : <span className="text-[var(--clp-ok)]">{m.checked_by_name}, {fmtDate(m.checked_at)}</span>}</td>
                      <td className={`${td} text-right whitespace-nowrap`}>
                        {recorded && can("estimate:issue") && (
                          <Tooltip describeChild title="Checked by someone other than the one who measured it"><Button size="small" aria-label={`Check entry ${m.entry_no}`}
                            onClick={() => check.mutate(m.id, { onSuccess: () => notify(`Entry ${m.entry_no} checked`, "success"), onError: fail })}>Check</Button></Tooltip>)}
                        {recorded && can("estimate:write") && (
                          <Tooltip title="Delete the entry"><IconButton size="small" aria-label={`Delete entry ${m.entry_no}`} onClick={() => {
                            if (window.confirm(`Delete entry ${m.entry_no}?`)) remove.mutate(m.id, { onError: fail });
                          }}><DeleteOutlined fontSize="small" /></IconButton></Tooltip>)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <EntryDialog open={!!dialog} onClose={() => setDialog(null)} estimateId={e.id} items={b.items} entry={dialog?.entry ?? null}
        readOnly={!!dialog?.entry && (dialog.entry.status === "checked" || !can("estimate:write"))} />
    </div>
  );
}
