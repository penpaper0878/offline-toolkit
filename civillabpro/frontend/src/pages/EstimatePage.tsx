import AddOutlined from "@mui/icons-material/AddOutlined";
import ArrowDownwardOutlined from "@mui/icons-material/ArrowDownwardOutlined";
import ArrowUpwardOutlined from "@mui/icons-material/ArrowUpwardOutlined";
import DeleteOutlined from "@mui/icons-material/DeleteOutlined";
import DownloadOutlined from "@mui/icons-material/DownloadOutlined";
import ExpandLessOutlined from "@mui/icons-material/ExpandLessOutlined";
import ExpandMoreOutlined from "@mui/icons-material/ExpandMoreOutlined";
import PictureAsPdfOutlined from "@mui/icons-material/PictureAsPdfOutlined";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import IconButton from "@mui/material/IconButton";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import { Fragment, useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, type ApiError, download } from "../api/client";
import { useDesignQuantities, useEstimate, useEstimatePreview, useInvalidatingMutation, useProject, useRateAnalyses } from "../api/hooks";
import type { DesignQuantities, DesignQuantityKey, Estimate, EstimateDoc, EstimateItem, EstimateItemResult, Measurement, RateAnalysis, SorBook, SorItem } from "../api/types";
import { Card, PageHeader } from "../components/Card";
import { EstimateStatus } from "../components/EstimateCommon";
import { SorPicker } from "../components/Estimation";
import { fmt, fmtDate } from "../lib/format";
import { useTab } from "../shell/hooks";
import { useAuth } from "../stores/auth";
import { useUi } from "../stores/ui";

/** What each design quantity is and the unit the design reports it in (as the server's DESIGN_QUANTITIES). */
export const DESIGN_QUANTITY: Record<DesignQuantityKey, { label: string; unit: string }> = {
  concrete_m3: { label: "Concrete", unit: "m3" },
  formwork_m2: { label: "Formwork", unit: "m2" },
  steel_kg: { label: "Reinforcement steel", unit: "kg" },
};
const MODES: { value: EstimateItem["quantity_mode"]; label: string }[] = [
  { value: "measured", label: "Measured" }, { value: "design", label: "From a design" }, { value: "direct", label: "Entered" },
];

type Draft = { title: string; notes: string; doc: EstimateDoc };

