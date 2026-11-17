import PersonAddAltOutlined from "@mui/icons-material/PersonAddAltOutlined";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import MenuItem from "@mui/material/MenuItem";
import Switch from "@mui/material/Switch";
import TextField from "@mui/material/TextField";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { api, type ApiError } from "../api/client";
import { useInvalidatingMutation, useRoles, useUsers } from "../api/hooks";
import type { Role, User } from "../api/types";
import { Card, PageHeader } from "../components/Card";
import { fmtDateTime, timeAgo } from "../lib/format";
import { useTab } from "../shell/hooks";
import { useAuth } from "../stores/auth";
import { useUi } from "../stores/ui";

interface Form { full_name: string; email: string; designation: string; role: Role; password: string }
interface AuditRow { id: string; user_name: string; action: string; summary: string; created_at: string }

export function UsersPage() {
  useTab("Users and roles");
  const me = useAuth((s) => s.me);
  const notify = useUi((s) => s.notify);
  const users = useUsers();
  const roles = useRoles();
  const audit = useQuery({ queryKey: ["users", "audit"], queryFn: () => api<AuditRow[]>("/users/audit?limit=40") });
  const [open, setOpen] = useState(false);
  const [failure, setFailure] = useState("");
  const { register, handleSubmit, setError, reset, formState: { errors } } = useForm<Form>({ defaultValues: { role: "engineer", designation: "" } });
  const fail = (e: unknown) => notify((e as ApiError).message, "error");
  const create = useInvalidatingMutation((f: Form) => api<User>("/users", { method: "POST", body: f }));
  const update = useInvalidatingMutation(({ id, ...body }: { id: string; role?: Role; is_active?: boolean }) => api<User>(`/users/${id}`, { method: "PATCH", body }));
  const assignable = (roles.data ?? []).filter((r) => r.role !== "owner" || me?.role === "owner");

  const submit = handleSubmit((f) => {
    setFailure("");
    create.mutate(f, {
      onSuccess: (u) => { notify(`${u.full_name} added`, "success"); reset(); setOpen(false); },
      onError: (e) => {
        const err = e as ApiError;
        for (const d of err.details ?? []) if (d.field) setError(d.field as keyof Form, { message: d.message });
        setFailure(err.message);
      },
    });
  });

  return (
    <div className="p-5 max-w-[1400px] mx-auto">
      <PageHeader title="Users and roles" subtitle={`Access to ${me?.organization.name ?? "the organisation"} is by role; every change is recorded in the audit trail.`}>
        <Button variant="contained" startIcon={<PersonAddAltOutlined />} onClick={() => setOpen(true)}>Add user</Button>
      </PageHeader>
      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)] gap-3">
        <Card title="People">
          <div className="overflow-x-auto">
            <table className="w-full text-[13px] border-collapse">
              <thead>
                <tr className="text-left text-[11px] text-[var(--clp-ink-3)] border-b border-[var(--clp-border)]">
                  <th className="py-2 px-3 font-semibold">Name</th><th className="py-2 px-2 font-semibold">Email</th><th className="py-2 px-2 font-semibold">Role</th>
                  <th className="py-2 px-2 font-semibold">Last sign-in</th><th className="py-2 px-3 font-semibold text-right">Active</th>
                </tr>
              </thead>
              <tbody>
                {(users.data ?? []).map((u) => {
                  const locked = u.id === me?.id || (u.role === "owner" && me?.role !== "owner");
                  return (
                    <tr key={u.id} className="border-b border-[var(--clp-border)] last:border-0">
                      <td className="py-1.5 px-3 font-semibold">{u.full_name}{u.designation && <span className="font-normal text-[var(--clp-ink-3)]">, {u.designation}</span>}</td>
                      <td className="py-1.5 px-2 text-[var(--clp-ink-2)]">{u.email}</td>
                      <td className="py-1.5 px-2">
                        <TextField select value={u.role} disabled={locked} onChange={(e) => update.mutate({ id: u.id, role: e.target.value as Role }, { onError: fail })} sx={{ width: 190 }} slotProps={{ htmlInput: { "aria-label": `Role of ${u.full_name}` } }}>
                          {(roles.data ?? []).filter((r) => assignable.includes(r) || r.role === u.role).map((r) => <MenuItem key={r.role} value={r.role}>{r.label}</MenuItem>)}
                        </TextField>
                      </td>
                      <td className="py-1.5 px-2 text-[var(--clp-ink-2)] whitespace-nowrap">{u.last_login_at ? fmtDateTime(u.last_login_at) : "Never"}</td>
                      <td className="py-1.5 px-3 text-right"><Switch size="small" checked={u.is_active} disabled={locked} onChange={(e) => update.mutate({ id: u.id, is_active: e.target.checked }, { onError: fail })} slotProps={{ input: { "aria-label": `${u.full_name} active` } }} /></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>
        <Card title="What each role may do">
          <ul className="m-0 p-0 list-none">
            {(roles.data ?? []).map((r) => (
              <li key={r.role} className="px-3 py-2 border-b border-[var(--clp-border)] last:border-0">
                <div className="font-semibold text-[12.5px]">{r.label}</div>
                <div className="mt-1 flex flex-wrap gap-1">{r.permissions.map((p) => <code key={p} className="px-1.5 py-px rounded bg-[var(--clp-panel-2)] border border-[var(--clp-border)] text-[10.5px]">{p}</code>)}</div>
              </li>
            ))}
          </ul>
        </Card>
      </div>
      <Card title="Audit trail" className="mt-3">
        <ul className="m-0 p-0 list-none max-h-[280px] overflow-y-auto">
          {(audit.data ?? []).map((a) => (
            <li key={a.id} className="grid grid-cols-[150px_180px_minmax(0,1fr)] gap-3 px-3 py-1.5 border-b border-[var(--clp-border)] last:border-0 text-[12.5px]">
              <span className="text-[var(--clp-ink-3)]" title={fmtDateTime(a.created_at)}>{timeAgo(a.created_at)}</span>
              <span className="truncate">{a.user_name}</span>
              <span className="truncate">{a.summary} <code className="text-[10.5px] text-[var(--clp-ink-3)]">{a.action}</code></span>
            </li>
          ))}
        </ul>
      </Card>

      <Dialog open={open} onClose={() => setOpen(false)} maxWidth="xs" fullWidth>
        <form onSubmit={submit} noValidate>
          <DialogTitle>Add user</DialogTitle>
          <DialogContent className="!pt-2 flex flex-col gap-3">
            {failure && <Alert severity="error">{failure}</Alert>}
            <TextField label="Full name" autoFocus {...register("full_name", { required: "Enter the name.", minLength: { value: 2, message: "Enter the name." } })} error={!!errors.full_name} helperText={errors.full_name?.message} />
            <TextField label="Email" type="email" {...register("email", { required: "Enter the email.", pattern: { value: /^\S+@\S+\.\S+$/, message: "Enter a valid email address." } })} error={!!errors.email} helperText={errors.email?.message} />
            <TextField label="Designation" {...register("designation")} />
            <TextField label="Role" select defaultValue="engineer" {...register("role")}>{assignable.map((r) => <MenuItem key={r.role} value={r.role}>{r.label}</MenuItem>)}</TextField>
            <TextField label="Temporary password" type="password" autoComplete="new-password" {...register("password", { required: "Enter a password.", minLength: { value: 10, message: "At least 10 characters, with a letter and a digit." } })}
              error={!!errors.password} helperText={errors.password?.message ?? "At least 10 characters, with a letter and a digit. Ask the user to change it."} />
          </DialogContent>
          <DialogActions className="!px-5 !pb-4">
            <Button onClick={() => setOpen(false)}>Cancel</Button>
            <Button type="submit" variant="contained" disabled={create.isPending}>Add user</Button>
          </DialogActions>
        </form>
      </Dialog>
    </div>
  );
}
