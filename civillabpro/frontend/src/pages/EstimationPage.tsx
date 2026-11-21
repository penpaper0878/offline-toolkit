import AddOutlined from "@mui/icons-material/AddOutlined";
import DeleteOutlined from "@mui/icons-material/DeleteOutlined";
import ManageSearchOutlined from "@mui/icons-material/ManageSearchOutlined";
import UploadFileOutlined from "@mui/icons-material/UploadFileOutlined";
import Button from "@mui/material/Button";
import IconButton from "@mui/material/IconButton";
import Tooltip from "@mui/material/Tooltip";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api, type ApiError } from "../api/client";
import { useEstimates, useInvalidatingMutation, useProjects, useRateAnalyses, useSorBooks } from "../api/hooks";
import type { RateAnalysis } from "../api/types";
import { Card, Empty, PageHeader } from "../components/Card";
import { EstimateStatus, NewEstimateDialog } from "../components/EstimateCommon";
import { ImportSorDialog, RateAnalysisDialog, SorPicker } from "../components/Estimation";
import { fmt, fmtDate, timeAgo } from "../lib/format";
import { useTab } from "../shell/hooks";
import { useAuth } from "../stores/auth";
import { useUi } from "../stores/ui";

const th = "py-2 px-2 font-semibold";
const td = "py-1.5 px-2";

