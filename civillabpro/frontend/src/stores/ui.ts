import type { ReactNode } from "react";
import { create } from "zustand";

export interface WorkspaceTab { path: string; title: string }
export interface RibbonAction { id: string; label: string; icon: ReactNode; onClick: () => void; disabled?: boolean; hint?: string; shortcut?: string; primary?: boolean }
export interface RibbonGroup { title: string; actions: RibbonAction[] }

function load<T>(key: string, fallback: T): T {
  try { const v = localStorage.getItem(key); return v ? (JSON.parse(v) as T) : fallback; } catch { return fallback; }
}
function save(key: string, value: unknown) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* preference not kept */ }
}

interface UiState {
  sidebarCollapsed: boolean;
  toggleSidebar: () => void;
  tabs: WorkspaceTab[];
  openTab: (tab: WorkspaceTab) => void;
  closeTab: (path: string) => WorkspaceTab | null; // returns the tab to show next
  paletteOpen: boolean;
  setPaletteOpen: (open: boolean) => void;
  calculatorOpen: boolean;
  setCalculatorOpen: (open: boolean) => void;
  shortcutsOpen: boolean;
  setShortcutsOpen: (open: boolean) => void;
  ribbonTab: string | null; // contextual tab title, e.g. "Design"
  ribbonGroups: RibbonGroup[];
  setRibbon: (tab: string | null, groups: RibbonGroup[]) => void;
  toast: { message: string; severity: "success" | "error" | "info" } | null;
  notify: (message: string, severity?: "success" | "error" | "info") => void;
  clearToast: () => void;
}

export const useUi = create<UiState>((set, get) => ({
  sidebarCollapsed: load("clp.sidebar", false),
  toggleSidebar: () => { const v = !get().sidebarCollapsed; save("clp.sidebar", v); set({ sidebarCollapsed: v }); },
  tabs: [],
  openTab: (tab) => set((s) => {
    const i = s.tabs.findIndex((t) => t.path === tab.path);
    if (i < 0) return { tabs: [...s.tabs, tab] };
    if (s.tabs[i].title === tab.title) return s;
    const tabs = s.tabs.slice();
    tabs[i] = tab;
    return { tabs };
  }),
  closeTab: (path) => {
    const tabs = get().tabs;
    const i = tabs.findIndex((t) => t.path === path);
    if (i < 0) return null;
    const next = tabs.filter((t) => t.path !== path);
    set({ tabs: next });
    return next[Math.min(i, next.length - 1)] ?? null;
  },
  paletteOpen: false,
  setPaletteOpen: (paletteOpen) => set({ paletteOpen }),
  calculatorOpen: false,
  setCalculatorOpen: (calculatorOpen) => set({ calculatorOpen }),
  shortcutsOpen: false,
  setShortcutsOpen: (shortcutsOpen) => set({ shortcutsOpen }),
  ribbonTab: null,
  ribbonGroups: [],
  setRibbon: (ribbonTab, ribbonGroups) => set({ ribbonTab, ribbonGroups }),
  toast: null,
  notify: (message, severity = "info") => set({ toast: { message, severity } }),
  clearToast: () => set({ toast: null }),
}));
