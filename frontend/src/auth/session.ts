// Client-side auth session: a short-lived access token (sent as the bearer) plus a long-lived refresh
// token used to mint new access tokens without re-login. Persisted so a reload stays signed in.
// Deliberately framework-agnostic (no React) so the API client can read/rotate tokens without importing
// the component tree — that keeps client.ts <- session.ts a one-way dependency.

const STORAGE_KEY = 'bonddesk.auth';

export type Role = 'VIEWER' | 'TRADER' | 'ADMIN' | 'SERVICE';

/** POST /api/v1/auth/login response. */
export interface LoginResponse {
  accessToken: string;
  refreshToken: string;
  tokenType: string;
  username: string;
  roles: Role[];
  expiresInSeconds: number;
}

/** POST /api/v1/auth/refresh response (a rotated pair; no identity fields). */
export interface RefreshResponse {
  accessToken: string;
  refreshToken: string;
  tokenType: string;
  expiresInSeconds: number;
}

/** The persisted session. */
export interface Session {
  accessToken: string;
  refreshToken: string;
  username: string;
  roles: Role[];
  expiresAt: number; // epoch ms — when the access token lapses
}

let current: Session | null = null;

/** Roles that may perform writes (mirrors the backend @PreAuthorize on the write endpoints). */
const WRITE_ROLES: Role[] = ['TRADER', 'ADMIN', 'SERVICE'];

export function canWrite(session: Session | null): boolean {
  return session != null && session.roles.some((r) => WRITE_ROLES.includes(r));
}

/** The current access token for the API client, or null when signed out. */
export function getToken(): string | null {
  return load()?.accessToken ?? null;
}

/** The refresh token, if any — used by the client to rotate an expired access token. */
export function getRefreshToken(): string | null {
  return load()?.refreshToken ?? null;
}

/** The active session, hydrating from storage on first call. */
export function load(): Session | null {
  if (current) return current;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    current = JSON.parse(raw) as Session;
    return current;
  } catch {
    return null;
  }
}

/** Persist a fresh login. `now` is injectable so tests aren't wall-clock dependent. */
export function save(res: LoginResponse, now: number = Date.now()): Session {
  current = {
    accessToken: res.accessToken,
    refreshToken: res.refreshToken,
    username: res.username,
    roles: res.roles,
    expiresAt: now + res.expiresInSeconds * 1000,
  };
  persist();
  return current;
}

/** Apply a refresh: swap in the new access + rotated refresh token, keeping the same identity. */
export function applyRefresh(res: RefreshResponse, now: number = Date.now()): Session | null {
  if (!current && !load()) return null;
  current = {
    ...(current as Session),
    accessToken: res.accessToken,
    refreshToken: res.refreshToken,
    expiresAt: now + res.expiresInSeconds * 1000,
  };
  persist();
  return current;
}

export function clear(): null {
  current = null;
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* ignore */
  }
  return null;
}

function persist(): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(current));
  } catch {
    /* storage disabled (private mode) — session still works in-memory for this tab */
  }
}
