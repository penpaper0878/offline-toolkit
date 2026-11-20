import AddOutlined from "@mui/icons-material/AddOutlined";
import DeleteOutlined from "@mui/icons-material/DeleteOutlined";
import DownloadOutlined from "@mui/icons-material/DownloadOutlined";
import PictureAsPdfOutlined from "@mui/icons-material/PictureAsPdfOutlined";
import Button from "@mui/material/Button";
import IconButton from "@mui/material/IconButton";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, type ApiError, download } from "../api/client";
import { useDesigns, useElements, useInvalidatingMutation, useProject } from "../api/hooks";
import type { Project } from "../api/types";
import { Card, Empty, PageHeader } from "../components/Card";
import { ReviewChip, StatusChip, Utilisation } from "../components/Status";
import { fmtDate, timeAgo, titleCase } from "../lib/format";
import { useTab } from "../shell/hooks";
import { useAuth } from "../stores/auth";
import { useUi } from "../stores/ui";
import { PROJECT_STATUSES } from "./ProjectsPage";

export function ProjectDetailPage() {
  const { projectId } = useParams();
  const project = useProject(projectId);
  const designs = useDesigns(projectId);
  const elements = useElements();
  const can = useAuth((s) => s.can);
  const notify = useUi((s) => s.notify);
  const navigate = useNavigate();
  useTab(project.data ? `${project.data.code} ${project.data.name}` : undefined);

  const fail = (e: unknown) => notify((e as ApiError).message, "error");
  const setStatus = useInvalidatingMutation((status: string) => api<Project>(`/projects/${projectId}`, { method: "PATCH", body: { status } }));
  const removeDesign = useInvalidatingMutation((id: string) => api<void>(`/designs/${id}`, { method: "DELETE" }));
  const removeProject = useInvalidatingMutation(() => api<void>(`/projects/${projectId}`, { method: "DELETE" }));

  if (project.error) return <div className="p-6 text-[var(--clp-bad)]" role="alert">{(project.error as Error).message} <Link to="/projects">Back to projects</Link></div>;
  if (!project.data) return <div className="p-6 text-[var(--clp-ink-3)]">Loading project</div>;
  const p = project.data;

  return (
    <div className="p-5 max-w-[1400px] mx-auto">
      <PageHeader title={`${p.code}  ${p.name}`} subtitle={[p.client, p.location, p.state].filter(Boolean).join(", ") || titleCase(p.project_type)}>
        <TextField select value={p.status} disabled={!can("project:write")} onChange={(e) => setStatus.mutate(e.target.value, { onError: fail })} sx={{ width: 140 }} slotProps={{ htmlInput: { "aria-label": "Project status" } }}>
          {PROJECT_STATUSES.map((t) => <MenuItem key={t} value={t}>{titleCase(t)}</MenuItem>)}
        </TextField>
        {can("design:read") && (
          <Button startIcon={<DownloadOutlined />} onClick={() => download(`/projects/${p.id}/export`, `${p.code}.clp.json`).catch(fail)}>Export project</Button>
        )}
        {can("project:delete") && (
          <Button color="error" onClick={() => {
            if (window.confirm(`Delete project ${p.code} and its ${p.design_count} design(s)? This cannot be undone.`)) {
              removeProject.mutate(undefined, { onSuccess: () => { notify(`Project ${p.code} deleted`, "success"); navigate("/projects"); }, onError: fail });
            }
          }}>Delete project</Button>
        )}
      </PageHeader>

      <Card
        title="Structural designs"
        action={can("design:write") && elements.data?.map((e) => (
          <Button key={e.type} variant="contained" startIcon={<AddOutlined />} component={Link} to={`/projects/${p.id}/designs/new/${e.type}`}>New {e.title}</Button>
        ))}
      >
        {designs.isLoading ? <div className="p-4 text-[var(--clp-ink-3)]">Loading designs</div>
          : (designs.data ?? []).length === 0 ? (
            <Empty title="No designs in this project yet">
              <span>Start with a member; its calculation, bar schedule and drawing are produced together.</span>
            </Empty>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-[13px] border-collapse">
                <thead>
                  <tr className="text-left text-[11px] text-[var(--clp-ink-3)] border-b border-[var(--clp-border)]">
                    <th className="py-2 px-3 font-semibold">Member</th><th className="py-2 px-2 font-semibold">Rev.</th><th className="py-2 px-2 font-semibold">Result</th>
                    <th className="py-2 px-2 font-semibold">Utilisation</th><th className="py-2 px-2 font-semibold">Review</th><th className="py-2 px-2 font-semibold">Designed by</th>
                    <th className="py-2 px-2 font-semibold">Updated</th><th className="py-2 px-3" />
                  </tr>
                </thead>
                <tbody>
                  {designs.data!.map((d) => (
                    <tr key={d.id} className="border-b border-[var(--clp-border)] last:border-0 hover:bg-[var(--clp-panel-2)]">
                      <td className="py-1.5 px-3"><Link to={`/designs/${d.id}`} className="font-semibold text-[var(--clp-accent)] no-underline hover:underline">{titleCase(d.element_type)} {d.name}</Link></td>
                      <td className="py-1.5 px-2 num">R{d.revision}</td>
                      <td className="py-1.5 px-2"><StatusChip status={d.status} /></td>
                      <td className="py-1.5 px-2"><Utilisation value={d.max_utilisation} /></td>
                      <td className="py-1.5 px-2"><ReviewChip status={d.review_status} />{d.approved_by_name && <span className="text-[11px] text-[var(--clp-ink-3)]"> by {d.approved_by_name}</span>}</td>
                      <td className="py-1.5 px-2 text-[var(--clp-ink-2)]">{d.designed_by_name}</td>
                      <td className="py-1.5 px-2 text-[var(--clp-ink-2)] whitespace-nowrap" title={fmtDate(d.updated_at)}>{timeAgo(d.updated_at)}</td>
                      <td className="py-1.5 px-3 text-right whitespace-nowrap">
                        <Tooltip title="Calculation report (PDF)"><IconButton aria-label={`Report for ${d.name}`} onClick={() => download(`/designs/${d.id}/report.pdf`, "report.pdf").catch(fail)}><PictureAsPdfOutlined fontSize="small" /></IconButton></Tooltip>
                        {can("design:delete") && (
                          <Tooltip title="Delete design"><IconButton aria-label={`Delete ${d.name}`} onClick={() => {
                            if (window.confirm(`Delete ${d.element_type} ${d.name} and its revisions?`)) removeDesign.mutate(d.id, { onSuccess: () => notify(`${titleCase(d.element_type)} ${d.name} deleted`, "success"), onError: fail });
                          }}><DeleteOutlined fontSize="small" /></IconButton></Tooltip>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
      </Card>
    </div>
  );
}
