import ArchitectureOutlined from "@mui/icons-material/ArchitectureOutlined";
import BoltOutlined from "@mui/icons-material/BoltOutlined";
import FolderOpenOutlined from "@mui/icons-material/FolderOpenOutlined";
import SearchOutlined from "@mui/icons-material/SearchOutlined";
import Dialog from "@mui/material/Dialog";
import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useSearch } from "../api/hooks";
import { useAuth } from "../stores/auth";
import { useUi } from "../stores/ui";
import { useThemeToggle } from "./hooks";

interface Item { id: string; title: string; subtitle?: string; icon: ReactNode; group: string; run: () => void }

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => { const t = setTimeout(() => setV(value), ms); return () => clearTimeout(t); }, [value, ms]);
  return v;
}

/** Ctrl K: one box for commands and for searching every project and design. */
export function CommandPalette() {
  const { paletteOpen, setPaletteOpen, setCalculatorOpen, setShortcutsOpen, toggleSidebar } = useUi();
  const navigate = useNavigate();
  const theme = useThemeToggle();
  const can = useAuth((s) => s.can);
  const [query, setQuery] = useState("");
  const [index, setIndex] = useState(0);
  const listRef = useRef<HTMLDivElement>(null);
  const hits = useSearch(useDebounced(query, 180));

  useEffect(() => { if (paletteOpen) { setQuery(""); setIndex(0); } }, [paletteOpen]);

  const items = useMemo<Item[]>(() => {
    const go = (path: string) => () => navigate(path);
    const commands: Item[] = [
      { id: "c-dash", title: "Go to Dashboard", icon: <BoltOutlined fontSize="small" />, group: "Commands", run: go("/") },
      { id: "c-proj", title: "Go to Projects", icon: <BoltOutlined fontSize="small" />, group: "Commands", run: go("/projects") },
      { id: "c-struct", title: "Go to Structural design", icon: <BoltOutlined fontSize="small" />, group: "Commands", run: go("/structural") },
      ...(can("project:write") ? [{ id: "c-new", title: "New project", icon: <BoltOutlined fontSize="small" />, group: "Commands", run: go("/projects?new=1") }] : []),
      ...(can("user:manage") ? [{ id: "c-users", title: "Users and roles", icon: <BoltOutlined fontSize="small" />, group: "Commands", run: go("/admin/users") }] : []),
      ...(can("project:write") ? [{ id: "c-data", title: "Data and backup", icon: <BoltOutlined fontSize="small" />, group: "Commands", run: go("/admin/data") }] : []),
      { id: "c-calc", title: "Open calculator", icon: <BoltOutlined fontSize="small" />, group: "Commands", run: () => setCalculatorOpen(true) },
      { id: "c-theme", title: theme.dark ? "Switch to light theme" : "Switch to dark theme", icon: <BoltOutlined fontSize="small" />, group: "Commands", run: theme.toggle },
      { id: "c-side", title: "Toggle sidebar", icon: <BoltOutlined fontSize="small" />, group: "Commands", run: toggleSidebar },
      { id: "c-keys", title: "Keyboard shortcuts", icon: <BoltOutlined fontSize="small" />, group: "Commands", run: () => setShortcutsOpen(true) },
    ];
    const q = query.trim().toLowerCase();
    const matched = q ? commands.filter((c) => c.title.toLowerCase().includes(q)) : commands;
    const found: Item[] = (q.length >= 2 ? hits.data ?? [] : []).map((h) => ({
      id: `${h.kind}-${h.id}`,
      title: h.title,
      subtitle: h.subtitle,
      icon: h.kind === "project" ? <FolderOpenOutlined fontSize="small" /> : <ArchitectureOutlined fontSize="small" />,
      group: h.kind === "project" ? "Projects" : "Designs",
      run: go(h.kind === "project" ? `/projects/${h.id}` : `/designs/${h.id}`),
    }));
    return [...found, ...matched];
  }, [query, hits.data, navigate, can, theme.dark, theme.toggle, setCalculatorOpen, setShortcutsOpen, toggleSidebar]);

  useEffect(() => { setIndex((i) => Math.min(i, Math.max(items.length - 1, 0))); }, [items.length]);
  useEffect(() => { listRef.current?.querySelector(`[data-index="${index}"]`)?.scrollIntoView({ block: "nearest" }); }, [index]);

  const run = (item: Item | undefined) => { if (!item) return; setPaletteOpen(false); item.run(); };

  let lastGroup = "";
  return (
    <Dialog open={paletteOpen} onClose={() => setPaletteOpen(false)} fullWidth maxWidth="sm" slotProps={{ paper: { sx: { position: "fixed", top: "12vh", m: 0 } } }} aria-label="Search everywhere">
      <div className="flex items-center gap-2 px-3 h-11 border-b border-[var(--clp-border)]">
        <SearchOutlined fontSize="small" className="text-[var(--clp-ink-3)]" />
        <input
          autoFocus
          value={query}
          onChange={(e) => { setQuery(e.target.value); setIndex(0); }}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") { e.preventDefault(); setIndex((i) => Math.min(i + 1, items.length - 1)); }
            else if (e.key === "ArrowUp") { e.preventDefault(); setIndex((i) => Math.max(i - 1, 0)); }
            else if (e.key === "Enter") { e.preventDefault(); run(items[index]); }
          }}
          placeholder="Search projects and designs, or type a command"
          aria-label="Search"
          className="flex-1 h-full bg-transparent border-0 outline-none text-sm text-[var(--clp-ink)] placeholder:text-[var(--clp-ink-3)]"
        />
        <kbd className="text-[10px] px-1.5 py-0.5 rounded border border-[var(--clp-border)] text-[var(--clp-ink-3)]">Esc</kbd>
      </div>
      <div ref={listRef} className="max-h-[46vh] overflow-y-auto py-1" role="listbox">
        {items.length === 0 && <div className="px-4 py-6 text-center text-[var(--clp-ink-3)]">{hits.isFetching ? "Searching" : "Nothing matches. Try a project name, a job number or a member mark."}</div>}
        {items.map((item, i) => {
          const header = item.group !== lastGroup ? item.group : null;
          lastGroup = item.group;
          return (
            <div key={item.id}>
              {header && <div className="px-4 pt-2 pb-1 text-[10.5px] font-semibold uppercase tracking-wider text-[var(--clp-ink-3)]">{header}</div>}
              <div
                role="option"
                aria-selected={i === index}
                data-index={i}
                onMouseEnter={() => setIndex(i)}
                onClick={() => run(item)}
                className={`flex items-center gap-3 mx-1.5 px-2.5 h-9 rounded cursor-pointer ${i === index ? "bg-[color-mix(in_srgb,var(--clp-accent)_14%,transparent)]" : ""}`}
              >
                <span className="text-[var(--clp-ink-2)] flex">{item.icon}</span>
                <span className="truncate">{item.title}</span>
                {item.subtitle && <span className="ml-auto text-xs text-[var(--clp-ink-3)] truncate">{item.subtitle}</span>}
              </div>
            </div>
          );
        })}
      </div>
    </Dialog>
  );
}
