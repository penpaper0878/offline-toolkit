import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type { DashboardSummary, Design, DesignResult, DesignSummary, ElementSpec, Me, Project, ProjectPage, RoleInfo, SearchHit, User } from "./types";

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
      for (const key of ["projects", "project", "designs", "design", "dashboard", "users", "search"]) void qc.invalidateQueries({ queryKey: [key] });
    },
  });
}
