import DescriptionOutlined from "@mui/icons-material/DescriptionOutlined";
import DesignServicesOutlined from "@mui/icons-material/DesignServicesOutlined";
import DashboardCustomizeOutlined from "@mui/icons-material/DashboardCustomizeOutlined";
import PictureAsPdfOutlined from "@mui/icons-material/PictureAsPdfOutlined";
import RestoreOutlined from "@mui/icons-material/RestoreOutlined";
import SaveOutlined from "@mui/icons-material/SaveOutlined";
import TableChartOutlined from "@mui/icons-material/TableChartOutlined";
import VerifiedOutlined from "@mui/icons-material/VerifiedOutlined";
import LinearProgress from "@mui/material/LinearProgress";
import { useColorScheme } from "@mui/material/styles";
import { DockviewReact, type DockviewApi, type DockviewReadyEvent, type IDockviewPanelProps, themeDark, themeLight } from "dockview-react";
import "dockview-react/dist/styles/dockview.css";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, ApiError, download } from "../api/client";
import { useCalculation, useDesign, useElements, useInvalidatingMutation, useProject } from "../api/hooks";
import type { Design, DesignResult, DrawingView, ElementSpec } from "../api/types";
import { CalcSheet, ChecksTable, Flags } from "../components/CalcSheet";
import { DrawingCanvas } from "../components/DrawingCanvas";
import { Unit } from "../components/Fx";
import { PropertyGrid, validateAll, type Values } from "../components/PropertyGrid";
import { ChartView } from "../components/ChartView";
import { BbsTable, QuantitiesPanel } from "../components/Schedule";
import { ReviewChip, StatusChip } from "../components/Status";
import { fmt, titleCase } from "../lib/format";
import { isTyping, useRibbon, useTab } from "../shell/hooks";
import { useAuth } from "../stores/auth";
import { useUi } from "../stores/ui";

interface Workspace {
  spec: ElementSpec;
  values: Values;
  errors: Record<string, string>;
  setValue: (key: string, value: unknown) => void;
  result: DesignResult | undefined;
  readOnly: boolean;
  /** The view each drawing panel shows when the drawing has more views than there are panels (a beam of many spans). */
  picks: Record<string, string>;
  setPick: (panel: string, viewId: string) => void;
}
const Ctx = createContext<Workspace | null>(null);
const useWorkspace = () => useContext(Ctx)!;

const DRAWING_PANELS = ["section", "elevation"] as const;
/** The view a drawing panel shows: the one picked for it, or the view in its own place (first, second). */
function viewFor(views: DrawingView[] | undefined, panel: string, picks: Record<string, string>): DrawingView | undefined {
  if (!views?.length) return undefined;
  return views.find((v) => v.id === picks[panel]) ?? views[DRAWING_PANELS.indexOf(panel as (typeof DRAWING_PANELS)[number])];
}

function DrawingPanel({ panel, missing }: { panel: string; missing: string }) {
  const w = useWorkspace();
  const views = w.result?.drawing?.views;
  const view = viewFor(views, panel, w.picks);
  if (!view || !views) return <Scroll><Missing what={missing} /></Scroll>;
  return (
    <div className="h-full flex flex-col bg-[var(--clp-panel)]">
      {views.length > DRAWING_PANELS.length && (
        <div className="shrink-0 px-2 py-1 border-b border-[var(--clp-border)] flex items-center gap-2 text-[12px]">
          <label htmlFor={`view-${panel}`} className="text-[var(--clp-ink-3)]">View</label>
          <select id={`view-${panel}`} value={view.id} onChange={(e) => w.setPick(panel, e.target.value)}
            className="h-6 px-1 bg-transparent border border-[var(--clp-border)] rounded text-[12px] text-[var(--clp-ink)] cursor-pointer">
            {views.map((v) => <option key={v.id} value={v.id}>{v.title}</option>)}
          </select>
        </div>
      )}
      <div className="flex-1 min-h-0"><DrawingCanvas view={view} /></div>
    </div>
  );
}

