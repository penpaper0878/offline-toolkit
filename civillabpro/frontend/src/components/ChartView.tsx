import Button from "@mui/material/Button";
import { useState } from "react";
import { CartesianGrid, LabelList, Legend, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis } from "recharts";
import type { Chart } from "../api/types";
import { fmt } from "../lib/format";
import { Fx, Prose } from "./Fx";

// Fixed slots by series position: the line series (capacity) is slot 1, the point series (design forces) slot 2.
// Validated as a pair for colour-blind separation in both themes; the series also differ by mark.
const SLOTS = ["var(--viz-series-1)", "var(--viz-series-2)"];

interface Point { x: number; y: number; label?: string; series: string; side: "left" | "right" }

/** Labels read away from each other: in a series of points, the leftmost label goes to the left of its point. */
function sides(points: [number, number][]): ("left" | "right")[] {
  if (points.length < 2) return points.map(() => "right");
  const leftmost = points.reduce((best, p, i) => (p[0] < points[best][0] ? i : best), 0);
  return points.map((_, i) => (i === leftmost ? "left" : "right"));
}

/** An x-y chart from the generic result contract, with a table view of every series. */
export function ChartView({ chart }: { chart: Chart }) {
  const [asTable, setAsTable] = useState(false);
  const axis = (a: Chart["x"]) => `${a.label.replace(/_/g, "")} (${a.unit})`;
  const below = chart.series.some((s) => s.points.some(([, y]) => y < 0)); // hogging moments, for one, are drawn negative
  const data = chart.series.map((s) => {
    const side = sides(s.points);
    return s.points.map(([x, y], i): Point => ({ x, y, label: s.labels?.[i], series: s.name, side: side[i] }));
  });

  return (
    <section className="p-3" aria-label={chart.title}>
      <header className="flex items-center gap-2 mb-1">
        <h3 className="m-0 text-[12.5px] font-semibold"><Prose>{chart.title}</Prose></h3>
        <Button size="small" className="!ml-auto" onClick={() => setAsTable(!asTable)}>{asTable ? "Chart" : "Table"}</Button>
      </header>
      {asTable ? (
        <div className="max-h-[300px] overflow-y-auto">
          {chart.series.map((s, i) => (
            <table key={s.name} className="w-full text-[12px] border-collapse mb-3">
              <caption className="text-left font-semibold text-[11.5px] py-1">{s.name}</caption>
              <thead>
                <tr className="text-left text-[11px] text-[var(--clp-ink-3)] border-b border-[var(--clp-border)]">
                  {s.labels && <th className="py-1 font-semibold">Point</th>}
                  <th className="py-1 font-semibold text-right"><Fx>{chart.x.label}</Fx> ({chart.x.unit})</th>
                  <th className="py-1 font-semibold text-right"><Fx>{chart.y.label}</Fx> ({chart.y.unit})</th>
                </tr>
              </thead>
              <tbody>
                {data[i].map((p, j) => (
                  <tr key={j} className="border-b border-[var(--clp-border)] last:border-0">
                    {s.labels && <td className="py-0.5">{p.label}</td>}
                    <td className="py-0.5 text-right num">{fmt(p.x, 2)}</td>
                    <td className="py-0.5 text-right num">{fmt(p.y, 1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ))}
        </div>
      ) : (
        <div className="h-[236px]" role="img" aria-label={`${chart.title}: ${chart.series.map((s) => s.name).join(" and ")}`}>
          <ResponsiveContainer width="100%" height="100%">
            <ScatterChart margin={{ top: 8, right: 16, bottom: 14, left: 4 }}>
              <CartesianGrid stroke="var(--viz-grid)" />
              <XAxis type="number" dataKey="x" name={chart.x.label} unit="" tick={{ fontSize: 11, fill: "var(--clp-ink-3)" }} tickLine={false}
                axisLine={{ stroke: "var(--viz-axis)" }} domain={[0, "auto"]}
                label={{ value: axis(chart.x), position: "insideBottom", offset: -8, fontSize: 11, fill: "var(--clp-ink-2)" }} />
              <YAxis type="number" dataKey="y" name={chart.y.label} tick={{ fontSize: 11, fill: "var(--clp-ink-3)" }} tickLine={false} axisLine={false}
                domain={[below ? "auto" : 0, "auto"]} width={56}
                label={{ value: axis(chart.y), angle: -90, position: "insideLeft", offset: 6, fontSize: 11, fill: "var(--clp-ink-2)" }} />
              <Tooltip
                cursor={{ stroke: "var(--clp-ink-3)", strokeDasharray: "3 3" }}
                content={({ active, payload }) => {
                  const p = active ? (payload?.[0]?.payload as Point | undefined) : undefined;
                  return p ? (
                    <div className="rounded border border-[var(--clp-border)] bg-[var(--clp-panel)] px-2.5 py-1.5 text-xs shadow-md">
                      <div className="text-[var(--clp-ink-2)]">{p.label ?? p.series}</div>
                      <div className="num"><Fx>{chart.x.label}</Fx> {fmt(p.x, 2)} {chart.x.unit}</div>
                      <div className="num"><Fx>{chart.y.label}</Fx> {fmt(p.y, 1)} {chart.y.unit}</div>
                    </div>
                  ) : null;
                }}
              />
              <Legend verticalAlign="top" height={24} iconSize={10} wrapperStyle={{ fontSize: 11, color: "var(--clp-ink-2)" }} />
              {chart.series.map((s, i) => s.kind === "line" ? (
                <Scatter key={s.name} name={s.name} data={data[i]} fill={SLOTS[i]} line={{ stroke: SLOTS[i], strokeWidth: 2 }} lineType="joint"
                  shape={() => <g />} legendType="line" isAnimationActive={false} />
              ) : (
                <Scatter key={s.name} name={s.name} data={data[i]} fill={SLOTS[Math.min(i, SLOTS.length - 1)]} shape="circle" legendType="circle"
                  stroke="var(--clp-panel)" strokeWidth={2} isAnimationActive={false}>
                  <LabelList
                    dataKey="label"
                    content={(p) => {
                      const pt = data[i][Number(p.index)];
                      if (!pt?.label || p.x === undefined || p.y === undefined) return null;
                      const left = pt.side === "left";
                      // p.x / p.y locate the marker's box; its centre is half the marker size further on
                      const cx = Number(p.x) + Number(p.width ?? 0) / 2, cy = Number(p.y) + Number(p.height ?? 0) / 2;
                      return <text x={cx + (left ? -9 : 9)} y={cy} dy={4} textAnchor={left ? "end" : "start"} fontSize={11} fill="var(--clp-ink-2)">{pt.label}</text>;
                    }}
                  />
                </Scatter>
              ))}
            </ScatterChart>
          </ResponsiveContainer>
        </div>
      )}
      {chart.note && <p className="m-0 mt-1 text-[11.5px] text-[var(--clp-ink-3)]"><Prose>{chart.note}</Prose></p>}
    </section>
  );
}
