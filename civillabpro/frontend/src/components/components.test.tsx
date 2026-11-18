import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { DrawingView, SchemaProp, Sheet } from "../api/types";
import { CalcSheet, ChecksTable } from "./CalcSheet";
import { renderPrimitives } from "./DrawingCanvas";
import { Fx, fxNodes } from "./Fx";
import { isVisible, PropertyGrid, validateAll, validateField } from "./PropertyGrid";

describe("Fx markup", () => {
  it("renders subscripts, Greek letters, powers and signs", () => {
    const { container } = render(<Fx>{"tau_c,max >= tau_v = V_u x 10^3 / (b d), f_ck <= 55, gamma b D, sqrt(d_b')"}</Fx>);
    expect(container.textContent).toBe("τc,max ≥ τv = Vu × 103 / (b d), fck ≤ 55, γ b D, √(db')");
    expect([...container.querySelectorAll("sub")].map((s) => s.textContent)).toEqual(["c,max", "v", "u", "ck", "b"]);
    expect(container.querySelector("sup")?.textContent).toBe("3");
  });

  it("renders a symbol with its own subscript as a power, and decimal powers", () => {
    const { container } = render(<Fx>{"(M_ux/M_ux1)^alpha_n + (90/125)^1.660"}</Fx>);
    expect(container.textContent).toBe("(Mux/Mux1)αn + (90/125)1.660");
    expect([...container.querySelectorAll("sup")].map((s) => s.textContent)).toEqual(["αn", "1.660"]);
  });

  it("leaves words alone in prose: the x axis is not a product", () => {
    const { container } = render(<span>{fxNodes("Moment capacity about x at P_u, about the x axis", true)}</span>);
    expect(container.textContent).toBe("Moment capacity about x at Pu, about the x axis");
    const { container: eq } = render(<span>{fxNodes("0.87 x 500")}</span>);
    expect(eq.textContent).toBe("0.87 × 500");
  });

  it("raises the power in units and leaves plain words alone", () => {
    const { container } = render(<Fx>N/mm2 and kN/m3 for the maximum beam</Fx>);
    expect([...container.querySelectorAll("sup")].map((s) => s.textContent)).toEqual(["2", "3"]);
    expect(container.textContent).toBe("N/mm2 and kN/m3 for the maximum beam");
  });
});

const PROPS: Record<string, SchemaProp> = {
  mode: { title: "Input mode", enum: ["loads", "forces"], group: "Loading", labels: { loads: "Loads (UDL)", forces: "Factored forces" } },
  width_mm: { title: "Width b", type: "number", minimum: 150, maximum: 2000, unit: "mm", group: "Geometry" },
  cover: { title: "Cover", anyOf: [{ type: "number", minimum: 15, maximum: 100 }, { type: "null" }], unit: "mm", group: "Geometry", description: "Blank takes Table 16" },
  dead: { title: "Dead load", type: "number", minimum: 0, unit: "kN/m", group: "Loading", show_if: { mode: "loads" } },
  mu: { title: "Moment", anyOf: [{ type: "number", exclusiveMinimum: 0 }, { type: "null" }], unit: "kN m", group: "Loading", show_if: { mode: "forces" } },
  self: { title: "Add self-weight", type: "boolean", group: "Loading" },
};

describe("property grid", () => {
  it("validates against the schema limits", () => {
    expect(validateField(PROPS.width_mm, 100)).toBe("Not less than 150.");
    expect(validateField(PROPS.width_mm, 2500)).toBe("Not more than 2000.");
    expect(validateField(PROPS.width_mm, null)).toBe("Enter a value.");
    expect(validateField(PROPS.width_mm, Number.NaN)).toBe("Enter a number.");
    expect(validateField(PROPS.cover, null)).toBeNull(); // optional
    expect(validateField(PROPS.mu, 0)).toBe("Greater than 0.");
    expect(validateField(PROPS.width_mm, 230)).toBeNull();
  });

  it("ignores rows that are hidden for the current mode", () => {
    const values = { mode: "loads", width_mm: 230, cover: null, dead: -1, mu: 0, self: true };
    expect(isVisible(PROPS.mu, values)).toBe(false);
    expect(validateAll(PROPS, values)).toEqual({ dead: "Not less than 0." });
  });

  it("shows a row whose condition lists several values when any of them is chosen", () => {
    const flange = { title: "Flange thickness", type: "number", group: "Geometry", show_if: { section: ["t_beam", "l_beam"] } };
    expect(isVisible(flange, { section: "t_beam" })).toBe(true);
    expect(isVisible(flange, { section: "l_beam" })).toBe(true);
    expect(isVisible(flange, { section: "rectangular" })).toBe(false);
  });

  it("renders groups, units and conditional rows, and reports edits", () => {
    const onChange = vi.fn();
    render(<PropertyGrid properties={PROPS} values={{ mode: "loads", width_mm: 230, cover: null, dead: 12, mu: null, self: true }} errors={{ width_mm: "Not less than 150." }} onChange={onChange} />);
    expect(screen.getByText("Geometry")).toBeInTheDocument();
    expect(screen.getByLabelText("Dead load")).toHaveValue("12");
    expect(screen.queryByLabelText("Moment")).toBeNull();
    expect(screen.getByRole("alert")).toHaveTextContent("Not less than 150.");
    expect(screen.getByLabelText("Cover")).toHaveAttribute("placeholder", "auto");

    fireEvent.change(screen.getByLabelText("Width b"), { target: { value: "300" } });
    expect(onChange).toHaveBeenLastCalledWith("width_mm", 300);
    fireEvent.change(screen.getByLabelText("Width b"), { target: { value: "" } });
    expect(onChange).toHaveBeenLastCalledWith("width_mm", null);
    fireEvent.change(screen.getByLabelText("Input mode"), { target: { value: "forces" } });
    expect(onChange).toHaveBeenLastCalledWith("mode", "forces");
    fireEvent.click(screen.getByLabelText("Add self-weight"));
    expect(onChange).toHaveBeenLastCalledWith("self", false);
  });
});