const Missing = ({ what }: { what: string }) => <div className="p-4 text-[var(--clp-ink-3)]">{what} appears once the calculation runs through.</div>;
const Scroll = ({ children }: { children: React.ReactNode }) => <div className="h-full overflow-auto bg-[var(--clp-panel)] text-[var(--clp-ink)]">{children}</div>;

// Dock panels. Each reads the shared workspace, so any panel can be moved, tabbed, split or floated.
const PANELS: Record<string, React.FunctionComponent<IDockviewPanelProps>> = {
  properties: () => { const w = useWorkspace(); return <Scroll><PropertyGrid properties={w.spec.input_schema.properties} values={w.values} errors={w.errors} onChange={w.setValue} disabled={w.readOnly} /></Scroll>; },
  // The two drawing panels show the element's first and second views (a section for members, a plan for slabs and
  // footings), or any view picked in them where there are more; their tab titles follow the views' titles. The panel ids
  // stay fixed so saved layouts keep working.
  section: () => <DrawingPanel panel="section" missing="The drawing" />,
  elevation: () => <DrawingPanel panel="elevation" missing="The second view" />,
  calculation: () => { const r = useWorkspace().result; return <Scroll>{r ? <CalcSheet sheet={r.sheet} /> : <Missing what="The calculation sheet" />}</Scroll>; },
  checks: () => { const r = useWorkspace().result; return <Scroll>{r ? <ChecksTable sheet={r.sheet} /> : <Missing what="The list of checks" />}</Scroll>; },
  bbs: () => { const r = useWorkspace().result; return <Scroll>{r?.bbs ? <BbsTable bbs={r.bbs} /> : <Missing what="The bar bending schedule" />}</Scroll>; },
  quantities: () => { const r = useWorkspace().result; return <Scroll>{r?.quantities ? <QuantitiesPanel q={r.quantities} /> : <Missing what="The quantity take-off" />}</Scroll>; },
  charts: () => {
    const r = useWorkspace().result;
    if (!r) return <Scroll><Missing what="The charts" /></Scroll>;
    if (!r.charts?.length) return <Scroll><div className="p-4 text-[var(--clp-ink-3)]">This element has no charts{r.status === "stopped" ? " while the calculation is stopped" : ""}.</div></Scroll>;
    return <Scroll><div className="@container"><div className="grid grid-cols-1 @3xl:grid-cols-2">{r.charts.map((c) => <ChartView key={c.id} chart={c} />)}</div></div></Scroll>;
  },
};

const LAYOUT_KEY = (type: string) => `clp.layout.${type}.v4`;

function defaultLayout(dock: DockviewApi) {
  dock.clear();
  // Inputs on the left; drawings above the results so wide views and tables both get the full width.
  dock.addPanel({ id: "properties", component: "properties", title: "Properties", initialWidth: 340 });
  dock.addPanel({ id: "section", component: "section", title: "Section", position: { referencePanel: "properties", direction: "right" } });
  dock.addPanel({ id: "elevation", component: "elevation", title: "Elevation", position: { referencePanel: "section", direction: "within" }, inactive: true });
  dock.addPanel({ id: "charts", component: "charts", title: "Charts", position: { referencePanel: "section", direction: "within" }, inactive: true });
  dock.addPanel({ id: "calculation", component: "calculation", title: "Calculation", position: { referencePanel: "section", direction: "below" } });
  dock.addPanel({ id: "checks", component: "checks", title: "Checks", position: { referencePanel: "calculation", direction: "within" }, inactive: true });
  dock.addPanel({ id: "bbs", component: "bbs", title: "Bar schedule", position: { referencePanel: "calculation", direction: "within" }, inactive: true });
  dock.addPanel({ id: "quantities", component: "quantities", title: "Quantities", position: { referencePanel: "calculation", direction: "within" }, inactive: true });
  // Sizes are set once every group exists: the property grid keeps a fixed width, the drawings take the upper 45 %.
  dock.getPanel("properties")?.group.api.setSize({ width: 340 });
  dock.getPanel("section")?.group.api.setSize({ height: Math.max(260, Math.round(dock.height * 0.45)) });
}

