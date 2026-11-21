import UploadFileOutlined from "@mui/icons-material/UploadFileOutlined";
import Button from "@mui/material/Button";
import { useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, type ApiError } from "../api/client";
import type { Project } from "../api/types";
import { useUi } from "../stores/ui";

interface ImportResult { project: Project; designs: number; revisions: number; estimates: number; code_changed: boolean; note: string }

/** Import a project archive (.clp.json) exported from this or another installation: a new project with its designs as recorded. */
export function ImportProjectButton({ variant = "outlined" }: { variant?: "outlined" | "contained" }) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const notify = useUi((s) => s.notify);
  const navigate = useNavigate();
  const qc = useQueryClient();

  const load = async (file: File) => {
    setBusy(true);
    try {
      let archive: unknown;
      try { archive = JSON.parse(await file.text()); } catch { throw new Error(`${file.name} is not a project archive (it is not JSON).`); }
      const r = await api<ImportResult>("/projects/import", { method: "POST", body: archive });
      await qc.invalidateQueries();
      notify(`${r.note} ${r.designs} design${r.designs === 1 ? "" : "s"}, ${r.revisions} earlier revision${r.revisions === 1 ? "" : "s"} and `
        + `${r.estimates} estimate${r.estimates === 1 ? "" : "s"} imported.`, "success");
      navigate(`/projects/${r.project.id}`);
    } catch (e) {
      notify((e as ApiError | Error).message, "error");
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  };

  return (
    <>
      <input ref={input} type="file" accept=".json,application/json" hidden aria-label="Project archive file"
        onChange={(e) => { const f = e.target.files?.[0]; if (f) void load(f); }} />
      <Button variant={variant} startIcon={<UploadFileOutlined />} disabled={busy} onClick={() => input.current?.click()}>
        {busy ? "Importing" : "Import project"}
      </Button>
    </>
  );
}
