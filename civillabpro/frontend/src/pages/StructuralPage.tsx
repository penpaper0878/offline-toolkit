import Button from "@mui/material/Button";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useElements, useProjects } from "../api/hooks";
import { Card, Empty, PageHeader } from "../components/Card";
import { useTab } from "../shell/hooks";
import { useAuth } from "../stores/auth";

// The order in which further members join the registry (docs/ROADMAP.md, phase 1 and 2).
const NEXT = ["Trapezoidal footing", "Staircase", "Retaining wall",
  "Pile cap", "Water tanks to IS 3370 (rectangular, circular, ESR, GSR)", "Box and pipe culvert"];

export function StructuralPage() {
  useTab("Structural design");
  const elements = useElements();
  const projects = useProjects();
  const canWrite = useAuth((s) => s.can("design:write"));
  const [projectId, setProjectId] = useState("");
  const list = projects.data?.items ?? [];
  const chosen = projectId || list[0]?.id || "";

  return (
    <div className="p-5 max-w-[1400px] mx-auto">
      <PageHeader title="Structural design" subtitle="Limit state design to IS 456:2000. Each design produces its calculation, bar bending schedule, quantities and drawing.">
        {list.length > 0 && (
          <TextField select label="Project" value={chosen} onChange={(e) => setProjectId(e.target.value)} sx={{ width: 300 }}>
            {list.map((p) => <MenuItem key={p.id} value={p.id}>{p.code}  {p.name}</MenuItem>)}
          </TextField>
        )}
      </PageHeader>
      {projects.isSuccess && list.length === 0 && (
        <Card className="mb-3"><Empty title="Create a project first"><span>A design is filed under a project.</span><Button variant="contained" component={Link} to="/projects?new=1">New project</Button></Empty></Card>
      )}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        {(elements.data ?? []).map((e) => (
          <Card key={e.type} title={e.title} action={<span className="text-[11px] text-[var(--clp-ink-3)]">engine {e.engine_version}</span>}>
            <div className="p-3">
              <p className="m-0">{e.description}</p>
              <div className="mt-2 flex flex-wrap gap-1.5">{e.code_basis.map((c) => <span key={c} className="px-2 py-0.5 rounded border border-[var(--clp-border)] bg-[var(--clp-panel-2)] text-[11px]">{c}</span>)}</div>
              <div className="mt-3 text-[11.5px] font-semibold text-[var(--clp-ink-2)]">Scope limits</div>
              <ul className="m-0 mt-1 pl-4 text-[12px] text-[var(--clp-ink-2)] leading-relaxed">{e.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
              <div className="mt-3">
                <Button variant="contained" disabled={!chosen || !canWrite} component={Link} to={`/projects/${chosen}/designs/new/${e.type}`}>New {e.title.toLowerCase()} design</Button>
                {!canWrite && <span className="ml-3 text-xs text-[var(--clp-ink-3)]">Your role can view designs but not create them.</span>}
              </div>
            </div>
          </Card>
        ))}
        <Card title="Next members">
          <div className="p-3">
            <p className="m-0 text-[var(--clp-ink-2)]">These join the same workspace as they are built and hand-checked, one at a time.</p>
            <ol className="m-0 mt-2 pl-5 text-[12.5px] leading-relaxed">{NEXT.map((n) => <li key={n}>{n}</li>)}</ol>
          </div>
        </Card>
      </div>
    </div>
  );
}
