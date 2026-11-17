import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { TokenPair } from "../api/types";
import { useAuth } from "../stores/auth";

interface Form { email: string; password: string; full_name: string; organization_name: string; organization_kind: string }

const KINDS = [["consultant", "Consultant"], ["contractor", "Contractor"], ["government", "Government department"], ["laboratory", "Laboratory"], ["academic", "University or college"]];

export function LoginPage() {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [failure, setFailure] = useState("");
  const { accessToken, setTokens } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const { register, handleSubmit, setError, formState: { errors, isSubmitting } } = useForm<Form>({ defaultValues: { organization_kind: "consultant" } });

  if (accessToken) return <Navigate to={(location.state as { from?: string } | null)?.from ?? "/"} replace />;

  const submit = handleSubmit(async (f) => {
    setFailure("");
    try {
      const tokens = mode === "login"
        ? await api<TokenPair>("/auth/login", { method: "POST", form: { username: f.email, password: f.password }, auth: false })
        : await api<TokenPair>("/auth/register", { method: "POST", body: f, auth: false });
      setTokens(tokens);
      navigate((location.state as { from?: string } | null)?.from ?? "/", { replace: true });
    } catch (e) {
      const err = e as ApiError;
      for (const d of err.details ?? []) if (d.field) setError(d.field as keyof Form, { message: d.message });
      setFailure(err.message);
    }
  });

  return (
    <div className="min-h-full grid lg:grid-cols-[minmax(0,1fr)_460px]">
      <div className="hidden lg:flex flex-col justify-between p-12 bg-[#0f172a] text-slate-100">
        <div className="flex items-center gap-3"><img src="/icon.svg" alt="" className="h-8 w-8" /><span className="text-lg font-semibold tracking-tight">CivilLabPro OS</span></div>
        <div className="max-w-lg">
          <h1 className="text-3xl font-semibold leading-tight tracking-tight m-0">One workspace for design, estimation, testing and site.</h1>
          <p className="mt-4 text-slate-300 text-[15px] leading-relaxed">Calculations to Indian Standards with every line traced to its clause, checked by a second engineer and issued as reports, schedules and drawings.</p>
          <ul className="mt-6 space-y-2 text-slate-300 text-sm list-none p-0">
            <li>IS 456:2000 member design with bar bending schedules</li>
            <li>PDF calculation reports, Excel schedules and DXF drawings</li>
            <li>Roles, approvals and an audit trail for every project</li>
          </ul>
        </div>
        <div className="text-xs text-slate-500">Design aids do not replace the judgement of a qualified engineer.</div>
      </div>
      <div className="flex items-center justify-center p-8 bg-[var(--clp-panel)]">
        <form onSubmit={submit} className="w-full max-w-sm flex flex-col gap-3.5" noValidate>
          <h2 className="text-xl font-semibold m-0">{mode === "login" ? "Sign in" : "Create your organisation"}</h2>
          <p className="m-0 -mt-2 text-[var(--clp-ink-2)]">{mode === "login" ? "Use your work email." : "You become its owner and can add your team afterwards."}</p>
          {failure && <Alert severity="error">{failure}</Alert>}
          {mode === "register" && (
            <>
              <TextField label="Organisation" autoFocus {...register("organization_name", { required: "Enter the organisation name.", minLength: { value: 2, message: "Enter the organisation name." } })} error={!!errors.organization_name} helperText={errors.organization_name?.message} />
              <TextField label="Type of organisation" select defaultValue="consultant" {...register("organization_kind")}>
                {KINDS.map(([v, l]) => <MenuItem key={v} value={v}>{l}</MenuItem>)}
              </TextField>
              <TextField label="Your name" autoComplete="name" {...register("full_name", { required: "Enter your name.", minLength: { value: 2, message: "Enter your name." } })} error={!!errors.full_name} helperText={errors.full_name?.message} />
            </>
          )}
          <TextField label="Email" type="email" autoComplete="email" autoFocus={mode === "login"} {...register("email", { required: "Enter your email.", pattern: { value: /^\S+@\S+\.\S+$/, message: "Enter a valid email address." } })} error={!!errors.email} helperText={errors.email?.message} />
          <TextField label="Password" type="password" autoComplete={mode === "login" ? "current-password" : "new-password"}
            {...register("password", { required: "Enter your password.", ...(mode === "register" ? { minLength: { value: 10, message: "At least 10 characters, with a letter and a digit." } } : {}) })}
            error={!!errors.password} helperText={errors.password?.message ?? (mode === "register" ? "At least 10 characters, with a letter and a digit." : undefined)} />
          <Button type="submit" variant="contained" size="large" disabled={isSubmitting}>{mode === "login" ? "Sign in" : "Create organisation"}</Button>
          <Button variant="text" onClick={() => { setMode(mode === "login" ? "register" : "login"); setFailure(""); }}>
            {mode === "login" ? "New here? Create an organisation" : "Already registered? Sign in"}
          </Button>
        </form>
      </div>
    </div>
  );
}
