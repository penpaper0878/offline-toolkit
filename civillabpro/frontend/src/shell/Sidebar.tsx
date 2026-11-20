import AddRoadOutlined from "@mui/icons-material/AddRoadOutlined";
import ArchitectureOutlined from "@mui/icons-material/ArchitectureOutlined";
import AutoAwesomeOutlined from "@mui/icons-material/AutoAwesomeOutlined";
import EventNoteOutlined from "@mui/icons-material/EventNoteOutlined";
import FolderOpenOutlined from "@mui/icons-material/FolderOpenOutlined";
import ManageAccountsOutlined from "@mui/icons-material/ManageAccountsOutlined";
import SaveAltOutlined from "@mui/icons-material/SaveAltOutlined";
import MapOutlined from "@mui/icons-material/MapOutlined";
import MenuBookOutlined from "@mui/icons-material/MenuBookOutlined";
import PlumbingOutlined from "@mui/icons-material/PlumbingOutlined";
import ReceiptLongOutlined from "@mui/icons-material/ReceiptLongOutlined";
import ScienceOutlined from "@mui/icons-material/ScienceOutlined";
import SpaceDashboardOutlined from "@mui/icons-material/SpaceDashboardOutlined";
import WaterDropOutlined from "@mui/icons-material/WaterDropOutlined";
import Tooltip from "@mui/material/Tooltip";
import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { MODULES } from "../app/modules";
import { useAuth } from "../stores/auth";
import { useUi } from "../stores/ui";

const ICONS: Record<string, ReactNode> = {
  dashboard: <SpaceDashboardOutlined fontSize="small" />,
  projects: <FolderOpenOutlined fontSize="small" />,
  structural: <ArchitectureOutlined fontSize="small" />,
  water: <WaterDropOutlined fontSize="small" />,
  sewerage: <PlumbingOutlined fontSize="small" />,
  highway: <AddRoadOutlined fontSize="small" />,
  estimation: <ReceiptLongOutlined fontSize="small" />,
  lims: <ScienceOutlined fontSize="small" />,
  gis: <MapOutlined fontSize="small" />,
  pm: <EventNoteOutlined fontSize="small" />,
  ai: <AutoAwesomeOutlined fontSize="small" />,
  standards: <MenuBookOutlined fontSize="small" />,
};

const row = "flex items-center gap-2.5 h-8 px-3 mx-1.5 rounded text-[13px] whitespace-nowrap overflow-hidden";

export function Sidebar() {
  const collapsed = useUi((s) => s.sidebarCollapsed);
  const canManageUsers = useAuth((s) => s.can("user:manage"));
  const canData = useAuth((s) => s.can("project:write"));
  const available = MODULES.filter((m) => m.status === "available");
  const planned = MODULES.filter((m) => m.status === "planned").sort((a, b) => a.phase - b.phase);

  const link = (path: string, icon: ReactNode, title: string, tip: string) => (
    <Tooltip key={path} title={collapsed ? title : tip} placement="right">
      <span className="block">
      <NavLink
        to={path}
        end={path === "/"}
        className={({ isActive }) =>
          `${row} no-underline ${isActive ? "bg-[color-mix(in_srgb,var(--clp-accent)_14%,transparent)] text-[var(--clp-accent)] font-semibold" : "text-[var(--clp-ink)] hover:bg-[var(--clp-panel-2)]"}`
        }
      >
        {icon}
        {!collapsed && <span>{title}</span>}
      </NavLink>
      </span>
    </Tooltip>
  );

  return (
    <nav aria-label="Modules" className={`no-print shrink-0 flex flex-col border-r border-[var(--clp-border)] bg-[var(--clp-panel)] py-2 overflow-y-auto transition-[width] duration-150 ${collapsed ? "w-[52px]" : "w-[216px]"}`}>
      {!collapsed && <div className="px-4 pb-1 text-[10.5px] font-semibold uppercase tracking-wider text-[var(--clp-ink-3)]">Workspace</div>}
      <div className="flex flex-col gap-0.5">{available.map((m) => link(m.path!, ICONS[m.id], m.title, m.summary))}</div>

      <div className="my-2 mx-3 border-t border-[var(--clp-border)]" />
      {!collapsed && <div className="px-4 pb-1 text-[10.5px] font-semibold uppercase tracking-wider text-[var(--clp-ink-3)]">Roadmap</div>}
      <div className="flex flex-col gap-0.5">
        {planned.map((m) => (
          <Tooltip key={m.id} title={`${m.title}: ${m.summary}. Planned for phase ${m.phase}.`} placement="right">
            <div className={`${row} text-[var(--clp-ink-3)] cursor-default`} aria-disabled="true">
              {ICONS[m.id]}
              {!collapsed && (
                <>
                  <span className="flex-1 truncate">{m.title}</span>
                  <span className="text-[10px] px-1.5 py-px rounded border border-[var(--clp-border)]">P{m.phase}</span>
                </>
              )}
            </div>
          </Tooltip>
        ))}
      </div>

      {(canManageUsers || canData) && (
        <div className="mt-auto pt-2">
          <div className="mb-2 mx-3 border-t border-[var(--clp-border)]" />
          {canData && link("/admin/data", <SaveAltOutlined fontSize="small" />, "Data and backup", "Back up the database; move projects between installations")}
          {canManageUsers && link("/admin/users", <ManageAccountsOutlined fontSize="small" />, "Users and roles", "People, roles and the audit trail")}
        </div>
      )}
    </nav>
  );
}
