import Button from "@mui/material/Button";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useDashboard, useElements } from "../api/hooks";
import type { DashboardSummary } from "../api/types";
import { Card, Empty, PageHeader } from "../components/Card";
import { ReviewChip, StatusChip, Utilisation } from "../components/Status";
import { fmtDateTime, timeAgo, titleCase } from "../lib/format";
import { useTab } from "../shell/hooks";
import { useAuth } from "../stores/auth";

function Tile({ label, value, note }: { label: string; value: string | number; note?: string }) {
  return (
    <div className="rounded-md border border-[var(--clp-border)] bg-[var(--clp-panel)] px-4 py-3">
      <div className="text-[11.5px] text-[var(--clp-ink-2)]">{label}</div>
      <div className="mt-0.5 text-[26px] leading-none font-semibold num tracking-tight">{value}</div>
      <div className="mt-1.5 text-[11.5px] text-[var(--clp-ink-3)] h-4">{note}</div>
    </div>
  );
}

const day = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", { day: "2-digit", month: "short" });

/** Saves and revisions per day. One series, so no legend: the card title names it. */
function ActivityChart({ data }: { data: DashboardSummary["design_activity"] }) {
  const [asTable, setAsTable] = useState(false);
  const total = data.reduce((s, d) => s + d.count, 0);
  return (
    <Card title="Design activity, last 14 days" action={<Button size="small" onClick={() => setAsTable(!asTable)}>{asTable ? "Chart" : "Table"}</Button>}>
      {asTable ? (
        <div className="p-3 max-h-[220px] overflow-y-auto">
          <table className="w-full text-[12.5px] border-collapse">
            <thead><tr className="text-left text-[11px] text-[var(--clp-ink-3)] border-b border-[var(--clp-border)]"><th className="py-1 font-semibold">Date</th><th className="py-1 font-semibold text-right">Designs saved or revised</th></tr></thead>
            <tbody>{data.map((d) => <tr key={d.date} className="border-b border-[var(--clp-border)] last:border-0"><td className="py-1">{day(d.date)}</td><td className="py-1 text-right num">{d.count}</td></tr>)}</tbody>
          </table>
        </div>
      ) : (
        <div className="h-[220px] px-2 pt-3 pb-1" role="img" aria-label={`Bar chart: ${total} designs saved or revised in the last 14 days`}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ top: 6, right: 12, bottom: 0, left: -18 }}>
              <CartesianGrid vertical={false} stroke="var(--viz-grid)" />
              <XAxis dataKey="date" tickFormatter={day} tick={{ fontSize: 11, fill: "var(--clp-ink-3)" }} tickLine={false} axisLine={{ stroke: "var(--viz-axis)" }} interval={1} />
              <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: "var(--clp-ink-3)" }} tickLine={false} axisLine={false} width={44} />
              <Tooltip
                cursor={{ fill: "color-mix(in srgb, var(--clp-ink) 6%, transparent)" }}
                content={({ active, payload }) => active && payload?.length ? (
                  <div className="rounded border border-[var(--clp-border)] bg-[var(--clp-panel)] px-2.5 py-1.5 text-xs shadow-md">
                    <div className="text-[var(--clp-ink-2)]">{day(String(payload[0].payload.date))}</div>
                    <div className="font-semibold num">{payload[0].payload.count} saved or revised</div>
                  </div>
                ) : null}
              />
              <Bar dataKey="count" fill="var(--viz-series-1)" radius={[4, 4, 0, 0]} maxBarSize={18} isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </Card>
  );
}

const STATUS_ROWS = [
  { key: "ok", colour: "var(--viz-good)" },
  { key: "not_ok", colour: "var(--viz-critical)" },
  { key: "stopped", colour: "var(--viz-serious)" },
] as const;

