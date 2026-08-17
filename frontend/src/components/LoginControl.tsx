import { useState } from 'react';
import { useAuth } from '../auth/AuthContext';

/**
 * Header sign-in widget. Signed out: a "Sign in" button that reveals a compact credential form.
 * Signed in: the username, a role pill, and "Sign out". Writes stay disabled in the UI until a
 * trader/admin is signed in — the backend enforces the same rule regardless.
 */
export function LoginControl() {
  const { session, login, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (session) {
    return (
      <div className="auth-box">
        <span className="auth-user">{session.username}</span>
        {session.roles.map((r) => (
          <span key={r} className="auth-role">{r}</span>
        ))}
        <button className="auth-btn" onClick={logout}>Sign out</button>
      </div>
    );
  }

  if (!open) {
    return (
      <div className="auth-box">
        <span className="auth-anon">Read-only</span>
        <button className="auth-btn" onClick={() => setOpen(true)}>Sign in</button>
      </div>
    );
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(username, password);
      setOpen(false);
      setUsername('');
      setPassword('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sign-in failed');
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="auth-form" onSubmit={submit}>
      <input
        aria-label="Username"
        placeholder="username"
        value={username}
        onChange={(e) => setUsername(e.target.value)}
        autoFocus
      />
      <input
        aria-label="Password"
        type="password"
        placeholder="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
      />
      <button className="auth-btn primary" type="submit" disabled={busy || !username || !password}>
        {busy ? '…' : 'Go'}
      </button>
      <button className="auth-btn" type="button" onClick={() => { setOpen(false); setError(null); }}>
        Cancel
      </button>
      {error && <span className="auth-err">{error}</span>}
      <span className="auth-hint">demo: trader / trader</span>
    </form>
  );
}
