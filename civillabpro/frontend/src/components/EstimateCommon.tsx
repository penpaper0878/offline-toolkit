import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, type ApiError } from "../api/client";
import { useInvalidatingMutation, useProjects } from "../api/hooks";
import type { Estimate } from "../api/types";
import { useUi } from "../stores/ui";

export function EstimateStatus({ status, revision }: { status: string; revision: number }) {
  const issued = status === "issued";
  return <span className={`text-[12px] font-semibold ${issued ? "text-[var(--clp-ok)]" : "text-[var(--clp-ink-3)]"}`}>R{revision} {issued ? "Issued" : "Draft"}</span>;
}

/** Start an estimate in a project. */
export function NewEstimateDialog({ open, onClose, projectId }: { open: boolean; onClose: () => void; projectId?: string }) {
  const projects = useProjects();
  const navigate = useNavigate();
  const notify = useUi((s) => s.notify);
  const [project, setProject] = useState(projectId ?? "");
  const [title, setTitle] = useState("");
  useEffect(() => { if (open) { setTitle(""); setProject(projectId ?? ""); } }, [open, projectId]);
  const create = useInvalidatingMutation((pid: string) => api<Estimate>(`/projects/${pid}/estimates`, { method: "POST", body: { title: title.trim() } }));
  const pid = projectId ?? project;
  return (
    <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth aria-label="New estimate">
      <DialogTitle>New estimate</DialogTitle>
      <DialogContent>
        <div className="flex flex-col gap-3 pt-1">
          {!projectId && (
            <TextField select label="Project" value={project} onChange={(e) => setProject(e.target.value)}>
              {(projects.data?.items ?? []).map((p) => <MenuItem key={p.id} value={p.id}>{p.code}  {p.name}</MenuItem>)}
            </TextField>
          )}
          <TextField label="Estimate title" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Foundations, Superstructure, Whole work" autoFocus />
        </div>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" disabled={!pid || !title.trim() || create.isPending} onClick={() => {
          create.mutate(pid, { onSuccess: (e) => { onClose(); navigate(`/estimates/${e.id}`); }, onError: (e) => notify((e as ApiError).message, "error") });
        }}>Create</Button>
      </DialogActions>
    </Dialog>
  );
}
