// Client-side auth session: the signed JWT plus the identity it encodes, persisted so a page reload
// stays logged in. Deliberately framework-agnostic (no React) so the API client can read the token
// without importing the component tree — that keeps client.ts <- session.ts a one-way dependency.

const STORAGE_KEY = 'bonddesk.auth';

export type Role = 'VIEWER' | 'TRADER' | 'ADMIN' | 'SERVICE';

/** The login response returned by POST /api/v1/auth/login. */
export interface LoginResponse {
  token: string;
  tokenType: string;
  username: string;
  roles: Role[];
  expiresInMinutes: number;
}

/** The persisted session — the token plus who it belongs to and when it lapses. */
export interface Session {
  token: string;
  username: string;
  roles: Role[];
  expiresAt: number; // epoch ms
}

let current: Session | null = null;

/** Roles that may perform writes (mirrors the backend @PreAuthorize on OrderController). */
const WRITE_ROLES: Role[] = ['TRADER', 'ADMIN', 'SERVICE'];

export function canWrite(session: Session | null): boolean {
  return session != null && session.roles.some((r) => WRITE_ROLES.includes(r));
}

/** The raw bearer token for the API client, or null when signed out / expired. */
export function getToken(): string | null {
  const s = load();
  return s ? s.token : null;
}

/** The active session, hydrating from storage on first call and dropping it once expired. */
export function load(): Session | null {
  if (current) {
    return isExpired(current) ? clear() : current;
  }
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Session;
    if (isExpired(parsed)) return clear();
    current = parsed;
    return current;
  } catch {
    return null;
  }
}

/** Persist a fresh login. `now` is injectable so tests aren't wall-clock dependent. */
export function save(res: LoginResponse, now: number = Date.now()): Session {
  const session: Session = {
    token: res.token,
    username: res.username,
    roles: res.roles,
    expiresAt: now + res.expiresInMinutes * 60_000,
  };
  current = session;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  } catch {
    /* storage disabled (private mode) — session still works in-memory for this tab */
  }
  return session;
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

function isExpired(s: Session, now: number = Date.now()): boolean {
  return s.expiresAt <= now;
}
