import ArchitectureOutlined from "@mui/icons-material/ArchitectureOutlined";
import CalculateOutlined from "@mui/icons-material/CalculateOutlined";
import CreateNewFolderOutlined from "@mui/icons-material/CreateNewFolderOutlined";
import DarkModeOutlined from "@mui/icons-material/DarkModeOutlined";
import FolderOpenOutlined from "@mui/icons-material/FolderOpenOutlined";
import KeyboardOutlined from "@mui/icons-material/KeyboardOutlined";
import LightModeOutlined from "@mui/icons-material/LightModeOutlined";
import LogoutOutlined from "@mui/icons-material/LogoutOutlined";
import MenuOpenOutlined from "@mui/icons-material/MenuOpenOutlined";
import SearchOutlined from "@mui/icons-material/SearchOutlined";
import SpaceDashboardOutlined from "@mui/icons-material/SpaceDashboardOutlined";
import ButtonBase from "@mui/material/ButtonBase";
import IconButton from "@mui/material/IconButton";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import Tooltip from "@mui/material/Tooltip";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../stores/auth";
import { type RibbonGroup, useUi } from "../stores/ui";
import { useThemeToggle } from "./hooks";

function Group({ group }: { group: RibbonGroup }) {
  return (
    <div className="flex flex-col h-full px-2 border-r border-[var(--clp-border)] last:border-r-0">
      <div className="flex-1 flex items-stretch gap-0.5 pt-1">
        {group.actions.map((a) => (
          <Tooltip key={a.id} title={a.hint ? `${a.hint}${a.shortcut ? ` (${a.shortcut})` : ""}` : a.shortcut ? `${a.label} (${a.shortcut})` : ""}>
            <span className="flex">
              <ButtonBase
                onClick={a.onClick}
                disabled={a.disabled}
                data-ribbon={a.id}
                className="!flex !flex-col !justify-start !gap-0.5 !px-2 !pt-1 !min-w-[58px] !rounded"
                sx={{ color: a.primary ? "primary.main" : "text.primary", "&:hover": { bgcolor: "action.hover" }, "&.Mui-disabled": { opacity: 0.38 } }}
              >
                <span className="[&>svg]:!text-[22px]">{a.icon}</span>
                <span className="text-[11px] leading-tight text-center max-w-[76px]">{a.label}</span>
              </ButtonBase>
            </span>
          </Tooltip>
        ))}
      </div>
      <div className="text-center text-[10px] text-[var(--clp-ink-3)] pb-0.5 select-none">{group.title}</div>
    </div>
  );
}

