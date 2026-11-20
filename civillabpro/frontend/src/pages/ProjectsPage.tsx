import AddOutlined from "@mui/icons-material/AddOutlined";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, type ApiError } from "../api/client";
import { useInvalidatingMutation, useProjects } from "../api/hooks";
import type { Project } from "../api/types";
import { Card, Empty, PageHeader } from "../components/Card";
import { ImportProjectButton } from "../components/ImportProject";
import { fmtDate, titleCase } from "../lib/format";
import { useTab } from "../shell/hooks";
import { useAuth } from "../stores/auth";
import { useUi } from "../stores/ui";

export const PROJECT_TYPES = ["building", "water_supply", "sewerage", "highway", "bridge", "irrigation", "industrial", "other"];
export const PROJECT_STATUSES = ["planning", "active", "on_hold", "completed"];
export const STATES = ["Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh", "Goa", "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka", "Kerala",
  "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura", "Uttar Pradesh",
  "Uttarakhand", "West Bengal", "Andaman and Nicobar Islands", "Chandigarh", "Dadra and Nagar Haveli and Daman and Diu", "Delhi", "Jammu and Kashmir", "Ladakh", "Lakshadweep", "Puducherry"];

type Form = Pick<Project, "code" | "name" | "client" | "location" | "state" | "project_type" | "status">;

export function ProjectDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const navigate = useNavigate();
  const notify = useUi((s) => s.notify);
  const [failure, setFailure] = useState("");
  const { register, handleSubmit, setError, reset, formState: { errors } } = useForm<Form>({ defaultValues: { project_type: "building", status: "active", state: "" } });
  const create = useInvalidatingMutation((f: Form) => api<Project>("/projects", { method: "POST", body: f }));

  const submit = handleSubmit((f) => {
    setFailure("");
    create.mutate(f, {
      onSuccess: (p) => { notify(`Project ${p.code} created`, "success"); reset(); onClose(); navigate(`/projects/${p.id}`); },
      onError: (e) => {
        const err = e as ApiError;
        for (const d of err.details ?? []) if (d.field) setError(d.field as keyof Form, { message: d.message });
        setFailure(err.message);
      },
    });
  });

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <form onSubmit={submit} noValidate>
        <DialogTitle>New project</DialogTitle>
        <DialogContent className="!pt-2 grid grid-cols-2 gap-3">
          {failure && <Alert severity="error" className="col-span-2">{failure}</Alert>}
          <TextField label="Job number" autoFocus {...register("code", { required: "Enter the job number.", pattern: { value: /^[A-Za-z0-9][A-Za-z0-9 _./-]*$/, message: "Letters, digits, spaces and . _ / - only." } })} error={!!errors.code} helperText={errors.code?.message} />
          <TextField label="Type" select defaultValue="building" {...register("project_type")}>{PROJECT_TYPES.map((t) => <MenuItem key={t} value={t}>{titleCase(t)}</MenuItem>)}</TextField>
          <TextField label="Project name" className="col-span-2" {...register("name", { required: "Enter the project name.", minLength: { value: 2, message: "Enter the project name." } })} error={!!errors.name} helperText={errors.name?.message} />
          <TextField label="Client" {...register("client")} />
          <TextField label="Location" {...register("location")} />
          <TextField label="State or union territory" select defaultValue="" {...register("state")} helperText="Selects the schedule of rates later">
            <MenuItem value="">Not set</MenuItem>
            {STATES.map((s) => <MenuItem key={s} value={s}>{s}</MenuItem>)}
          </TextField>
          <TextField label="Status" select defaultValue="active" {...register("status")}>{PROJECT_STATUSES.map((t) => <MenuItem key={t} value={t}>{titleCase(t)}</MenuItem>)}</TextField>
        </DialogContent>
        <DialogActions className="!px-5 !pb-4">
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="contained" disabled={create.isPending}>Create project</Button>
        </DialogActions>
      </form>
    </Dialog>
  );
}