/** Parts of a whole across three reserved status colours; every segment is also listed with its icon, label and count. */
function StatusBreakdown({ designs }: { designs: DashboardSummary["designs"] }) {
  const total = designs.total;
  return (
    <Card title="Design status">
      <div className="p-3">
        {total > 0 && (
          <div className="flex h-2.5 gap-[2px] mb-3" aria-hidden="true">
            {STATUS_ROWS.filter((r) => designs.by_status[r.key]).map((r) => (
              <div key={r.key} className="h-full rounded-[3px]" style={{ flexGrow: designs.by_status[r.key], background: r.colour }} title={`${titleCase(r.key)}: ${designs.by_status[r.key]}`} />
            ))}
          </div>
        )}
        <table className="w-full text-[12.5px] border-collapse">
          <tbody>
            {STATUS_ROWS.map((r) => (
              <tr key={r.key} className="border-b border-[var(--clp-border)] last:border-0">
                <td className="py-1.5"><StatusChip status={r.key} /></td>
                <td className="py-1.5 text-right num font-semibold">{designs.by_status[r.key] ?? 0}</td>
                <td className="py-1.5 pl-3 text-right num text-[var(--clp-ink-3)] w-14">{total ? `${Math.round(((designs.by_status[r.key] ?? 0) / total) * 100)}%` : "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="mt-2 pt-2 border-t border-[var(--clp-border)] flex justify-between text-[12.5px]">
          <span className="text-[var(--clp-ink-2)]">Approved by a checker</span>
          <span className="num font-semibold">{designs.by_review.approved ?? 0} of {total}</span>
        </div>
      </div>
    </Card>
  );
}

export function DashboardPage() {
  useTab("Dashboard");
  const { data, isLoading, error } = useDashboard();
  const elements = useElements();
  const me = useAuth((s) => s.me);
  const navigate = useNavigate();

  if (isLoading) return <div className="p-6 text-[var(--clp-ink-3)]">Loading dashboard</div>;
  if (error || !data) return <div className="p-6 text-[var(--clp-bad)]" role="alert">The dashboard could not be loaded. {(error as Error | null)?.message}</div>;

  const active = data.projects.by_status.active ?? 0;
  const ok = data.designs.by_status.ok ?? 0;
  // "2 beams, 1 combined footing": the registry's titles without the "RCC" every one of them carries
  const names = Object.fromEntries((elements.data ?? []).map((e) => [e.type, e.title.replace(/^RCC /, "")]));
  const byType = Object.entries(data.designs.by_type).map(([t, n]) => `${n} ${names[t] ?? t.replace(/_/g, " ")}${n === 1 ? "" : "s"}`).join(", ");
  return (
    <div className="p-5 max-w-[1400px] mx-auto">
      <PageHeader title={`Welcome, ${me?.full_name.split(" ")[0] ?? ""}`} subtitle={me?.organization.name}>
        <Button variant="outlined" component={Link} to="/projects">Open projects</Button>
        <Button variant="contained" component={Link} to="/structural">New design</Button>
      </PageHeader>

      <div className="grid grid-cols-2 xl:grid-cols-4 gap-3">
        <Tile label="Active projects" value={active} note={`${data.projects.total} in the register`} />
        <Tile label="Designs" value={data.designs.total} note={byType} />
        <Tile label="All checks OK" value={data.designs.total ? `${Math.round((ok / data.designs.total) * 100)}%` : "-"} note={data.designs.total ? `${ok} of ${data.designs.total} designs` : "No designs yet"} />
        <Tile label="Awaiting approval" value={data.designs.awaiting_approval} note="Passing designs not yet checked" />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)] gap-3 mt-3">
        <ActivityChart data={data.design_activity} />
        <StatusBreakdown designs={data.designs} />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)] gap-3 mt-3">
        <Card title="Recent designs">
          {data.recent_designs.length === 0 ? (
            <Empty title="No designs yet">
              <span>Create a project, then design its first member.</span>
              <Button variant="contained" component={Link} to="/structural">Start a design</Button>
            </Empty>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-[12.5px] border-collapse">
                <thead>
                  <tr className="text-left text-[11px] text-[var(--clp-ink-3)] border-b border-[var(--clp-border)]">
                    <th className="py-1.5 px-3 font-semibold">Member</th><th className="py-1.5 px-2 font-semibold">Project</th><th className="py-1.5 px-2 font-semibold">Result</th>
                    <th className="py-1.5 px-2 font-semibold">Utilisation</th><th className="py-1.5 px-2 font-semibold">Review</th><th className="py-1.5 px-3 font-semibold text-right">Updated</th>
                  </tr>
                </thead>
                <tbody>
                  {data.recent_designs.map((d) => (
                    <tr key={d.id} onClick={() => navigate(`/designs/${d.id}`)} className="border-b border-[var(--clp-border)] last:border-0 cursor-pointer hover:bg-[var(--clp-panel-2)]">
                      <td className="py-1.5 px-3"><Link to={`/designs/${d.id}`} className="font-semibold text-[var(--clp-accent)] no-underline hover:underline" onClick={(e) => e.stopPropagation()}>{titleCase(d.element_type)} {d.name}</Link> <span className="text-[var(--clp-ink-3)]">R{d.revision}</span></td>
                      <td className="py-1.5 px-2 truncate max-w-[220px]">{d.project_code} <span className="text-[var(--clp-ink-3)]">{d.project_name}</span></td>
                      <td className="py-1.5 px-2"><StatusChip status={d.status} /></td>
                      <td className="py-1.5 px-2"><Utilisation value={d.max_utilisation} /></td>
                      <td className="py-1.5 px-2"><ReviewChip status={d.review_status} /></td>
                      <td className="py-1.5 px-3 text-right text-[var(--clp-ink-2)] whitespace-nowrap" title={fmtDateTime(d.updated_at)}>{timeAgo(d.updated_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
        <Card title="Activity">
          {data.activity.length === 0 ? <Empty title="Nothing yet" /> : (
            <ul className="m-0 p-0 list-none max-h-[320px] overflow-y-auto">
              {data.activity.map((a) => (
                <li key={a.id} className="px-3 py-2 border-b border-[var(--clp-border)] last:border-0">
                  <div className="text-[12.5px]">{a.summary}</div>
                  <div className="text-[11px] text-[var(--clp-ink-3)]">{a.user_name}, {timeAgo(a.created_at)}</div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}
