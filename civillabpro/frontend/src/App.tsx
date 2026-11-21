import CircularProgress from "@mui/material/CircularProgress";
import { lazy, Suspense, useEffect, useState } from "react";
import { Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";
import { refreshSession } from "./api/client";
import { useMe } from "./api/hooks";
import { LoginPage } from "./pages/LoginPage";
import { ProjectDetailPage } from "./pages/ProjectDetailPage";
import { ProjectsPage } from "./pages/ProjectsPage";
import { StructuralPage } from "./pages/StructuralPage";
import { AppShell } from "./shell/AppShell";
import { useAuth } from "./stores/auth";

// The heavier screens (charts, the docking workspace) load on demand so sign-in stays light.
const DashboardPage = lazy(() => import("./pages/DashboardPage").then((m) => ({ default: m.DashboardPage })));
const DesignWorkspacePage = lazy(() => import("./pages/DesignWorkspacePage").then((m) => ({ default: m.DesignWorkspacePage })));
const UsersPage = lazy(() => import("./pages/UsersPage").then((m) => ({ default: m.UsersPage })));
const DataPage = lazy(() => import("./pages/DataPage").then((m) => ({ default: m.DataPage })));
const EstimationPage = lazy(() => import("./pages/EstimationPage").then((m) => ({ default: m.EstimationPage })));
const EstimatePage = lazy(() => import("./pages/EstimatePage").then((m) => ({ default: m.EstimatePage })));

const Splash = ({ label }: { label: string }) => (
  <div className="h-full flex flex-col items-center justify-center gap-3 text-[var(--clp-ink-2)]"><CircularProgress size={22} /><span>{label}</span></div>
);

/** Restores the session from the stored refresh token, loads the profile, then renders the protected routes. */
function RequireAuth() {
  const { accessToken, refreshToken, me, setMe } = useAuth();
  const location = useLocation();
  const [restoring, setRestoring] = useState(!accessToken && !!refreshToken);
  useEffect(() => {
    if (!accessToken && refreshToken) void refreshSession().finally(() => setRestoring(false));
  }, [accessToken, refreshToken]);
  const profile = useMe(!!accessToken);
  useEffect(() => { if (profile.data) setMe(profile.data); }, [profile.data, setMe]);

  if (restoring) return <Splash label="Restoring your session" />;
  if (!accessToken) return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  if (!me) return profile.isError ? <div className="p-8 text-[var(--clp-bad)]" role="alert">Your profile could not be loaded. {(profile.error as Error).message}</div> : <Splash label="Loading your workspace" />;
  return <Outlet />;
}

function RequirePermission({ permission }: { permission: string }) {
  const can = useAuth((s) => s.can);
  return can(permission) ? <Outlet /> : <div className="p-8" role="alert">Your role does not include this area.</div>;
}

export function App() {
  return (
    <Suspense fallback={<Splash label="Loading" />}>
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<RequireAuth />}>
        <Route element={<AppShell />}>
          <Route index element={<DashboardPage />} />
          <Route path="projects" element={<ProjectsPage />} />
          <Route path="projects/:projectId" element={<ProjectDetailPage />} />
          <Route path="projects/:projectId/designs/new/:elementType" element={<DesignWorkspacePage />} />
          <Route path="designs/:designId" element={<DesignWorkspacePage />} />
          <Route path="structural" element={<StructuralPage />} />
          <Route path="estimation" element={<EstimationPage />} />
          <Route path="estimates/:estimateId" element={<EstimatePage />} />
          <Route element={<RequirePermission permission="user:manage" />}>
            <Route path="admin/users" element={<UsersPage />} />
          </Route>
          <Route element={<RequirePermission permission="project:write" />}>
            <Route path="admin/data" element={<DataPage />} />
          </Route>
          <Route path="*" element={<div className="p-8">This page does not exist. Use the sidebar or press Ctrl K.</div>} />
        </Route>
      </Route>
    </Routes>
    </Suspense>
  );
}