export function Ribbon() {
  const navigate = useNavigate();
  const { me, refreshToken, clear } = useAuth();
  const ui = useUi();
  const theme = useThemeToggle();
  const [active, setActive] = useState<string>("Home");
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);

  // A page that registers a contextual tab brings it to the front; leaving the page falls back to Home.
  useEffect(() => { setActive(ui.ribbonTab ?? "Home"); }, [ui.ribbonTab]);

  const home: RibbonGroup[] = [
    { title: "Go to", actions: [
      { id: "dashboard", label: "Dashboard", icon: <SpaceDashboardOutlined />, onClick: () => navigate("/"), shortcut: "Alt 1" },
      { id: "projects", label: "Projects", icon: <FolderOpenOutlined />, onClick: () => navigate("/projects"), shortcut: "Alt 2" },
      { id: "structural", label: "Structural", icon: <ArchitectureOutlined />, onClick: () => navigate("/structural"), shortcut: "Alt 3" },
    ] },
    { title: "Create", actions: [
      { id: "new-project", label: "New project", icon: <CreateNewFolderOutlined />, onClick: () => navigate("/projects?new=1"), disabled: !me?.permissions.includes("project:write"), primary: true },
    ] },
    { title: "Tools", actions: [
      { id: "search", label: "Search", icon: <SearchOutlined />, onClick: () => ui.setPaletteOpen(true), shortcut: "Ctrl K" },
      { id: "calculator", label: "Calculator", icon: <CalculateOutlined />, onClick: () => ui.setCalculatorOpen(!ui.calculatorOpen), shortcut: "Alt C" },
      { id: "shortcuts", label: "Shortcuts", icon: <KeyboardOutlined />, onClick: () => ui.setShortcutsOpen(true), shortcut: "?" },
    ] },
    { title: "View", actions: [
      { id: "theme", label: theme.dark ? "Light theme" : "Dark theme", icon: theme.dark ? <LightModeOutlined /> : <DarkModeOutlined />, onClick: theme.toggle, shortcut: "Alt T" },
      { id: "sidebar", label: "Sidebar", icon: <MenuOpenOutlined />, onClick: ui.toggleSidebar, shortcut: "Alt B" },
    ] },
  ];
  const tabs = ["Home", ...(ui.ribbonTab ? [ui.ribbonTab] : [])];
  const groups = active === "Home" || !ui.ribbonTab ? home : ui.ribbonGroups;

  async function signOut() {
    if (refreshToken) await api("/auth/logout", { method: "POST", body: { refresh_token: refreshToken }, auth: false }).catch(() => undefined);
    clear();
    navigate("/login");
  }

  return (
    <header className="no-print shrink-0 border-b border-[var(--clp-border)] bg-[var(--clp-panel)]">
      <div className="flex items-center h-9 pl-3 pr-2 gap-3 bg-[#0f172a] text-slate-100">
        <img src="/icon.svg" alt="" className="h-5 w-5" />
        <span className="font-semibold tracking-tight text-[13.5px]">CivilLabPro OS</span>
        <span className="text-slate-400 text-xs truncate">{me?.organization.name}</span>
        <button
          type="button"
          onClick={() => ui.setPaletteOpen(true)}
          className="ml-auto flex items-center gap-2 h-6 w-[280px] max-w-[36vw] px-2 rounded bg-white/10 hover:bg-white/15 text-slate-300 text-xs cursor-pointer border-0"
        >
          <SearchOutlined sx={{ fontSize: 15 }} />
          <span className="flex-1 text-left truncate">Search or run a command</span>
          <kbd className="font-sans text-[10px] px-1 rounded bg-white/10 whitespace-nowrap">Ctrl K</kbd>
        </button>
        <Tooltip title={me ? `${me.full_name} (${me.role})` : ""}>
          <IconButton onClick={(e) => setAnchor(e.currentTarget)} aria-label="Account" sx={{ color: "inherit", fontSize: 12, fontWeight: 700, width: 26, height: 26, bgcolor: "rgba(255,255,255,0.14)" }}>
            {me?.full_name.split(/\s+/).map((p) => p[0]).slice(0, 2).join("").toUpperCase() ?? "?"}
          </IconButton>
        </Tooltip>
        <Menu anchorEl={anchor} open={!!anchor} onClose={() => setAnchor(null)}>
          <div className="px-4 py-2 text-xs">
            <div className="font-semibold text-sm">{me?.full_name}</div>
            <div className="text-[var(--clp-ink-2)]">{me?.email}</div>
            <div className="text-[var(--clp-ink-2)] capitalize">{me?.role} at {me?.organization.name}</div>
          </div>
          <MenuItem onClick={signOut}><LogoutOutlined fontSize="small" className="mr-2" />Sign out</MenuItem>
        </Menu>
      </div>
      <div className="flex items-end h-7 px-2 gap-0.5 border-b border-[var(--clp-border)] bg-[var(--clp-panel-2)]" role="tablist" aria-label="Ribbon">
        {tabs.map((t) => (
          <button
            key={t}
            type="button"
            role="tab"
            aria-selected={active === t}
            onClick={() => setActive(t)}
            className={`h-6 px-3 text-xs rounded-t border border-b-0 cursor-pointer ${active === t ? "bg-[var(--clp-panel)] border-[var(--clp-border)] font-semibold text-[var(--clp-ink)] -mb-px h-[25px]" : "bg-transparent border-transparent text-[var(--clp-ink-2)] hover:text-[var(--clp-ink)]"}`}
          >
            {t}
          </button>
        ))}
      </div>
      <div className="flex h-[66px] px-1 overflow-x-auto" role="toolbar" aria-label={`${active} commands`}>
        {groups.map((g) => <Group key={g.title} group={g} />)}
      </div>
    </header>
  );
}
