/**
 * The platform's module map. A module is "available" once its backend context and
 * workspace exist; planned ones are listed with their roadmap phase so the
 * navigation shows where the product is going without pretending they work.
 */
export interface ModuleEntry {
  id: string;
  title: string;
  path?: string; // set only for available modules
  phase: number;
  status: "available" | "planned";
  summary: string;
}

export const MODULES: ModuleEntry[] = [
  { id: "dashboard", title: "Dashboard", path: "/", phase: 1, status: "available", summary: "Projects, design status and recent activity" },
  { id: "projects", title: "Projects", path: "/projects", phase: 1, status: "available", summary: "Project register and design files" },
  { id: "structural", title: "Structural design", path: "/structural", phase: 1, status: "available", summary: "IS 456 members: beams, continuous beams, columns, slabs, isolated, combined and strap footings" },
  { id: "water", title: "Water engineering", phase: 3, status: "planned", summary: "Demand, networks, reservoirs, pumping (CPHEEO)" },
  { id: "sewerage", title: "Sewerage engineering", phase: 4, status: "planned", summary: "Sewer networks, STP, pumping stations" },
  { id: "highway", title: "Highway engineering", phase: 5, status: "planned", summary: "Pavement and geometric design (IRC, MoRTH)" },
  { id: "estimation", title: "Quantity estimation", phase: 2, status: "planned", summary: "BOQ, rate analysis, SOR, measurement and bills" },
  { id: "lims", title: "Laboratory (LIMS)", phase: 6, status: "planned", summary: "Material tests and NABL reports" },
  { id: "gis", title: "GIS", phase: 7, status: "planned", summary: "Maps, utility networks, PostGIS" },
  { id: "pm", title: "Project management", phase: 8, status: "planned", summary: "Schedule, resources, DPR, quality and safety" },
  { id: "ai", title: "AI assistant", phase: 9, status: "planned", summary: "Code explanations, calculation and drawing review" },
  { id: "standards", title: "Standards library", phase: 2, status: "planned", summary: "Searchable register of IS, IRC, CPHEEO, MoRTH" },
];
