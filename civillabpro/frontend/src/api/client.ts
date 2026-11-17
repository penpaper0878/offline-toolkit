import { useAuth } from "../stores/auth";
import type { TokenPair } from "./types";

const BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? "";
export const API = `${BASE}/api/v1`;

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public details: { field: string; message: string }[] = []) {
    super(message);
  }
}

async function toError(res: Response): Promise<ApiError> {
  try {
    const body = await res.json();
    if (body?.error) return new ApiError(res.status, body.error.code, body.error.message, body.error.details ?? []);
  } catch { /* not JSON */ }
  return new ApiError(res.status, "http_error", res.status >= 500 ? "The server could not complete the request." : `Request failed (${res.status}).`);
}

let refreshing: Promise<boolean> | null = null;

/** Exchange the refresh token for a new pair. Concurrent callers share one request. */
export function refreshSession(): Promise<boolean> {
  refreshing ??= (async () => {
    const { refreshToken, setTokens, clear } = useAuth.getState();
    if (!refreshToken) return false;
    try {
      const res = await fetch(`${API}/auth/refresh`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ refresh_token: refreshToken }) });
      if (!res.ok) { clear(); return false; }
      setTokens((await res.json()) as TokenPair);
      return true;
    } catch {
      return false; // offline: keep the session so it resumes when the network returns
    }
  })().finally(() => { refreshing = null; });
  return refreshing;
}

interface Options { method?: string; body?: unknown; form?: Record<string, string>; signal?: AbortSignal; auth?: boolean }

async function send(path: string, o: Options): Promise<Response> {
  const headers: Record<string, string> = {};
  const token = useAuth.getState().accessToken;
  if (token && o.auth !== false) headers.Authorization = `Bearer ${token}`;
  let body: BodyInit | undefined;
  if (o.form) { body = new URLSearchParams(o.form); }
  else if (o.body !== undefined) { headers["Content-Type"] = "application/json"; body = JSON.stringify(o.body); }
  return fetch(`${API}${path}`, { method: o.method ?? "GET", headers, body, signal: o.signal });
}

async function request(path: string, o: Options = {}): Promise<Response> {
  let res: Response;
  try {
    res = await send(path, o);
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new ApiError(0, "network", "Cannot reach the server. Check the connection and try again.");
  }
  if (res.status === 401 && o.auth !== false && useAuth.getState().refreshToken && (await refreshSession())) res = await send(path, o);
  if (!res.ok) throw await toError(res);
  return res;
}

export async function api<T>(path: string, o: Options = {}): Promise<T> {
  const res = await request(path, o);
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

/** Fetch a protected file and hand it to the browser as a download. */
export async function download(path: string, fallbackName: string): Promise<void> {
  const res = await request(path);
  const name = /filename="([^"]+)"/.exec(res.headers.get("Content-Disposition") ?? "")?.[1] ?? fallbackName;
  const url = URL.createObjectURL(await res.blob());
  const a = Object.assign(document.createElement("a"), { href: url, download: name });
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}