/** An identifier for a new item; crypto.randomUUID needs a secure context, which a server reached over plain http on a LAN is not. */
function newId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") return crypto.randomUUID();
  return `i${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;
}

const blankLine = (): Measurement => ({ description: "", nos: 1, length: null, breadth: null, depth: null, deduct: false });
const blankItem = (patch: Partial<EstimateItem> = {}): EstimateItem => ({
  id: newId(), item_no: "", description: "", unit: "", rate: 0, rate_source: { kind: "manual", sor_item_id: null, book_title: "", item_code: "", analysis_id: null },
  quantity_mode: "measured", quantity: 0, measurements: [], design: null, ...patch,
});

const input = "w-full bg-[var(--clp-panel)] border border-[var(--clp-border)] rounded px-1.5 py-1 text-[12.5px] text-[var(--clp-ink)] focus:outline-none focus:border-[var(--clp-accent)] disabled:bg-transparent disabled:border-transparent";
const th = "py-2 px-1.5 font-semibold text-left";
const td = "py-1 px-1.5 align-top";

/** A number field that may be left blank (a dimension not measured) or not. */
function Num({ value, onChange, label, blank = false, disabled, width = "w-[84px]" }: {
  value: number | null; onChange: (v: number | null) => void; label: string; blank?: boolean; disabled?: boolean; width?: string;
}) {
  return (
    <input type="number" step="any" aria-label={label} disabled={disabled} className={`${input} ${width} text-right num`}
      value={value ?? ""} onChange={(e) => onChange(e.target.value === "" ? (blank ? null : 0) : Number(e.target.value))} />
  );
}

function sourceCaption(it: EstimateItem): string {
  const s = it.rate_source;
  if (s.kind === "sor") return [s.book_title, s.item_code].filter(Boolean).join(", item ");
  if (s.kind === "analysis") return "Rate from a rate analysis";
  return s.item_code ? `Item ${s.item_code}, rate entered` : "";
}

/** A list to pick from, each row with an Add button. */
function PickDialog({ open, onClose, title, empty, rows }: {
  open: boolean; onClose: () => void; title: string; empty: ReactNode; rows: { key: string; main: ReactNode; sub?: ReactNode; right?: ReactNode; label: string; onAdd: () => void }[];
}) {
  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth aria-label={title}>
      <DialogTitle>{title}</DialogTitle>
      <DialogContent>
        {rows.length === 0 ? <div className="py-4 text-[var(--clp-ink-2)]">{empty}</div> : (
          <table className="w-full text-[13px] border-collapse">
            <tbody>
              {rows.map((r) => (
                <tr key={r.key} className="border-b border-[var(--clp-border)] last:border-0">
                  <td className={td}><div className="font-semibold">{r.main}</div>{r.sub && <div className="text-[11.5px] text-[var(--clp-ink-3)]">{r.sub}</div>}</td>
                  <td className={`${td} text-right num whitespace-nowrap`}>{r.right}</td>
                  <td className={`${td} text-right`}><Button size="small" aria-label={r.label} onClick={r.onAdd}>Add</Button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </DialogContent>
      <DialogActions><Button onClick={onClose}>Close</Button></DialogActions>
    </Dialog>
  );
}

const designOptions = (designs: DesignQuantities[] | undefined) =>
  (designs ?? []).flatMap((d) => (Object.keys(d.quantities) as DesignQuantityKey[]).map((key) => ({
    value: `${d.design_id}|${key}`, design: d, key, qty: d.quantities[key] as number,
    label: `${d.name} (${d.title}, R${d.revision}): ${DESIGN_QUANTITY[key].label.toLowerCase()} ${fmt(d.quantities[key])} ${DESIGN_QUANTITY[key].unit}`,
  })));

export function EstimatePage() {
  const { estimateId } = useParams();
  const est = useEstimate(estimateId);
  const e = est.data;
  const project = useProject(e?.project_id);
  const designs = useDesignQuantities(e?.project_id);
  const analyses = useRateAnalyses();
  const can = useAuth((s) => s.can);
  const notify = useUi((s) => s.notify);
  const navigate = useNavigate();
  useTab(e ? `Estimate ${e.title}` : undefined);

  const [draft, setDraft] = useState<Draft | null>(null);
  const base = useMemo<Draft | null>(() => (e ? { title: e.title, notes: e.notes, doc: e.doc } : null), [e]);
  useEffect(() => { setDraft(base); }, [base]);
  const dirty = !!draft && !!base && JSON.stringify(draft) !== JSON.stringify(base);

  // The figures of the document being edited come from the server, a moment after the last keystroke.
  const [settled, setSettled] = useState<EstimateDoc | null>(null);
  useEffect(() => { const t = setTimeout(() => setSettled(draft?.doc ?? null), 350); return () => clearTimeout(t); }, [draft?.doc]);
  const preview = useEstimatePreview(estimateId, dirty ? settled : null);
  const result = dirty ? (preview.data ?? e?.result) : e?.result;
  const byId = useMemo(() => new Map((result?.items ?? []).map((r) => [r.id, r])), [result]);

  const [openLines, setOpenLines] = useState<Set<string>>(new Set());
  const [addAnchor, setAddAnchor] = useState<HTMLElement | null>(null);
  const [picker, setPicker] = useState<"" | "sor" | "analysis" | "design">("");

  const fail = (err: unknown) => notify((err as ApiError).message, "error");
  const save = useInvalidatingMutation((d: Draft) => api<Estimate>(`/estimates/${estimateId}`, { method: "PUT", body: d }));
  const action = useInvalidatingMutation((what: "refresh" | "issue" | "revise") => api<Estimate>(`/estimates/${estimateId}/${what}`, { method: "POST" }));
  const remove = useInvalidatingMutation(() => api<void>(`/estimates/${estimateId}`, { method: "DELETE" }));

  const readOnly = !e || e.status === "issued" || !can("estimate:write");
  const doSave = () => { if (draft && dirty && !readOnly) save.mutate(draft, { onSuccess: () => notify("Estimate saved", "success"), onError: fail }); };

  useEffect(() => {
    if (!dirty) return;
    const warn = (ev: BeforeUnloadEvent) => { ev.preventDefault(); };
    const key = (ev: KeyboardEvent) => { if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === "s") { ev.preventDefault(); doSave(); } };
    window.addEventListener("beforeunload", warn);
    window.addEventListener("keydown", key);
    return () => { window.removeEventListener("beforeunload", warn); window.removeEventListener("keydown", key); };
  });

  if (est.error) return <div className="p-6 text-[var(--clp-bad)]" role="alert">{(est.error as Error).message} <Link to="/estimation">Back to estimation</Link></div>;
  if (!e || !draft) return <div className="p-6 text-[var(--clp-ink-3)]">Loading estimate</div>;

  const items = draft.doc.items;
  const setDoc = (doc: Partial<EstimateDoc>) => setDraft({ ...draft, doc: { ...draft.doc, ...doc } });
  const setItem = (id: string, patch: Partial<EstimateItem>) => setDoc({ items: items.map((it) => (it.id === id ? { ...it, ...patch } : it)) });
  const setLine = (it: EstimateItem, i: number, patch: Partial<Measurement>) =>
    setItem(it.id, { measurements: it.measurements.map((m, k) => (k === i ? { ...m, ...patch } : m)) });
  const addItem = (it: EstimateItem) => {
    setDoc({ items: [...items, it] });
    if (it.quantity_mode === "measured") setOpenLines(new Set(openLines).add(it.id));
  };
  const move = (i: number, by: number) => {
    const next = [...items];
    [next[i], next[i + by]] = [next[i + by], next[i]];
    setDoc({ items: next });
  };
  const toggle = (id: string) => { const s = new Set(openLines); if (s.has(id)) s.delete(id); else s.add(id); setOpenLines(s); };

  const fromSor = (s: SorItem, book: SorBook) => {
    addItem(blankItem({ description: s.description, unit: s.unit, rate: s.rate,
      rate_source: { kind: "sor", sor_item_id: s.id, book_title: book.title, item_code: s.item_code, analysis_id: null } }));
    notify(`Item ${s.item_code} added`, "success");
  };
  const fromAnalysis = (a: RateAnalysis) => {
    addItem(blankItem({ description: a.title, unit: a.unit, rate: a.rate,
      rate_source: { kind: "analysis", sor_item_id: null, book_title: "", item_code: "", analysis_id: a.id } }));
    notify(`${a.title} added`, "success");
  };
  const fromDesign = (d: DesignQuantities, key: DesignQuantityKey) => {
    addItem(blankItem({ description: `${DESIGN_QUANTITY[key].label}: ${d.title} ${d.name}`, unit: DESIGN_QUANTITY[key].unit, quantity_mode: "design",
      design: { design_id: d.design_id, key, revision: null, value: null, label: "" } }));
    notify(`${DESIGN_QUANTITY[key].label} of ${d.name} added: enter its rate`, "success");
  };
  const options = designOptions(designs.data);
  const ab = result?.abstract;
  const stale = result?.stale ?? 0;

  return (
    <div className="p-5 max-w-[1500px] mx-auto flex flex-col gap-3">
      <PageHeader title={draft.title || "Untitled estimate"} subtitle={project.data ? `${project.data.code}  ${project.data.name}` : undefined}>
        <EstimateStatus status={e.status} revision={e.revision} />
        <span className="text-[13px] text-[var(--clp-ink-2)]">Total <b className="num text-[var(--clp-ink)]">Rs {fmt(ab?.rounded ?? 0, 0)}</b></span>
        {!readOnly && <Button variant="contained" disabled={!dirty || save.isPending} onClick={doSave}>Save</Button>}
        {!readOnly && dirty && <Button onClick={() => setDraft(base)}>Discard changes</Button>}
        {e.status === "draft" && can("estimate:issue") && (
          <Tooltip describeChild title={dirty ? "Save the changes first" : "Checked and issued by someone other than the preparer"}><span>
            <Button variant="outlined" disabled={dirty || action.isPending || items.length === 0} onClick={() => {
              if (window.confirm(`Issue R${e.revision} of ${e.title}? An issued estimate is not changed afterwards; it is revised.`)) {
                action.mutate("issue", { onSuccess: () => notify(`Estimate issued as R${e.revision}`, "success"), onError: fail });
              }
            }}>Issue</Button></span></Tooltip>
        )}
        {e.status === "issued" && can("estimate:write") && (
          <Button variant="outlined" disabled={action.isPending} onClick={() => action.mutate("revise", { onSuccess: (x) => notify(`Revision R${x.revision} opened`, "success"), onError: fail })}>Revise</Button>
        )}
        <Tooltip describeChild title={dirty ? "The workbook is of the saved estimate" : "Abstract with live formulas, and the measurements"}>
          <Button startIcon={<DownloadOutlined />} onClick={() => download(`/estimates/${e.id}/estimate.xlsx`, "estimate.xlsx").catch(fail)}>Excel</Button>
        </Tooltip>
        <Tooltip describeChild title={dirty ? "The report is of the saved estimate" : "Abstract and measurements, with the title block"}>
          <Button startIcon={<PictureAsPdfOutlined />} onClick={() => download(`/estimates/${e.id}/estimate.pdf`, "estimate.pdf").catch(fail)}>PDF</Button>
        </Tooltip>
        {e.status === "draft" && can("estimate:write") && (
          <Tooltip title="Delete the draft"><IconButton aria-label="Delete estimate" onClick={() => {
            if (window.confirm(`Delete the draft estimate ${e.title}?`)) remove.mutate(undefined, { onSuccess: () => { notify("Estimate deleted", "success"); navigate(`/projects/${e.project_id}`); }, onError: fail });
          }}><DeleteOutlined /></IconButton></Tooltip>
        )}
      </PageHeader>

      {e.status === "issued" && (
        <Alert severity="success">Issued as R{e.revision} by {e.issued_by_name} on {fmtDate(e.issued_at)}. It is kept as issued; to change it, open a revision.</Alert>
      )}
      {stale > 0 && (
        <Alert severity="warning" action={!readOnly && (
          <Tooltip describeChild title={dirty ? "Save or discard your changes first" : ""}><span>
            <Button color="inherit" size="small" disabled={dirty || action.isPending} onClick={() => action.mutate("refresh", { onSuccess: () => notify("Design quantities taken again", "success"), onError: fail })}>
              Take the current quantities</Button></span></Tooltip>)}>
          {stale} item{stale === 1 ? " takes its quantity" : "s take their quantities"} from a design revised since: the quantities shown are those recorded. {e.status === "draft" ? "It cannot be issued until they are taken again." : ""}
        </Alert>
      )}
      {dirty && preview.error && <Alert severity="error">{(preview.error as Error).message} The figures shown are from the last valid state.</Alert>}

      {!readOnly && (
        <div className="grid grid-cols-1 md:grid-cols-[1fr_auto] gap-3">
          <TextField label="Estimate title" value={draft.title} onChange={(ev) => setDraft({ ...draft, title: ev.target.value })} size="small" />
        </div>
      )}

      <Card title={`Items (${items.length})`} action={!readOnly && <>
        <Button size="small" variant="contained" startIcon={<AddOutlined />} onClick={(ev) => setAddAnchor(ev.currentTarget)} aria-haspopup="menu">Add item</Button>
        <Menu anchorEl={addAnchor} open={!!addAnchor} onClose={() => setAddAnchor(null)}>
          <MenuItem onClick={() => { setAddAnchor(null); setPicker("sor"); }}>From a schedule of rates</MenuItem>
          <MenuItem onClick={() => { setAddAnchor(null); setPicker("analysis"); }}>From a rate analysis</MenuItem>
          <MenuItem onClick={() => { setAddAnchor(null); setPicker("design"); }}>A quantity from a design</MenuItem>
          <MenuItem onClick={() => { setAddAnchor(null); addItem(blankItem()); }}>A blank item</MenuItem>
        </Menu>
      </>}>
        {items.length === 0 ? (
          <div className="px-6 py-10 text-center text-[var(--clp-ink-2)]">
            <div className="font-semibold text-[var(--clp-ink)]">No items yet</div>
            {readOnly ? "This estimate has no items." : "Add items from a schedule of rates or a rate analysis, take quantities from the project's designs, or enter an item."}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-[12.5px] border-collapse" aria-label="Estimate items">
              <thead><tr className="text-[11px] text-[var(--clp-ink-3)] border-b border-[var(--clp-border)]">
                <th className={`${th} w-[64px]`}>No.</th><th className={th}>Description</th><th className={`${th} w-[80px]`}>Unit</th><th className={`${th} w-[150px]`}>Quantity from</th>
                <th className={`${th} text-right w-[110px]`}>Quantity</th><th className={`${th} text-right w-[110px]`}>Rate (Rs)</th><th className={`${th} text-right w-[120px]`}>Amount (Rs)</th>
                {!readOnly && <th className={`${th} w-[108px]`} />}</tr></thead>
              <tbody>
                {items.map((it, i) => {
                  const r: EstimateItemResult | undefined = byId.get(it.id);
                  const n = i + 1;
                  const linesOpen = it.quantity_mode === "measured" && (openLines.has(it.id) || readOnly);
                  return (
                    <Fragment key={it.id}>
                      <tr className="border-t border-[var(--clp-border)]">
                        <td className={td}>{readOnly ? <span className="font-semibold">{r?.no ?? it.item_no}</span>
                          : <input className={input} aria-label={`Item number, item ${n}`} placeholder={r?.no ?? String(n)} value={it.item_no} onChange={(ev) => setItem(it.id, { item_no: ev.target.value })} />}</td>
                        <td className={td}>
                          {readOnly ? <div className="whitespace-pre-wrap">{it.description}</div>
                            : <textarea className={`${input} resize-y min-h-[30px]`} rows={it.description.length > 90 ? 3 : 1} aria-label={`Description, item ${n}`} value={it.description} onChange={(ev) => setItem(it.id, { description: ev.target.value })} />}
                          {sourceCaption(it) && <div className="text-[11px] text-[var(--clp-ink-3)] mt-0.5">{sourceCaption(it)}</div>}
                        </td>
                        <td className={td}>{readOnly ? it.unit : <input className={input} aria-label={`Unit, item ${n}`} value={it.unit} onChange={(ev) => setItem(it.id, { unit: ev.target.value })} />}</td>
                        <td className={td}>
                          {readOnly ? MODES.find((m) => m.value === it.quantity_mode)?.label : (
                            <select className={input} aria-label={`Quantity from, item ${n}`} value={it.quantity_mode} onChange={(ev) => {
                              const mode = ev.target.value as EstimateItem["quantity_mode"];
                              setItem(it.id, { quantity_mode: mode, quantity: r?.quantity ?? it.quantity });
                              if (mode === "measured") setOpenLines(new Set(openLines).add(it.id));
                            }}>{MODES.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}</select>)}
                          {it.quantity_mode === "measured" && !readOnly && (
                            <button type="button" className="mt-1 flex items-center gap-0.5 text-[11.5px] text-[var(--clp-accent)] bg-transparent border-0 p-0 cursor-pointer" onClick={() => toggle(it.id)}>
                              {openLines.has(it.id) ? <ExpandLessOutlined sx={{ fontSize: 15 }} /> : <ExpandMoreOutlined sx={{ fontSize: 15 }} />}
                              {it.measurements.length} measurement line{it.measurements.length === 1 ? "" : "s"}</button>
                          )}
                        </td>
                        <td className={`${td} text-right`}>
                          {it.quantity_mode === "direct" && !readOnly
                            ? <Num value={it.quantity} onChange={(v) => setItem(it.id, { quantity: v ?? 0 })} label={`Quantity, item ${n}`} width="w-full" />
                            : <span className="num inline-block pt-1">{r ? fmt(r.quantity, 3) : ""}</span>}
                        </td>
                        <td className={`${td} text-right`}>
                          {readOnly ? <span className="num">{fmt(it.rate)}</span> : (
                            <Num value={it.rate} label={`Rate, item ${n}`} width="w-full" onChange={(v) => setItem(it.id, {
                              rate: v ?? 0,
                              rate_source: it.rate_source.kind === "manual" ? it.rate_source : { ...it.rate_source, kind: "manual", sor_item_id: null, analysis_id: null, book_title: "" },
                            })} />)}
                        </td>
                        <td className={`${td} text-right num font-semibold pt-2`}>{r ? fmt(r.amount) : ""}</td>
                        {!readOnly && (
                          <td className={`${td} whitespace-nowrap text-right`}>
                            <IconButton size="small" aria-label={`Move item ${n} up`} disabled={i === 0} onClick={() => move(i, -1)}><ArrowUpwardOutlined fontSize="small" /></IconButton>
                            <IconButton size="small" aria-label={`Move item ${n} down`} disabled={i === items.length - 1} onClick={() => move(i, 1)}><ArrowDownwardOutlined fontSize="small" /></IconButton>
                            <IconButton size="small" aria-label={`Remove item ${n}`} onClick={() => setDoc({ items: items.filter((x) => x.id !== it.id) })}><DeleteOutlined fontSize="small" /></IconButton>
                          </td>
                        )}
                      </tr>

                      {it.quantity_mode === "design" && (
                        <tr><td />
                          <td colSpan={readOnly ? 6 : 7} className="pb-2 px-1.5">
                            <div className="flex flex-wrap items-center gap-2 text-[12px]">
                              {readOnly ? <span className="text-[var(--clp-ink-2)]">{it.design?.label}</span> : (
                                <select className={`${input} max-w-[640px]`} aria-label={`Design quantity, item ${n}`} value={it.design ? `${it.design.design_id}|${it.design.key}` : ""}
                                  onChange={(ev) => {
                                    const o = options.find((x) => x.value === ev.target.value);
                                    if (!o) return;
                                    setItem(it.id, { design: { design_id: o.design.design_id, key: o.key, revision: null, value: null, label: "" }, unit: it.unit || DESIGN_QUANTITY[o.key].unit });
                                  }}>
                                  <option value="" disabled>Choose the design and the quantity</option>
                                  {it.design && !options.some((o) => o.value === `${it.design!.design_id}|${it.design!.key}`) && (
                                    <option value={`${it.design.design_id}|${it.design.key}`}>{it.design.label || "A design no longer in the project"}</option>)}
                                  {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                                </select>)}
                              {it.design?.revision != null && (
                                <span className="text-[var(--clp-ink-3)]">taken at R{it.design.revision}: {fmt(it.design.value ?? 0)} {DESIGN_QUANTITY[it.design.key].unit}</span>)}
                              {it.design && it.design.revision == null && (
                                <span className="text-[var(--clp-ink-3)]">the design's current quantity, recorded with its revision when the estimate is saved</span>)}
                              {r?.stale && (
                                <span className="font-semibold text-[var(--clp-warn)]">{r.design_now ? `the design is now R${r.design_now.revision}, giving ${fmt(r.design_now.value)} ${DESIGN_QUANTITY[it.design!.key].unit}` : "the design is no longer in the project"}</span>)}
                            </div>
                          </td>
                        </tr>
                      )}

                      {linesOpen && (
                        <tr><td />
                          <td colSpan={readOnly ? 6 : 7} className="pb-3 px-1.5">
                            <table className="w-full text-[12px] border-collapse bg-[var(--clp-panel-2)] rounded" aria-label={`Measurements, item ${n}`}>
                              <thead><tr className="text-[10.5px] text-[var(--clp-ink-3)]">
                                <th className={th}>Measurement</th><th className={`${th} text-right`}>Nos</th><th className={`${th} text-right`}>Length</th><th className={`${th} text-right`}>Breadth</th>
                                <th className={`${th} text-right`}>Depth</th><th className={th}>Deduct</th><th className={`${th} text-right`}>Quantity</th>{!readOnly && <th />}</tr></thead>
                              <tbody>
                                {it.measurements.map((m, k) => {
                                  const tag = `item ${n} line ${k + 1}`;
                                  const q = r?.lines?.[k];
                                  return readOnly ? (
                                    <tr key={k}>
                                      <td className={td}>{m.description}</td>
                                      {[m.nos, m.length, m.breadth, m.depth].map((v, j) => <td key={j} className={`${td} text-right num`}>{v == null ? "" : fmt(v, 3)}</td>)}
                                      <td className={td}>{m.deduct ? "Deduct" : ""}</td>
                                      <td className={`${td} text-right num`}>{q !== undefined ? fmt(q) : ""}</td>
                                    </tr>
                                  ) : (
                                    <tr key={k}>
                                      <td className={td}><input className={input} aria-label={`Measurement, ${tag}`} value={m.description} placeholder="e.g. Footings F1 to F4" onChange={(ev) => setLine(it, k, { description: ev.target.value })} /></td>
                                      <td className={`${td} text-right`}><Num value={m.nos} label={`Nos, ${tag}`} onChange={(v) => setLine(it, k, { nos: v ?? 0 })} width="w-[64px]" /></td>
                                      <td className={`${td} text-right`}><Num value={m.length} blank label={`Length, ${tag}`} onChange={(v) => setLine(it, k, { length: v })} /></td>
                                      <td className={`${td} text-right`}><Num value={m.breadth} blank label={`Breadth, ${tag}`} onChange={(v) => setLine(it, k, { breadth: v })} /></td>
                                      <td className={`${td} text-right`}><Num value={m.depth} blank label={`Depth, ${tag}`} onChange={(v) => setLine(it, k, { depth: v })} /></td>
                                      <td className={td}><input type="checkbox" aria-label={`Deduct, ${tag}`} checked={m.deduct} onChange={(ev) => setLine(it, k, { deduct: ev.target.checked })} className="mt-1.5" /></td>
                                      <td className={`${td} text-right num pt-2 ${q !== undefined && q < 0 ? "text-[var(--clp-bad)]" : ""}`}>{q !== undefined ? fmt(q) : ""}</td>
                                      <td className={`${td} text-right`}><IconButton size="small" aria-label={`Remove ${tag}`} onClick={() => setItem(it.id, { measurements: it.measurements.filter((_, x) => x !== k) })}><DeleteOutlined fontSize="small" /></IconButton></td>
                                    </tr>
                                  );
                                })}
                              </tbody>
                            </table>
                            <div className="flex items-center gap-3 mt-1 text-[11.5px] text-[var(--clp-ink-3)]">
                              {!readOnly && <Button size="small" startIcon={<AddOutlined />} aria-label={`Add a measurement line, item ${n}`}
                                onClick={() => setItem(it.id, { measurements: [...it.measurements, it.measurements.length ? { ...it.measurements[it.measurements.length - 1], description: "", deduct: false } : blankLine()] })}>Add line</Button>}
                              <span>A blank dimension is not measured; each line is rounded to 0.01 and a deduction is taken off.</span>
                            </div>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <Card title="Abstract">
          <div className="p-3 flex flex-col gap-2">
            <table className="w-full text-[13px] border-collapse" aria-label="Abstract">
              <tbody>
                <tr><td className="py-1">Cost of the items</td><td /><td className="py-1 text-right num">{fmt(ab?.subtotal ?? 0)}</td><td /></tr>
                {draft.doc.additions.map((a, k) => (
                  <tr key={k}>
                    <td className="py-1 pr-2">{readOnly ? a.label : <input className={input} aria-label={`Label, addition ${k + 1}`} value={a.label} placeholder="e.g. Contingencies"
                      onChange={(ev) => setDoc({ additions: draft.doc.additions.map((x, j) => (j === k ? { ...x, label: ev.target.value } : x)) })} />}</td>
                    <td className="py-1 pr-2 w-[110px]">{readOnly ? <span className="num">{fmt(a.pct)} %</span> : (
                      <span className="flex items-center gap-1"><Num value={a.pct} label={`Percentage, addition ${k + 1}`} onChange={(v) => setDoc({ additions: draft.doc.additions.map((x, j) => (j === k ? { ...x, pct: v ?? 0 } : x)) })} width="w-[80px]" />%</span>)}</td>
                    <td className="py-1 text-right num">{ab && ab.additions.length === draft.doc.additions.length ? fmt(ab.additions[k].amount) : ""}</td>
                    <td className="w-[36px] text-right">{!readOnly && <IconButton size="small" aria-label={`Remove addition ${k + 1}`} onClick={() => setDoc({ additions: draft.doc.additions.filter((_, j) => j !== k) })}><DeleteOutlined fontSize="small" /></IconButton>}</td>
                  </tr>
                ))}
                <tr className="border-t border-[var(--clp-border)] font-semibold"><td className="py-1.5">Total</td><td /><td className="py-1.5 text-right num">{fmt(ab?.total ?? 0)}</td><td /></tr>
                <tr className="font-semibold"><td className="py-1">Say</td><td /><td className="py-1 text-right num">Rs {fmt(ab?.rounded ?? 0, 0)}</td><td /></tr>
              </tbody>
            </table>
            {!readOnly && <div><Button size="small" startIcon={<AddOutlined />} onClick={() => setDoc({ additions: [...draft.doc.additions, { label: "", pct: 0 }] })}>Add a percentage addition</Button></div>}
            <div className="text-[11.5px] text-[var(--clp-ink-3)]">Each amount is the quantity times the rate, rounded to the paisa; additions are percentages of the cost of the items, and the total is rounded to the rupee.</div>
          </div>
        </Card>
        <Card title="Notes and record">
          <div className="p-3 flex flex-col gap-3">
            {readOnly ? <div className="whitespace-pre-wrap text-[13px]">{draft.notes || <span className="text-[var(--clp-ink-3)]">No notes.</span>}</div>
              : <TextField label="Notes" multiline minRows={3} value={draft.notes} onChange={(ev) => setDraft({ ...draft, notes: ev.target.value })} placeholder="Basis of the estimate, the schedule and its cost index, exclusions" />}
            <div className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-[12.5px]">
              <span className="text-[var(--clp-ink-3)]">Prepared by</span><span>{e.prepared_by_name || "-"}</span>
              <span className="text-[var(--clp-ink-3)]">Issued by</span><span>{e.issued_by_name ? `${e.issued_by_name}, ${fmtDate(e.issued_at)}` : "-"}</span>
              <span className="text-[var(--clp-ink-3)]">Project</span><span><Link to={`/projects/${e.project_id}`} className="text-[var(--clp-accent)]">{project.data ? `${project.data.code}  ${project.data.name}` : "Open"}</Link></span>
            </div>
          </div>
        </Card>
      </div>

      <SorPicker open={picker === "sor"} onClose={() => setPicker("")} onPick={fromSor} />
      <PickDialog open={picker === "analysis"} onClose={() => setPicker("")} title="Add an item from a rate analysis"
        empty={<>No rate analysis yet: write one on the <Link to="/estimation">Quantity estimation</Link> page.</>}
        rows={(analyses.data ?? []).map((a) => ({ key: a.id, main: a.title, sub: `per ${a.unit}`, right: `Rs ${fmt(a.rate)}`, label: `Add ${a.title}`, onAdd: () => fromAnalysis(a) }))} />
      <PickDialog open={picker === "design"} onClose={() => setPicker("")} title="Add a quantity from a design"
        empty="No design in this project reports quantities yet."
        rows={options.map((o) => ({ key: o.value, main: `${o.design.name}: ${DESIGN_QUANTITY[o.key].label.toLowerCase()}`, sub: `${o.design.title}, R${o.design.revision}`,
          right: `${fmt(o.qty)} ${DESIGN_QUANTITY[o.key].unit}`, label: `Add ${DESIGN_QUANTITY[o.key].label.toLowerCase()} of ${o.design.name}`, onAdd: () => fromDesign(o.design, o.key) }))} />
    </div>
  );
}