/** Name the two drawing tabs after the views they show ("Plan", "Section A-A", ...). */
function applyViewTitles(dock: DockviewApi | null, titles: string) {
  if (!dock || !titles) return;
  titles.split("\n").slice(0, 2).forEach((title, i) => { if (title) dock.getPanel(DRAWING_PANELS[i])?.api.setTitle(title); });
}

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => { const t = setTimeout(() => setV(value), ms); return () => clearTimeout(t); }, [value, ms]);
  return v;
}

export function DesignWorkspacePage() {
  const { designId, projectId: newProjectId, elementType: newType } = useParams();
  const saved = useDesign(designId);
  const elements = useElements();
  const elementType = saved.data?.element_type ?? newType;
  const spec = elements.data?.find((e) => e.type === elementType);
  const projectId = saved.data?.project_id ?? newProjectId;
  const project = useProject(projectId);
  const can = useAuth((s) => s.can);
  const notify = useUi((s) => s.notify);
  const navigate = useNavigate();
  const { mode, systemMode } = useColorScheme();
  const dark = (mode === "system" ? systemMode : mode) === "dark";

  // Inputs start from the saved design or the element's worked example, then live here until saved.
  const [values, setValues] = useState<Values | null>(null);
  const baseline = saved.data?.inputs ?? spec?.defaults;
  const baselineKey = `${designId ?? "new"}:${saved.data?.revision ?? ""}:${elementType ?? ""}`;
  useEffect(() => { if (baseline) setValues({ ...baseline }); /* reset only when the document changes */ // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [baselineKey, !!baseline]);

  const errors = useMemo(() => (spec && values ? validateAll(spec.input_schema.properties, values) : {}), [spec, values]);
  const valid = Object.keys(errors).length === 0;
  const settled = useDebounced(values, 300);
  // Validate the values that are sent, not the ones on screen: after a pause on an invalid entry, the debounced
  // copy still holds it for 300 ms once the screen is corrected, and would otherwise reach the server.
  const settledValid = useMemo(() => !!spec && !!settled && Object.keys(validateAll(spec.input_schema.properties, settled)).length === 0, [spec, settled]);
  const calc = useCalculation(elementType, settledValid ? settled : null);
  const serverErrors = useMemo(() => {
    const out: Record<string, string> = {};
    if (calc.error instanceof ApiError) for (const d of calc.error.details) if (d.field) out[d.field] = d.message;
    return out;
  }, [calc.error]);
  const result = calc.data;

  const dirty = !!values && !!baseline && (!designId || JSON.stringify(values) !== JSON.stringify(baseline));
  const name = String(values?.mark ?? saved.data?.name ?? spec?.title ?? "");
  const readOnly = !can("design:write");
  useTab(spec ? `${spec.title} ${name}${designId ? "" : " (new)"}` : undefined);

  const setValue = useCallback((key: string, value: unknown) => setValues((v) => (v ? { ...v, [key]: value } : v)), []);
  const fail = useCallback((e: unknown) => notify((e as Error).message, "error"), [notify]);

  const save = useInvalidatingMutation(async () => {
    if (!values || !spec) throw new Error("Nothing to save.");
    if (designId) return api<Design>(`/designs/${designId}`, { method: "PUT", body: { name, inputs: values } });
    return api<Design>(`/projects/${projectId}/designs`, { method: "POST", body: { element_type: spec.type, name, inputs: values } });
  });
  const approve = useInvalidatingMutation(() => api<Design>(`/designs/${designId}/approve`, { method: "POST" }));

  const canSave = !readOnly && valid && dirty && !save.isPending && !!result;
  const doSave = useCallback(() => {
    if (!canSave) return;
    save.mutate(undefined, {
      onSuccess: (d) => {
        notify(designId ? `Saved as revision R${d.revision}` : `${titleCase(d.element_type)} ${d.name} saved`, "success");
        if (!designId) { useUi.getState().closeTab(window.location.pathname); navigate(`/designs/${d.id}`, { replace: true }); }
      },
      onError: fail,
    });
  }, [canSave, save, notify, designId, navigate, fail]);

  const issued = !!designId && !dirty; // exports always describe a saved revision
  const doExport = useCallback((file: string) => { download(`/designs/${designId}/${file}`, file).catch(fail); }, [designId, fail]);
  const dockRef = useRef<DockviewApi | null>(null);
  const titlesRef = useRef("");
  const resetLayout = useCallback(() => {
    if (!dockRef.current) return;
    defaultLayout(dockRef.current);
    applyViewTitles(dockRef.current, titlesRef.current);
  }, []);

  const canApprove = issued && can("design:approve") && saved.data?.status === "ok" && saved.data?.review_status === "draft";
  const exportHint = issued ? undefined : "Save the design first: reports are issued from a saved revision";
  useRibbon("Design", () => [
    { title: "File", actions: [
      { id: "save", label: designId ? "Save revision" : "Save", icon: <SaveOutlined />, onClick: doSave, disabled: !canSave, shortcut: "Ctrl S", primary: true },
      { id: "revert", label: "Revert", icon: <RestoreOutlined />, onClick: () => baseline && setValues({ ...baseline }), disabled: !dirty || !designId, hint: "Discard changes since the last save" },
    ] },
    { title: "Issue", actions: [
      { id: "pdf", label: "Report PDF", icon: <PictureAsPdfOutlined />, onClick: () => doExport("report.pdf"), disabled: !issued, hint: exportHint ?? "Calculation report, A4", shortcut: "Alt R" },
      { id: "xlsx", label: "BBS Excel", icon: <TableChartOutlined />, onClick: () => doExport("bbs.xlsx"), disabled: !issued || !saved.data?.result.bbs, hint: exportHint ?? "Bar bending schedule" },
      { id: "dxf", label: "Drawing DXF", icon: <DesignServicesOutlined />, onClick: () => doExport("drawing.dxf"), disabled: !issued || !saved.data?.result.drawing, hint: exportHint ?? "Reinforcement drawing for CAD" },
    ] },
    { title: "Review", actions: [
      { id: "approve", label: "Approve", icon: <VerifiedOutlined />, onClick: () => approve.mutate(undefined, { onSuccess: () => notify("Design approved", "success"), onError: fail }), disabled: !canApprove,
        hint: "A checker other than the designer approves a saved design with every check OK" },
    ] },
    { title: "View", actions: [
      { id: "layout", label: "Reset layout", icon: <DashboardCustomizeOutlined />, onClick: resetLayout },
      { id: "project", label: "Project", icon: <DescriptionOutlined />, onClick: () => navigate(`/projects/${projectId}`) },
    ] },
  ], [designId, canSave, dirty, issued, canApprove, doSave, doExport, projectId, saved.data, baseline]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); doSave(); }
      if (e.altKey && e.key.toLowerCase() === "r" && issued && !isTyping(e.target)) { e.preventDefault(); doExport("report.pdf"); }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [doSave, doExport, issued]);

  const onReady = useCallback((e: DockviewReadyEvent) => {
    dockRef.current = e.api;
    const key = LAYOUT_KEY(elementType ?? "");
    let restored = false;
    try {
      const raw = localStorage.getItem(key);
      if (raw) { e.api.fromJSON(JSON.parse(raw)); restored = true; }
    } catch { restored = false; }
    if (!restored) defaultLayout(e.api);
    applyViewTitles(e.api, titlesRef.current);
    e.api.onDidLayoutChange(() => { try { localStorage.setItem(key, JSON.stringify(e.api.toJSON())); } catch { /* layout not remembered */ } });
  }, [elementType]);

  const [picks, setPicks] = useState<Record<string, string>>({});
  useEffect(() => setPicks({}), [elementType]);
  const setPick = useCallback((panel: string, viewId: string) => setPicks((p) => ({ ...p, [panel]: viewId })), []);
  const viewTitles = DRAWING_PANELS.map((pn) => viewFor(result?.drawing?.views, pn, picks)?.title ?? "").join("\n");
  useEffect(() => { titlesRef.current = viewTitles; applyViewTitles(dockRef.current, viewTitles); }, [viewTitles]);

  if (saved.error) return <div className="p-6 text-[var(--clp-bad)]" role="alert">{(saved.error as Error).message} <Link to="/projects">Back to projects</Link></div>;
  if (elements.isSuccess && elementType && !spec) return <div className="p-6 text-[var(--clp-bad)]" role="alert">This server has no designer for "{elementType}".</div>;
  if (!spec || !values) return <div className="p-6 text-[var(--clp-ink-3)]">Opening design</div>;

  const workspace: Workspace = { spec, values, errors: { ...serverErrors, ...errors }, setValue, result, readOnly, picks, setPick };
  const stale = !valid || calc.isError;
  return (
    <Ctx.Provider value={workspace}>
      <div className="h-full flex flex-col">
        <div className="no-print shrink-0 px-4 py-2 border-b border-[var(--clp-border)] bg-[var(--clp-panel)]">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
            <div className="min-w-0">
              <div className="text-[11px] text-[var(--clp-ink-3)] truncate">
                {project.data ? <Link to={`/projects/${project.data.id}`} className="text-inherit no-underline hover:underline">{project.data.code} {project.data.name}</Link> : "Project"}
              </div>
              <div className="flex items-center gap-2">
                <h1 className="m-0 text-[15px] font-semibold">{spec.title} {name}</h1>
                {designId ? <span className="text-xs text-[var(--clp-ink-2)] num">R{saved.data?.revision}</span> : <span className="text-xs text-[var(--clp-ink-3)]">not saved</span>}
                {dirty && designId && <span className="text-xs text-[var(--clp-warn)] font-semibold">unsaved changes</span>}
                {designId && saved.data && !dirty && <ReviewChip status={saved.data.review_status} />}
              </div>
            </div>
            {result && (
              <div className={`flex flex-wrap items-center gap-x-5 gap-y-1 ml-auto ${stale ? "opacity-45" : ""}`} aria-live="polite">
                <div><StatusChip status={result.status} size="md" /><div className="text-[11px] text-[var(--clp-ink-3)] num">{result.checks_passed} of {result.checks_total} checks OK</div></div>
                {result.max_utilisation !== null && <div><div className={`text-sm font-semibold num ${result.max_utilisation > 1 ? "text-[var(--clp-bad)]" : ""}`}>{result.max_utilisation.toFixed(2)}</div><div className="text-[11px] text-[var(--clp-ink-3)]">highest utilisation</div></div>}
                {result.key_results.slice(0, 6).map((k) => (
                  <div key={k.label}><div className="text-sm font-semibold num whitespace-nowrap">{fmt(k.value, k.dp)} <span className="text-[11px] font-normal text-[var(--clp-ink-2)]"><Unit>{k.unit}</Unit></span></div><div className="text-[11px] text-[var(--clp-ink-3)]">{k.label}</div></div>
                ))}
              </div>
            )}
          </div>
          {!valid && <div className="mt-1 text-xs text-[var(--clp-bad)]" role="alert">Correct the highlighted inputs: the results shown are from the last valid entry.</div>}
          {calc.isError && valid && <div className="mt-1 text-xs text-[var(--clp-bad)]" role="alert">{(calc.error as Error).message}</div>}
          {result?.status === "stopped" && <div className="mt-2"><Flags flags={result.sheet.flags.filter((f) => f.level === "error")} /></div>}
        </div>
        <div className="h-0.5 shrink-0">{calc.isFetching && <LinearProgress sx={{ height: 2 }} />}</div>
        <div className="flex-1 min-h-0">
          <DockviewReact className="clp-dock" theme={dark ? themeDark : themeLight} components={PANELS} onReady={onReady} />
        </div>
      </div>
    </Ctx.Provider>
  );
}
