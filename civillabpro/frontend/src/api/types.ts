// Mirrors the backend response models (app/modules/*/schemas.py).

export interface TokenPair { access_token: string; refresh_token: string; token_type: "bearer"; expires_in: number }
export type Role = "owner" | "admin" | "engineer" | "reviewer" | "viewer";
export interface User { id: string; email: string; full_name: string; designation: string; role: Role; is_active: boolean; last_login_at: string | null; created_at: string }
export interface Me extends User { organization: { id: string; name: string; kind: string }; permissions: string[] }
export interface RoleInfo { role: Role; label: string; permissions: string[] }

export interface Project {
  id: string; code: string; name: string; client: string; location: string; state: string; project_type: string;
  status: "planning" | "active" | "on_hold" | "completed"; description: string; start_date: string | null; end_date: string | null;
  created_at: string; updated_at: string; design_count: number;
}
export interface ProjectPage { items: Project[]; total: number }

export interface Step { kind: "step"; ref: string; title: string; eq: string; sub: string; value: number | string | null; unit: string; dp: number }
export interface Check {
  kind: "check"; id: string; ref: string; title: string; lhs_label: string; lhs: number; op: "<=" | ">="; rhs_label: string; rhs: number;
  unit: string; ok: boolean; util: number | null; dp: number;
}
export interface Flag { level: "info" | "warning" | "error"; message: string; ref: string }
export interface Sheet { sections: { title: string; items: (Step | Check)[] }[]; flags: Flag[] }

export interface BbsItem {
  mark: string; description: string; shape: string; dia: number; count: number; dims: Record<string, number>; cutting_length_mm: number;
  total_length_m: number; unit_weight_kg_m: number; weight_kg: number; formula: string;
}
export interface Bbs { member: string; members: number; items: BbsItem[]; summary: { dia: number; length_m: number; weight_kg: number }[]; total_weight_kg: number; stirrup_count: number; notes: string[] }
export interface Quantities { length_m: number; concrete_m3: number; formwork_m2: number; steel_kg: number; steel_kg_per_m3: number | null; basis: string[] }

export type Layer = "concrete" | "rebar" | "stirrup" | "dimension" | "text" | "support" | "centerline";
export type Primitive =
  | { t: "line"; x1: number; y1: number; x2: number; y2: number; layer: Layer }
  | { t: "polyline"; points: [number, number][]; closed: boolean; layer: Layer }
  | { t: "circle"; cx: number; cy: number; r: number; layer: Layer; filled: boolean }
  | { t: "text"; x: number; y: number; text: string; h: number; anchor: "start" | "middle" | "end"; layer: Layer }
  | { t: "dim"; x1: number; y1: number; x2: number; y2: number; offset: number; horizontal: boolean; text: string; h: number; layer: Layer }
  | { t: "leader"; x: number; y: number; tx: number; ty: number; text: string; h: number; layer: Layer };
export interface DrawingView { id: string; title: string; scale_note: string; items: Primitive[]; bounds: [number, number, number, number] }
export interface Drawing { title: string; views: DrawingView[]; notes: string[] }

export interface ChartSeries { name: string; kind: "line" | "point"; points: [number, number][]; labels?: string[] }
export interface Chart { id: string; title: string; x: { label: string; unit: string }; y: { label: string; unit: string }; series: ChartSeries[]; note?: string }

export interface KeyResult { label: string; sym: string; value: number | string | null; unit: string; dp: number }
export interface DesignResult {
  element_type: string; engine_version: string; code_basis: string[]; status: "ok" | "not_ok" | "stopped"; stop_message: string | null;
  checks_passed: number; checks_total: number; max_utilisation: number | null; key_results: KeyResult[]; data: Record<string, unknown>;
  reinforcement: Record<string, unknown> | null; sheet: Sheet; bbs: Bbs | null; quantities: Quantities | null; drawing: Drawing | null;
  charts?: Chart[] | null;
}

export interface SchemaProp {
  title?: string; description?: string; type?: string; enum?: (string | number)[]; default?: unknown; minimum?: number; maximum?: number;
  exclusiveMinimum?: number; minLength?: number; maxLength?: number; anyOf?: SchemaProp[]; group?: string; unit?: string;
  show_if?: Record<string, unknown>; labels?: Record<string, string>;
}
export interface ElementSpec {
  type: string; title: string; description: string; engine_version: string; code_basis: string[]; limitations: string[];
  defaults: Record<string, unknown>; input_schema: { properties: Record<string, SchemaProp> };
}

export interface DesignSummary {
  id: string; project_id: string; element_type: string; name: string; status: "ok" | "not_ok" | "stopped"; review_status: "draft" | "approved";
  revision: number; engine_version: string; max_utilisation: number | null; designed_by_name: string; approved_by_name: string;
  approved_at: string | null; created_at: string; updated_at: string;
}
export interface Design extends DesignSummary { inputs: Record<string, unknown>; result: DesignResult }

export interface DashboardSummary {
  projects: { total: number; by_status: Record<string, number> };
  designs: { total: number; by_status: Record<string, number>; by_review: Record<string, number>; by_type: Record<string, number>; awaiting_approval: number };
  recent_designs: (Pick<DesignSummary, "id" | "project_id" | "element_type" | "name" | "status" | "review_status" | "revision" | "max_utilisation" | "designed_by_name" | "updated_at"> & { project_code: string; project_name: string })[];
  design_activity: { date: string; count: number }[];
  activity: { id: string; user_name: string; action: string; summary: string; entity_type: string; entity_id: string | null; created_at: string }[];
}
export interface SearchHit { kind: "project" | "design"; id: string; title: string; subtitle: string; project_id: string; element_type?: string }
