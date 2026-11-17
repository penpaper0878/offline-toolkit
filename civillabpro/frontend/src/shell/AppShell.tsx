import Alert from "@mui/material/Alert";
import Dialog from "@mui/material/Dialog";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Snackbar from "@mui/material/Snackbar";
import { Suspense, useEffect } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { useUi } from "../stores/ui";
import { CommandPalette } from "./CommandPalette";
import { FloatingCalculator } from "./FloatingCalculator";
import { isTyping, SHORTCUTS, useThemeToggle } from "./hooks";
import { Ribbon } from "./Ribbon";
import { Sidebar } from "./Sidebar";
import { StatusBar } from "./StatusBar";
import { TabBar } from "./TabBar";

export function AppShell() {
  const ui = useUi();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const theme = useThemeToggle();

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const key = e.key.toLowerCase();
      if ((e.ctrlKey || e.metaKey) && key === "k") { e.preventDefault(); ui.setPaletteOpen(!ui.paletteOpen); return; }
      if (e.altKey && !e.ctrlKey && !e.metaKey) {
        const routes: Record<string, string> = { "1": "/", "2": "/projects", "3": "/structural" };
        if (routes[key]) { e.preventDefault(); navigate(routes[key]); }
        else if (key === "c") { e.preventDefault(); ui.setCalculatorOpen(!ui.calculatorOpen); }
        else if (key === "t") { e.preventDefault(); theme.toggle(); }
        else if (key === "b") { e.preventDefault(); ui.toggleSidebar(); }
        else if (key === "w") { e.preventDefault(); const next = ui.closeTab(pathname); navigate(next?.path ?? "/"); }
        return;
      }
      if (e.key === "?" && !isTyping(e.target)) { e.preventDefault(); ui.setShortcutsOpen(true); }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [ui, navigate, pathname, theme]);

  return (
    <div className="h-full flex flex-col">
      <Ribbon />
      <div className="flex-1 min-h-0 flex">
        <Sidebar />
        <div className="flex-1 min-w-0 flex flex-col">
          <TabBar />
          <main className="flex-1 min-h-0 overflow-auto">
            <Suspense fallback={<div className="p-6 text-[var(--clp-ink-3)]">Loading</div>}>
              <Outlet />
            </Suspense>
          </main>
        </div>
      </div>
      <StatusBar />
      <CommandPalette />
      <FloatingCalculator />
      <Dialog open={ui.shortcutsOpen} onClose={() => ui.setShortcutsOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle>Keyboard shortcuts</DialogTitle>
        <DialogContent>
          <table className="w-full text-[13px]">
            <tbody>
              {SHORTCUTS.map((s) => (
                <tr key={s.keys} className="border-b border-[var(--clp-border)] last:border-0">
                  <td className="py-1.5 pr-3 whitespace-nowrap"><kbd className="px-1.5 py-0.5 rounded border border-[var(--clp-border)] bg-[var(--clp-panel-2)] text-xs">{s.keys}</kbd></td>
                  <td className="py-1.5">{s.action}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </DialogContent>
      </Dialog>
      <Snackbar open={!!ui.toast} autoHideDuration={ui.toast?.severity === "error" ? 7000 : 3500} onClose={ui.clearToast} anchorOrigin={{ vertical: "bottom", horizontal: "center" }}>
        <Alert severity={ui.toast?.severity ?? "info"} variant="filled" onClose={ui.clearToast}>{ui.toast?.message}</Alert>
      </Snackbar>
    </div>
  );
}