export function ProjectsPage() {
  useTab("Projects");
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const { data, isLoading, error } = useProjects(q, status);
  const canWrite = useAuth((s) => s.can("project:write"));
  const canDesign = useAuth((s) => s.can("design:write"));
  const navigate = useNavigate();
  const open = params.get("new") === "1" && canWrite;
  const setOpen = (v: boolean) => setParams(v ? { new: "1" } : {}, { replace: true });

  return (
    <div className="p-5 max-w-[1400px] mx-auto">
      <PageHeader title="Projects" subtitle="Every design, estimate and report belongs to a project.">
        <TextField placeholder="Search name, job number or client" value={q} onChange={(e) => setQ(e.target.value)} sx={{ width: 280 }} slotProps={{ htmlInput: { "aria-label": "Search projects" } }} />
        <TextField select value={status} onChange={(e) => setStatus(e.target.value)} sx={{ width: 140 }} slotProps={{ select: { displayEmpty: true }, htmlInput: { "aria-label": "Status filter" } }}>
          <MenuItem value="">All statuses</MenuItem>
          {PROJECT_STATUSES.map((t) => <MenuItem key={t} value={t}>{titleCase(t)}</MenuItem>)}
        </TextField>
        {canWrite && canDesign && <ImportProjectButton />}
        {canWrite && <Button variant="contained" startIcon={<AddOutlined />} onClick={() => setOpen(true)}>New project</Button>}
      </PageHeader>
      <Card>
        {error ? <div className="p-4 text-[var(--clp-bad)]" role="alert">Projects could not be loaded. {(error as Error).message}</div>
          : isLoading ? <div className="p-4 text-[var(--clp-ink-3)]">Loading projects</div>
          : data!.items.length === 0 ? (
            <Empty title={q || status ? "No project matches" : "No projects yet"}>
              <span>{q || status ? "Clear the search or the status filter." : "A project holds the designs, drawings and reports of one job."}</span>
              {!q && !status && canWrite && <Button variant="contained" onClick={() => setOpen(true)}>Create the first project</Button>}
            </Empty>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-[13px] border-collapse">
                <thead>
                  <tr className="text-left text-[11px] text-[var(--clp-ink-3)] border-b border-[var(--clp-border)]">
                    <th className="py-2 px-3 font-semibold">Job no.</th><th className="py-2 px-2 font-semibold">Project</th><th className="py-2 px-2 font-semibold">Client</th>
                    <th className="py-2 px-2 font-semibold">Type</th><th className="py-2 px-2 font-semibold">Status</th><th className="py-2 px-2 font-semibold text-right">Designs</th>
                    <th className="py-2 px-3 font-semibold text-right">Updated</th>
                  </tr>
                </thead>
                <tbody>
                  {data!.items.map((p) => (
                    <tr key={p.id} tabIndex={0} onClick={() => navigate(`/projects/${p.id}`)} onKeyDown={(e) => e.key === "Enter" && navigate(`/projects/${p.id}`)}
                      className="border-b border-[var(--clp-border)] last:border-0 cursor-pointer hover:bg-[var(--clp-panel-2)]">
                      <td className="py-2 px-3 font-semibold text-[var(--clp-accent)] whitespace-nowrap">{p.code}</td>
                      <td className="py-2 px-2">{p.name}{p.location && <span className="text-[var(--clp-ink-3)]">, {p.location}</span>}</td>
                      <td className="py-2 px-2 text-[var(--clp-ink-2)]">{p.client || "-"}</td>
                      <td className="py-2 px-2 text-[var(--clp-ink-2)]">{titleCase(p.project_type)}</td>
                      <td className="py-2 px-2">{titleCase(p.status)}</td>
                      <td className="py-2 px-2 text-right num">{p.design_count}</td>
                      <td className="py-2 px-3 text-right text-[var(--clp-ink-2)] whitespace-nowrap">{fmtDate(p.updated_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
      </Card>
      <ProjectDialog open={open} onClose={() => setOpen(false)} />
    </div>
  );
}
