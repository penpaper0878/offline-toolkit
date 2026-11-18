import AddOutlined from "@mui/icons-material/AddOutlined";
import FitScreenOutlined from "@mui/icons-material/FitScreenOutlined";
import RemoveOutlined from "@mui/icons-material/RemoveOutlined";
import IconButton from "@mui/material/IconButton";
import Tooltip from "@mui/material/Tooltip";
import { type PointerEvent, type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { DrawingView, Layer, Primitive } from "../api/types";

const COLOUR: Record<Layer, string> = {
  concrete: "var(--dwg-concrete)", rebar: "var(--dwg-rebar)", stirrup: "var(--dwg-stirrup)", dimension: "var(--dwg-dim)",
  text: "var(--dwg-concrete)", support: "var(--dwg-support)", centerline: "var(--dwg-dim)",
};
const WIDTH: Record<Layer, number> = { concrete: 1.6, rebar: 2, stirrup: 1.1, dimension: 0.8, text: 0.8, support: 1.1, centerline: 0.8 };

interface Box { x: number; y: number; w: number; h: number }

/** Drawing model coordinates are millimetres with y upwards; SVG has y downwards, so y is mirrored about the top of the bounds. */
export function renderPrimitives(items: Primitive[], top: number): ReactNode[] {
  const Y = (y: number) => top - y;
  const out: ReactNode[] = [];
  const text = (key: string, x: number, y: number, s: string, h: number, anchor: "start" | "middle" | "end", fill: string, rotate?: number) => (
    <text key={key} x={x} y={y} fontSize={h} textAnchor={anchor} fill={fill} transform={rotate ? `rotate(${rotate} ${x} ${y})` : undefined} style={{ fontFamily: "inherit" }}>{s}</text>
  );
  items.forEach((it, i) => {
    const stroke = COLOUR[it.layer];
    const common = { stroke, strokeWidth: WIDTH[it.layer], vectorEffect: "non-scaling-stroke" as const, fill: "none" };
    switch (it.t) {
      case "line":
        out.push(<line key={i} x1={it.x1} y1={Y(it.y1)} x2={it.x2} y2={Y(it.y2)} {...common} />);
        break;
      case "polyline": {
        const pts = it.points.map(([x, y]) => `${x},${Y(y)}`).join(" ");
        out.push(it.closed ? <polygon key={i} points={pts} {...common} fill={it.layer === "support" ? "color-mix(in srgb, var(--dwg-support) 22%, transparent)" : "none"} /> : <polyline key={i} points={pts} {...common} />);
        break;
      }
      case "circle":
        out.push(<circle key={i} cx={it.cx} cy={Y(it.cy)} r={it.r} {...common} fill={it.filled ? stroke : "none"} />);
        break;
      case "text":
        out.push(text(`${i}`, it.x, Y(it.y), it.text, it.h, it.anchor, stroke, it.rot ? -it.rot : undefined)); // y runs down on screen
        break;
      case "leader":
        out.push(<line key={`${i}l`} x1={it.x} y1={Y(it.y)} x2={it.tx} y2={Y(it.ty + 0.3 * it.h)} stroke="var(--dwg-dim)" strokeWidth={0.8} vectorEffect="non-scaling-stroke" />);
        // a label to the left of its point is right-aligned, so it reads towards what it marks
        out.push(it.tx < it.x ? text(`${i}t`, it.tx - 0.3 * it.h, Y(it.ty), it.text, it.h, "end", stroke) : text(`${i}t`, it.tx + 0.3 * it.h, Y(it.ty), it.text, it.h, "start", stroke));
        break;
      case "dim": {
        const tick = 0.35 * it.h;
        const thin = { stroke, strokeWidth: 0.6, vectorEffect: "non-scaling-stroke" as const };
        if (it.horizontal) {
          const yd = (it.offset >= 0 ? Math.max(it.y1, it.y2) : Math.min(it.y1, it.y2)) + it.offset;
          out.push(<line key={`${i}d`} x1={it.x1} y1={Y(yd)} x2={it.x2} y2={Y(yd)} {...thin} strokeWidth={0.8} />);
          for (const [k, x, y] of [["a", it.x1, it.y1], ["b", it.x2, it.y2]] as const) {
            out.push(<line key={`${i}e${k}`} x1={x} y1={Y(y)} x2={x} y2={Y(yd)} {...thin} />);
            out.push(<line key={`${i}t${k}`} x1={x - tick} y1={Y(yd - tick)} x2={x + tick} y2={Y(yd + tick)} {...thin} strokeWidth={1.2} />);
          }
          out.push(text(`${i}x`, (it.x1 + it.x2) / 2, Y(yd + 0.3 * it.h), it.text, it.h, "middle", stroke));
        } else {
          const xd = (it.offset >= 0 ? Math.max(it.x1, it.x2) : Math.min(it.x1, it.x2)) + it.offset;
          out.push(<line key={`${i}d`} x1={xd} y1={Y(it.y1)} x2={xd} y2={Y(it.y2)} {...thin} strokeWidth={0.8} />);
          for (const [k, x, y] of [["a", it.x1, it.y1], ["b", it.x2, it.y2]] as const) {
            out.push(<line key={`${i}e${k}`} x1={x} y1={Y(y)} x2={xd} y2={Y(y)} {...thin} />);
            out.push(<line key={`${i}t${k}`} x1={xd - tick} y1={Y(y - tick)} x2={xd + tick} y2={Y(y + tick)} {...thin} strokeWidth={1.2} />);
          }
          out.push(text(`${i}x`, xd - 0.3 * it.h, Y((it.y1 + it.y2) / 2), it.text, it.h, "middle", stroke, -90));
        }
        break;
      }
    }
  });
  return out;
}

function fitBox(view: DrawingView): Box {
  const [xmin, ymin, xmax, ymax] = view.bounds;
  const pad = 0.06 * Math.max(xmax - xmin, ymax - ymin);
  return { x: xmin - pad, y: -pad, w: xmax - xmin + 2 * pad, h: ymax - ymin + 2 * pad };
}

/** A to-scale view with wheel zoom, drag pan and fit. Double-click fits. */
export function DrawingCanvas({ view }: { view: DrawingView }) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [box, setBox] = useState<Box>(() => fitBox(view));
  const drag = useRef<{ px: number; py: number; box: Box } | null>(null);
  const top = view.bounds[3];
  const boundsKey = view.bounds.join(",");
  useEffect(() => { setBox(fitBox(view)); /* refit when the geometry changes size */ // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view.id, boundsKey]);

  const nodes = useMemo(() => renderPrimitives(view.items, top), [view.items, top]);

  const zoom = useCallback((factor: number, cx = 0.5, cy = 0.5) => {
    setBox((b) => {
      const w = b.w * factor, h = b.h * factor;
      return { x: b.x + (b.w - w) * cx, y: b.y + (b.h - h) * cy, w, h };
    });
  }, []);

  // React registers wheel listeners as passive; a native one is needed to stop the page scrolling while zooming.
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const r = svg.getBoundingClientRect();
      zoom(e.deltaY > 0 ? 1.15 : 1 / 1.15, (e.clientX - r.left) / r.width, (e.clientY - r.top) / r.height);
    };
    svg.addEventListener("wheel", onWheel, { passive: false });
    return () => svg.removeEventListener("wheel", onWheel);
  }, [zoom]);

  const onDown = (e: PointerEvent<SVGSVGElement>) => { drag.current = { px: e.clientX, py: e.clientY, box }; e.currentTarget.setPointerCapture(e.pointerId); };
  const onMove = (e: PointerEvent<SVGSVGElement>) => {
    const d = drag.current;
    if (!d) return;
    const r = e.currentTarget.getBoundingClientRect();
    const k = Math.max(d.box.w / r.width, d.box.h / r.height); // drawing units per pixel (preserveAspectRatio: meet)
    setBox({ ...d.box, x: d.box.x - (e.clientX - d.px) * k, y: d.box.y - (e.clientY - d.py) * k });
  };

  return (
    <div className="relative h-full w-full flex flex-col bg-[var(--clp-panel)]">
      <svg
        ref={svgRef}
        role="img"
        aria-label={view.title}
        viewBox={`${box.x} ${box.y} ${box.w} ${box.h}`}
        preserveAspectRatio="xMidYMid meet"
        className="flex-1 min-h-0 w-full touch-none select-none cursor-grab active:cursor-grabbing"
        onPointerDown={onDown}
        onPointerMove={onMove}
        onPointerUp={() => { drag.current = null; }}
        onDoubleClick={() => setBox(fitBox(view))}
      >
        {nodes}
      </svg>
      <div className="no-print absolute top-2 right-2 flex gap-0.5 rounded border border-[var(--clp-border)] bg-[var(--clp-panel)] shadow-sm">
        <Tooltip title="Zoom in"><IconButton aria-label="Zoom in" onClick={() => zoom(1 / 1.3)}><AddOutlined sx={{ fontSize: 16 }} /></IconButton></Tooltip>
        <Tooltip title="Zoom out"><IconButton aria-label="Zoom out" onClick={() => zoom(1.3)}><RemoveOutlined sx={{ fontSize: 16 }} /></IconButton></Tooltip>
        <Tooltip title="Fit (double-click)"><IconButton aria-label="Fit drawing" onClick={() => setBox(fitBox(view))}><FitScreenOutlined sx={{ fontSize: 16 }} /></IconButton></Tooltip>
      </div>
      <div className="shrink-0 h-6 px-3 flex items-center text-[11px] text-[var(--clp-ink-3)] border-t border-[var(--clp-border)]">{view.title}{view.scale_note ? `, ${view.scale_note}` : ""}. Dimensions in mm. Wheel zooms, drag pans.</div>
    </div>
  );
}
