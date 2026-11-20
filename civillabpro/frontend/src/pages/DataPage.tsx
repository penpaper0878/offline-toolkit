import BackupOutlined from "@mui/icons-material/BackupOutlined";
import Button from "@mui/material/Button";
import { useState } from "react";
import { type ApiError, download } from "../api/client";
import { Card, PageHeader } from "../components/Card";
import { ImportProjectButton } from "../components/ImportProject";
import { useTab } from "../shell/hooks";
import { useAuth } from "../stores/auth";
import { useUi } from "../stores/ui";

/** Data and backup: the database snapshot (owners), and moving projects between installations. */
export function DataPage() {
  useTab("Data and backup");
  const can = useAuth((s) => s.can);
  const notify = useUi((s) => s.notify);
  const [busy, setBusy] = useState(false);
  const backup = async () => {
    setBusy(true);
    try {
      await download("/admin/backup", "civillabpro-backup.db");
      notify("Backup saved. Keep it somewhere other than this computer.", "success");
    } catch (e) {
      notify((e as ApiError).message, "error");
    } finally {
      setBusy(false);
    }
  };
  const p = "m-0 text-[13px] leading-relaxed text-[var(--clp-ink-2)]";
  return (
    <div className="p-5 max-w-[960px] mx-auto">
      <PageHeader title="Data and backup" subtitle="Keep a copy of your work, and move projects between installations." />
      {can("org:manage") && (
        <Card title="Back up the database">
          <div className="p-4 flex flex-col gap-3">
            <p className={p}>
              A consistent copy of everything this installation holds: projects, designs and their revisions, users and the audit trail. On the
              desktop app, restore it from the File menu (Restore from backup); the data it replaces is kept in the data folder.
            </p>
            <p className={p}>
              Offered where this installation keeps your organisation alone in a single database file (the desktop app, a small server). A
              server on PostgreSQL is backed up there, with pg_dump.
            </p>
            <div><Button variant="contained" startIcon={<BackupOutlined />} disabled={busy} onClick={() => void backup()}>
              {busy ? "Preparing the backup" : "Download a backup"}
            </Button></div>
          </div>
        </Card>
      )}
      {can("project:write") && can("design:write") && (
        <Card title="Move a project between installations">
          <div className="p-4 flex flex-col gap-3">
            <p className={p}>
              Export a project from its page (Export project): one file with the project, every design, its revisions and its review record.
              Import it here or on any other installation. Designs come in as they were calculated, with the engine version that made them, and
              are not recalculated; a revision recalculates as usual. A job number already in use gets a suffix.
            </p>
            <div><ImportProjectButton variant="contained" /></div>
          </div>
        </Card>
      )}
    </div>
  );
}
