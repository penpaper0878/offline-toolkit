import CloseOutlined from "@mui/icons-material/CloseOutlined";
import { useLocation, useNavigate } from "react-router-dom";
import { useUi } from "../stores/ui";

/** Open documents as tabs, like a drawing or spreadsheet application. Middle-click or the cross closes one. */
export function TabBar() {
  const { tabs, closeTab } = useUi();
  const { pathname } = useLocation();
  const navigate = useNavigate();

  const close = (path: string) => {
    const next = closeTab(path);
    if (path === pathname) navigate(next?.path ?? "/");
  };

  if (tabs.length === 0) return null;
  return (
    <div className="no-print shrink-0 flex items-end h-8 px-1 gap-0.5 overflow-x-auto border-b border-[var(--clp-border)] bg-[var(--clp-panel-2)]" role="tablist" aria-label="Open documents">
      {tabs.map((t) => {
        const active = t.path === pathname;
        return (
          <div
            key={t.path}
            role="tab"
            aria-selected={active}
            tabIndex={0}
            onClick={() => navigate(t.path)}
            onKeyDown={(e) => e.key === "Enter" && navigate(t.path)}
            onAuxClick={(e) => e.button === 1 && close(t.path)}
            className={`group flex items-center gap-1.5 h-7 pl-3 pr-1 max-w-[220px] text-xs rounded-t border border-b-0 cursor-pointer select-none ${active ? "bg-[var(--clp-bg)] border-[var(--clp-border)] font-semibold" : "border-transparent text-[var(--clp-ink-2)] hover:bg-[var(--clp-panel)]"}`}
          >
            <span className="truncate">{t.title}</span>
            <button
              type="button"
              aria-label={`Close ${t.title}`}
              onClick={(e) => { e.stopPropagation(); close(t.path); }}
              className={`flex items-center justify-center h-4 w-4 rounded border-0 bg-transparent cursor-pointer text-[var(--clp-ink-3)] hover:bg-[var(--clp-border)] hover:text-[var(--clp-ink)] ${active ? "" : "opacity-0 group-hover:opacity-100"}`}
            >
              <CloseOutlined sx={{ fontSize: 12 }} />
            </button>
          </div>
        );
      })}
    </div>
  );
}
