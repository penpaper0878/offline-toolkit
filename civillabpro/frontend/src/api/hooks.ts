import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type {
  DashboardSummary, Design, DesignQuantities, MeasurementBook, DesignResult, DesignSummary, ElementSpec, Estimate, EstimateDoc, EstimateResult, EstimateSummary, Me, Project,
  ProjectPage, RateAnalysis, RoleInfo, SearchHit, SorBook, SorItem, User,
} from "./types";

export const keys = {
  me: ["me"] as const,
  dashboard: ["dashboard"] as const,
  projects: (q = "", status = "") => ["projects", q, status] as const,
  project: (id: string) => ["project", id] as const,
  designs: (projectId: string) => ["designs", projectId] as const,
  design: (id: string) => ["design", id] as const,
  elements: ["elements"] as const,
  users: ["users"] as const,
};

export const useMe = (enabled: boolean) => useQuery({ queryKey: keys.me, queryFn: () => api<Me>("/auth/me"), enabled, staleTime: 5 * 60_000 });
export const useDashboard = () => useQuery({ queryKey: keys.dashboard, queryFn: () => api<DashboardSummary>("/dashboard/summary") });

export function useProjects(q = "", status = "") {
  const params = new URLSearchParams({ limit: "200" });
  if (q) params.set("q", q);
  if (status) params.set("status", status);
  return useQuery({ queryKey: keys.projects(q, status), queryFn: () => api<ProjectPage>(`/projects?${params}`), placeholderData: keepPreviousData });
}
export const useProject = (id: string | undefined) =>
  useQuery({ queryKey: keys.project(id ?? ""), queryFn: () => api<Project>(`/projects/${id}`), enabled: !!id });
export const useDesigns = (projectId: string | undefined) =>
  useQuery({ queryKey: keys.designs(projectId ?? ""), queryFn: () => api<DesignSummary[]>(`/projects/${projectId}/designs`), enabled: !!projectId });
export const useDesign = (id: string | undefined) =>
  useQuery({ queryKey: keys.design(id ?? ""), queryFn: () => api<Design>(`/designs/${id}`), enabled: !!id });
export const useElements = () => useQuery({ queryKey: keys.elements, queryFn: () => api<ElementSpec[]>("/structural/elements"), staleTime: Infinity });
export const useUsers = (enabled = true) => useQuery({ queryKey: keys.users, queryFn: () => api<User[]>("/users"), enabled });
export const useRoles = () => useQuery({ queryKey: ["roles"], queryFn: () => api<RoleInfo[]>("/users/roles"), staleTime: Infinity });

/** Live calculation: one request per distinct set of inputs, the previous result stays on screen meanwhile. */
export function useCalculation(elementType: string | undefined, inputs: Record<string, unknown> | null) {
  return useQuery({
    queryKey: ["calculate", elementType, inputs],
    queryFn: ({ signal }) => api<DesignResult>(`/structural/${elementType}/calculate`, { method: "POST", body: inputs, signal }),
    enabled: !!elementType && inputs !== null,
    placeholderData: keepPreviousData,
    retry: false,
    staleTime: Infinity,
    gcTime: 60_000,
  });
}

export function useSearch(q: string) {
  return useQuery({
    queryKey: ["search", q],
    queryFn: ({ signal }) => api<SearchHit[]>(`/search?q=${encodeURIComponent(q)}`, { signal }),
    enabled: q.trim().length >= 2,
    placeholderData: keepPreviousData,
  });
}

/** Mutation that refreshes everything a change to projects or designs can touch. */
export function useInvalidatingMutation<TIn, TOut>(fn: (input: TIn) => Promise<TOut>) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      for (const key of ["projects", "project", "designs", "design", "dashboard", "users", "search", "estimates", "estimate", "sor-books", "rate-analyses", "measurement-book"]) {
        void qc.invalidateQueries({ queryKey: [key] });
      }
    },
  });
}

// ----------------------------------------------------------------------------- quantity estimation

export const useSorBooks = () => useQuery({ queryKey: ["sor-books"], queryFn: () => api<SorBook[]>("/sor-books") });
export function useSorItems(bookId: string, q: string) {
  const params = new URLSearchParams({ q, limit: "100" });
  return useQuery({ queryKey: ["sor-books", bookId, "items", q], queryFn: () => api<{ items: SorItem[]; total: number }>(`/sor-books/${bookId}/items?${params}`),
    enabled: !!bookId, placeholderData: keepPreviousData });
}
export const useRateAnalyses = () => useQuery({ queryKey: ["rate-analyses"], queryFn: () => api<RateAnalysis[]>("/rate-analyses") });
export const useEstimates = (projectId?: string) => useQuery({
  queryKey: ["estimates", projectId ?? "all"], queryFn: () => api<EstimateSummary[]>(projectId ? `/projects/${projectId}/estimates` : "/estimates") });
export const useEstimate = (id: string | undefined) => useQuery({ queryKey: ["estimate", id ?? ""], queryFn: () => api<Estimate>(`/estimates/${id}`), enabled: !!id });
export const useDesignQuantities = (projectId: string | undefined) => useQuery({
  queryKey: ["designs", projectId ?? "", "quantities"], queryFn: () => api<DesignQuantities[]>(`/projects/${projectId}/design-quantities`), enabled: !!projectId });

/** The quantities, amounts and abstract of the document being edited, worked out by the server without saving it. */
export function useEstimatePreview(id: string | undefined, doc: EstimateDoc | null) {
  return useQuery({
    queryKey: ["estimate-preview", id, doc],
    queryFn: ({ signal }) => api<EstimateResult>(`/estimates/${id}/preview`, { method: "POST", body: doc, signal }),
    enabled: !!id && doc !== null, placeholderData: keepPreviousData, retry: false,
  });
}
export const useMeasurementBook = (estimateId: string | undefined) => useQuery({
  queryKey: ["measurement-book", estimateId ?? ""], queryFn: () => api<MeasurementBook>(`/estimates/${estimateId}/measurement-book`), enabled: !!estimateId });