const SHEET: Sheet = {
  flags: [{ level: "warning", message: "Check that the leg fits the supporting member.", ref: "IS 456:2000, Cl. 26.2.1" }],
  sections: [{
    title: "4. Flexure",
    items: [
      { kind: "step", ref: "IS 456:2000, Annex G-1.1(c)", title: "Limiting moment of resistance", eq: "M_u,lim = 0.36 f_ck b x_u,max (d - 0.42 x_u,max)", sub: "0.36 x 25 x 230", value: 124.5622, unit: "kN m", dp: 2 },
      { kind: "check", id: "moment", ref: "IS 456:2000, Cl. 38.1", title: "Moment of resistance as detailed", lhs_label: "M_u", lhs: 75.78, op: "<=", rhs_label: "M_u,R", rhs: 95.65, unit: "kN m", ok: true, util: 0.792, dp: 2 },
      { kind: "check", id: "deflection", ref: "IS 456:2000, Cl. 23.2.1", title: "Span to effective depth ratio", lhs_label: "l/d", lhs: 28, op: "<=", rhs_label: "allowable", rhs: 23.45, unit: "", ok: false, util: 1.194, dp: 2 },
    ],
  }],
};

describe("calculation sheet", () => {
  it("shows every line with its clause, value and verdict", () => {
    render(<CalcSheet sheet={SHEET} />);
    expect(screen.getByText("4. Flexure")).toBeInTheDocument();
    expect(screen.getByText("IS 456:2000, Annex G-1.1(c)")).toBeInTheDocument();
    expect(screen.getByText("124.56")).toBeInTheDocument();
    expect(screen.getByText("OK")).toBeInTheDocument();
    expect(screen.getByText("Not OK")).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent("Check that the leg fits");
  });

  it("lists failed checks first", () => {
    render(<ChecksTable sheet={SHEET} />);
    const rows = screen.getAllByRole("row").slice(1);
    expect(rows[0]).toHaveTextContent("Span to effective depth ratio");
    expect(rows[0]).toHaveTextContent("Not OK");
    expect(rows[1]).toHaveTextContent("0.79");
  });
});

describe("drawing renderer", () => {
  const view: DrawingView = {
    id: "section", title: "Section A-A", scale_note: "to scale", bounds: [-50, -60, 400, 460],
    items: [
      { t: "polyline", points: [[0, 0], [230, 0], [230, 450], [0, 450]], closed: true, layer: "concrete" },
      { t: "circle", cx: 46, cy: 46, r: 8, layer: "rebar", filled: true },
      { t: "line", x1: 0, y1: 0, x2: 10, y2: 10, layer: "stirrup" },
      { t: "dim", x1: 0, y1: 0, x2: 230, y2: 0, offset: -44, horizontal: true, text: "230", h: 20, layer: "dimension" },
      { t: "dim", x1: 0, y1: 0, x2: 0, y2: 450, offset: -44, horizontal: false, text: "450", h: 20, layer: "dimension" },
      { t: "leader", x: 184, y: 46, tx: 260, ty: 4, text: "3-T16", h: 20, layer: "text" },
      { t: "text", x: 115, y: -100, text: "Cover 30 mm", h: 16, anchor: "middle", layer: "text" },
    ],
  };

  it("mirrors y so the model's upward axis draws upward on screen", () => {
    const { container } = render(<svg>{renderPrimitives(view.items, view.bounds[3])}</svg>);
    // bottom-left bar at y = 46 in the model sits near the bottom of a 460-high view
    expect(container.querySelector("circle")).toHaveAttribute("cy", String(460 - 46));
    expect(container.querySelector("polygon")).toHaveAttribute("points", "0,460 230,460 230,10 0,10");
  });

  it("draws dimensions with their text and leaders with their label", () => {
    const { container } = render(<svg>{renderPrimitives(view.items, view.bounds[3])}</svg>);
    const texts = [...container.querySelectorAll("text")].map((t) => t.textContent);
    expect(texts).toEqual(["230", "450", "3-T16", "Cover 30 mm"]);
    expect(container.querySelectorAll("line").length).toBe(1 + 5 + 5 + 1); // stirrup, two dimensions (line, 2 extensions, 2 ticks), leader
    expect(container.innerHTML).not.toMatch(/NaN|undefined/);
  });
});

describe("chart view", () => {
  it("lists every series in its table view", async () => {
    const { ChartView } = await import("./ChartView");
    const chart = {
      id: "interaction_x", title: "Interaction about the x axis, 12-T12", x: { label: "M_ux", unit: "kN m" }, y: { label: "P_u", unit: "kN" },
      series: [
        { name: "Capacity", kind: "line" as const, points: [[150, 0], [160, 400], [0, 2000]] as [number, number][] },
        { name: "Design forces", kind: "point" as const, points: [[90, 1200], [90, 1200]] as [number, number][], labels: ["Case 1", "Case 2"] },
      ],
      note: "Uniaxial capacity by strain compatibility.",
    };
    render(<ChartView chart={chart} />);
    expect(screen.getByRole("img")).toHaveAccessibleName(/Capacity and Design forces/);
    fireEvent.click(screen.getByRole("button", { name: "Table" }));
    expect(screen.getByText("Capacity")).toBeInTheDocument();
    expect(screen.getByText("Case 2")).toBeInTheDocument();
    expect(screen.getAllByRole("row")).toHaveLength(2 + 3 + 2); // two header rows, three curve points, two design points
  });
});
