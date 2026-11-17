import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { useAuth } from "../stores/auth";

interface Health { status: string; version: string; database: string; environment: string }

export function StatusBar() {
  const me = useAuth((s) => s.me);
  const health = useQuery({ queryKey: ["health"], queryFn: () => api<Health>("/health", { auth: false }), refetchInterval: 30_000, retry: false });
  const online = health.isSuccess;
  return (
    <footer className="no-print shrink-0 flex items-center h-6 px-3 gap-4 text-[11px] border-t border-[var(--clp-border)] bg-[var(--clp-panel)] text-[var(--clp-ink-2)]">
      <span className="flex items-center gap-1.5" role="status">
        <span className={`h-2 w-2 rounded-full ${online ? "bg-[var(--clp-ok)]" : "bg-[var(--clp-bad)]"}`} />
        {online ? `Server connected (${health.data.database}, v${health.data.version})` : health.isLoading ? "Connecting to server" : "Server not reachable"}
      </span>
      <span>Units: SI (mm, kN, N/mm²)</span>
      <span>Design basis: IS 456:2000</span>
      <span className="ml-auto capitalize">{me ? `${me.full_name} · ${me.role}` : ""}</span>
    </footer>
  );
}
