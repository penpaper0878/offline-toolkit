import { create } from "zustand";
import type { Me, TokenPair } from "../api/types";

const KEY = "clp.refresh";

function stored(): string | null {
  try { return localStorage.getItem(KEY); } catch { return null; }
}
function persist(token: string | null) {
  try { if (token) localStorage.setItem(KEY, token); else localStorage.removeItem(KEY); } catch { /* storage unavailable: session lasts for this tab only */ }
}

interface AuthState {
  accessToken: string | null; // memory only
  refreshToken: string | null; // survives reloads
  me: Me | null;
  setTokens: (t: TokenPair) => void;
  setMe: (me: Me | null) => void;
  clear: () => void;
  can: (permission: string) => boolean;
}

export const useAuth = create<AuthState>((set, get) => ({
  accessToken: null,
  refreshToken: stored(),
  me: null,
  setTokens: (t) => { persist(t.refresh_token); set({ accessToken: t.access_token, refreshToken: t.refresh_token }); },
  setMe: (me) => set({ me }),
  clear: () => { persist(null); set({ accessToken: null, refreshToken: null, me: null }); },
  can: (permission) => get().me?.permissions.includes(permission) ?? false,
}));
