import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';
import { api, HttpError } from '../api/client';
import { canWrite, clear, getRefreshToken, load, save, type Session } from './session';

interface AuthValue {
  session: Session | null;
  /** Signed in with a role that may submit/stage/route/cancel (mirrors the backend gate). */
  canWrite: boolean;
  /** Resolves on success; throws an Error with a user-facing message on failure. */
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  // Hydrate once from persisted storage (dropped automatically if the token has expired).
  const [session, setSession] = useState<Session | null>(() => load());

  const login = useCallback(async (username: string, password: string) => {
    try {
      const res = await api.login(username, password);
      setSession(save(res));
    } catch (err) {
      // Surface the backend's indistinguishable 401 message; fall back for network errors.
      const msg =
        err instanceof HttpError
          ? err.body?.message ?? 'Invalid username or password'
          : 'Could not reach the server';
      throw new Error(msg);
    }
  }, []);

  const logout = useCallback(() => {
    // Best-effort server-side revocation (kills the refresh family + denylists the access token),
    // then clear locally regardless of the network result.
    const refreshToken = getRefreshToken();
    if (refreshToken) {
      api.logout(refreshToken).catch(() => {});
    }
    clear();
    setSession(null);
  }, []);

  const value = useMemo<AuthValue>(
    () => ({ session, canWrite: canWrite(session), login, logout }),
    [session, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider');
  return ctx;
}
