import { useColorScheme } from "@mui/material/styles";
import { useEffect } from "react";
import { useLocation } from "react-router-dom";
import { type RibbonGroup, useUi } from "../stores/ui";

/** Registers the current page as a workspace tab. */
export function useTab(title: string | undefined) {
  const { pathname } = useLocation();
  const openTab = useUi((s) => s.openTab);
  useEffect(() => {
    if (title) openTab({ path: pathname, title });
    if (title) document.title = `${title} - CivilLabPro OS`;
  }, [pathname, title, openTab]);
}

/** Shows a contextual ribbon tab while the calling page is mounted. Pass the values the actions depend on as deps. */
export function useRibbon(tab: string, build: () => RibbonGroup[], deps: unknown[]) {
  const setRibbon = useUi((s) => s.setRibbon);
  useEffect(() => {
    setRibbon(tab, build());
    return () => setRibbon(null, []);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, setRibbon, ...deps]);
}

export function useThemeToggle() {
  const { mode, systemMode, setMode } = useColorScheme();
  const resolved = (mode === "system" ? systemMode : mode) ?? "light";
  return { dark: resolved === "dark", toggle: () => setMode(resolved === "dark" ? "light" : "dark") };
}

export function isTyping(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  return !!el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName === "SELECT" || el.isContentEditable);
}

export const SHORTCUTS: { keys: string; action: string }[] = [
  { keys: "Ctrl K", action: "Search everywhere and run commands" },
  { keys: "Alt 1 / 2 / 3", action: "Dashboard / Projects / Structural design" },
  { keys: "Alt C", action: "Floating calculator" },
  { keys: "Alt T", action: "Light or dark theme" },
  { keys: "Alt B", action: "Collapse or expand the sidebar" },
  { keys: "Ctrl S", action: "Save the design (design workspace)" },
  { keys: "Alt R", action: "Download the PDF report (design workspace)" },
  { keys: "Alt W", action: "Close the current tab" },
  { keys: "?", action: "Keyboard shortcuts" },
];
