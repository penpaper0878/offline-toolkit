import CheckCircle from "@mui/icons-material/CheckCircle";
import ErrorIcon from "@mui/icons-material/Error";
import PauseCircle from "@mui/icons-material/PauseCircle";
import VerifiedOutlined from "@mui/icons-material/VerifiedOutlined";

const STATUS = {
  ok: { label: "OK", colour: "var(--clp-ok)", Icon: CheckCircle },
  not_ok: { label: "Not OK", colour: "var(--clp-bad)", Icon: ErrorIcon },
  stopped: { label: "Stopped", colour: "var(--clp-warn)", Icon: PauseCircle },
} as const;

/** Design verdict. Always an icon and a word together, never colour alone. */
export function StatusChip({ status, size = "sm" }: { status: keyof typeof STATUS; size?: "sm" | "md" }) {
  const s = STATUS[status];
  return (
    <span className={`inline-flex items-center gap-1 font-semibold whitespace-nowrap ${size === "md" ? "text-sm" : "text-xs"}`} style={{ color: s.colour }}>
      <s.Icon sx={{ fontSize: size === "md" ? 18 : 15 }} />
      {s.label}
    </span>
  );
}

export function ReviewChip({ status }: { status: "draft" | "approved" }) {
  if (status === "approved") {
    return <span className="inline-flex items-center gap-1 text-xs font-semibold text-[var(--clp-accent)]"><VerifiedOutlined sx={{ fontSize: 15 }} />Approved</span>;
  }
  return <span className="text-xs text-[var(--clp-ink-3)]">Draft</span>;
}

/** Demand over capacity as a thin bar with the figure beside it. */
export function Utilisation({ value }: { value: number | null }) {
  if (value === null) return <span className="text-[var(--clp-ink-3)]">-</span>;
  const over = value > 1;
  return (
    <span className="inline-flex items-center gap-2 num" title={`Utilisation ${value.toFixed(2)}`}>
      <span className="relative h-1.5 w-14 rounded-full bg-[var(--clp-border)] overflow-hidden">
        <span className="absolute inset-y-0 left-0 rounded-full" style={{ width: `${Math.min(value, 1) * 100}%`, background: over ? "var(--clp-bad)" : "var(--clp-accent)" }} />
      </span>
      <span className={over ? "text-[var(--clp-bad)] font-semibold" : ""}>{value.toFixed(2)}</span>
    </span>
  );
}