export function EstimationPage() {
  useTab("Quantity estimation");
  const can = useAuth((s) => s.can);
  const notify = useUi((s) => s.notify);
  const estimates = useEstimates();
  const books = useSorBooks();
  const analyses = useRateAnalyses();
  const projects = useProjects();
  const [newOpen, setNewOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [browse, setBrowse] = useState(false);
  const [analysis, setAnalysis] = useState<RateAnalysis | null | undefined>(undefined);
  const removeBook = useInvalidatingMutation((id: string) => api<void>(`/sor-books/${id}`, { method: "DELETE" }));
  const removeAnalysis = useInvalidatingMutation((id: string) => api<void>(`/rate-analyses/${id}`, { method: "DELETE" }));
  const fail = (e: unknown) => notify((e as ApiError).message, "error");
  const projectName = (id: string) => { const p = projects.data?.items.find((x) => x.id === id); return p ? `${p.code}  ${p.name}` : ""; };

  return (
    <div className="p-5 max-w-[1400px] mx-auto flex flex-col gap-3">
      <PageHeader title="Quantity estimation" subtitle="Estimates priced from schedules of rates and rate analyses, their quantities measured or taken from the designs.">
        {can("estimate:write") && <Button variant="contained" startIcon={<AddOutlined />} onClick={() => setNewOpen(true)}>New estimate</Button>}
      </PageHeader>

      <Card title="Estimates">
        {(estimates.data ?? []).length === 0 ? (
          <Empty title="No estimates yet"><span>Start one in a project; its items can take their quantities from the project's designs.</span></Empty>
        ) : (
          <table className="w-full text-[13px] border-collapse">
            <thead><tr className="text-left text-[11px] text-[var(--clp-ink-3)] border-b border-[var(--clp-border)]">
              <th className={th}>Estimate</th><th className={th}>Project</th><th className={th}>Status</th><th className={`${th} text-right`}>Items</th>
              <th className={`${th} text-right`}>Total (Rs)</th><th className={th}>Prepared by</th><th className={th}>Updated</th></tr></thead>
            <tbody>
              {estimates.data!.map((e) => (
                <tr key={e.id} className="border-b border-[var(--clp-border)] last:border-0 hover:bg-[var(--clp-panel-2)]">
                  <td className={td}><Link to={`/estimates/${e.id}`} className="font-semibold text-[var(--clp-accent)] no-underline hover:underline">{e.title}</Link></td>
                  <td className={td}><Link to={`/projects/${e.project_id}`} className="text-[var(--clp-ink-2)] no-underline hover:underline">{projectName(e.project_id)}</Link></td>
                  <td className={td}><EstimateStatus status={e.status} revision={e.revision} /></td>
                  <td className={`${td} text-right num`}>{e.item_count}</td>
                  <td className={`${td} text-right num font-semibold`}>{fmt(e.total, 0)}</td>
                  <td className={`${td} text-[var(--clp-ink-2)]`}>{e.prepared_by_name}</td>
                  <td className={`${td} text-[var(--clp-ink-2)]`} title={fmtDate(e.updated_at)}>{timeAgo(e.updated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
        <Card title="Schedules of rates" action={<>
          {(books.data ?? []).length > 0 && <Button size="small" startIcon={<ManageSearchOutlined />} onClick={() => setBrowse(true)}>Browse</Button>}
          {can("rates:manage") && <Button size="small" variant="contained" startIcon={<UploadFileOutlined />} onClick={() => setImportOpen(true)}>Import a schedule</Button>}
        </>}>
          {(books.data ?? []).length === 0 ? (
            <Empty title="No schedule of rates imported">
              <span>Import your state's schedule, or CPWD's, from a CSV file or an Excel workbook: code, description, unit and rate.</span>
            </Empty>
          ) : (
            <table className="w-full text-[13px] border-collapse">
              <thead><tr className="text-left text-[11px] text-[var(--clp-ink-3)] border-b border-[var(--clp-border)]">
                <th className={th}>Schedule</th><th className={th}>Authority, state, year</th><th className={`${th} text-right`}>Items</th><th /></tr></thead>
              <tbody>
                {books.data!.map((b) => (
                  <tr key={b.id} className="border-b border-[var(--clp-border)] last:border-0">
                    <td className={td}><div className="font-semibold">{b.title}</div><div className="text-[11px] text-[var(--clp-ink-3)]">from {b.source_name}</div></td>
                    <td className={`${td} text-[var(--clp-ink-2)]`}>{[b.authority, b.state, b.year].filter(Boolean).join(", ")}</td>
                    <td className={`${td} text-right num`}>{b.item_count}</td>
                    <td className={`${td} text-right`}>{can("rates:manage") && (
                      <Tooltip title="Delete the schedule (estimates keep their rates)"><IconButton aria-label={`Delete ${b.title}`} onClick={() => {
                        if (window.confirm(`Delete the schedule ${b.title}? Estimates already priced from it keep their rates.`)) removeBook.mutate(b.id, { onError: fail });
                      }}><DeleteOutlined fontSize="small" /></IconButton></Tooltip>)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>

        <Card title="Rate analyses" action={can("rates:manage") && <Button size="small" variant="contained" startIcon={<AddOutlined />} onClick={() => setAnalysis(null)}>New rate analysis</Button>}>
          {(analyses.data ?? []).length === 0 ? (
            <Empty title="No rate analyses"><span>Analyse a rate from its materials, labour, plant and sundries, with water charges and overheads and profit.</span></Empty>
          ) : (
            <table className="w-full text-[13px] border-collapse">
              <thead><tr className="text-left text-[11px] text-[var(--clp-ink-3)] border-b border-[var(--clp-border)]">
                <th className={th}>Item</th><th className={th}>Unit</th><th className={`${th} text-right`}>Rate (Rs)</th><th /></tr></thead>
              <tbody>
                {analyses.data!.map((a) => (
                  <tr key={a.id} className="border-b border-[var(--clp-border)] last:border-0">
                    <td className={td}><button type="button" className="text-left font-semibold text-[var(--clp-accent)] bg-transparent border-0 p-0 cursor-pointer hover:underline" onClick={() => setAnalysis(a)}>{a.title}</button></td>
                    <td className={td}>{a.unit}</td>
                    <td className={`${td} text-right num`}>{fmt(a.rate)}</td>
                    <td className={`${td} text-right`}>{can("rates:manage") && (
                      <Tooltip title="Delete the analysis"><IconButton aria-label={`Delete ${a.title}`} onClick={() => {
                        if (window.confirm(`Delete the rate analysis ${a.title}?`)) removeAnalysis.mutate(a.id, { onError: fail });
                      }}><DeleteOutlined fontSize="small" /></IconButton></Tooltip>)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      </div>

      <NewEstimateDialog open={newOpen} onClose={() => setNewOpen(false)} />
      <ImportSorDialog open={importOpen} onClose={() => setImportOpen(false)} />
      <SorPicker open={browse} onClose={() => setBrowse(false)} browseOnly />
      <RateAnalysisDialog open={analysis !== undefined} onClose={() => setAnalysis(undefined)} analysis={analysis ?? null} />
    </div>
  );
}
