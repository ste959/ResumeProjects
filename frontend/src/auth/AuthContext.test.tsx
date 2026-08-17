import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AuthProvider, useAuth } from './AuthContext';
import { api } from '../api/client';

// Mock only the login call; keep the real HttpError for the failure path.
vi.mock('../api/client', async () => {
  const actual = await vi.importActual<typeof import('../api/client')>('../api/client');
  return { ...actual, api: { login: vi.fn() } };
});

function Harness() {
  const { session, canWrite, login, logout } = useAuth();
  return (
    <div>
      <span data-testid="who">{session ? session.username : 'anon'}</span>
      <span data-testid="canwrite">{String(canWrite)}</span>
      <button onClick={() => login('trader', 'trader').catch(() => {})}>login</button>
      <button onClick={logout}>logout</button>
    </div>
  );
}

describe('AuthContext', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });
  afterEach(() => localStorage.clear());

  it('logs in, exposes a write-capable session, and persists it', async () => {
    const user = userEvent.setup();
    vi.mocked(api.login).mockResolvedValue({
      token: 'jwt.abc.def',
      tokenType: 'Bearer',
      username: 'trader',
      roles: ['TRADER'],
      expiresInMinutes: 60,
    });

    render(<AuthProvider><Harness /></AuthProvider>);

    expect(screen.getByTestId('who').textContent).toBe('anon');
    expect(screen.getByTestId('canwrite').textContent).toBe('false');

    await user.click(screen.getByText('login'));

    expect(await screen.findByText('trader')).toBeInTheDocument();
    expect(screen.getByTestId('canwrite').textContent).toBe('true');
    // The signed token is persisted so a reload stays authenticated.
    expect(localStorage.getItem('bonddesk.auth')).toContain('jwt.abc.def');

    await user.click(screen.getByText('logout'));
    expect(screen.getByTestId('who').textContent).toBe('anon');
    expect(localStorage.getItem('bonddesk.auth')).toBeNull();
  });

  it('a viewer is signed in but cannot write', async () => {
    const user = userEvent.setup();
    vi.mocked(api.login).mockResolvedValue({
      token: 't', tokenType: 'Bearer', username: 'viewer', roles: ['VIEWER'], expiresInMinutes: 60,
    });

    render(<AuthProvider><Harness /></AuthProvider>);
    await user.click(screen.getByText('login'));

    expect(await screen.findByText('viewer')).toBeInTheDocument();
    expect(screen.getByTestId('canwrite').textContent).toBe('false');
  });
});
