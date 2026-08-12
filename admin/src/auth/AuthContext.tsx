import { createContext, type PropsWithChildren, useContext, useEffect, useMemo, useState } from 'react';
import { login, logout, logoutAll, register, validateSession } from '../lib/authApi';
import {
  clearAuthSession,
  getAuthSession,
  getRefreshToken,
  migrateLegacyAdminRefreshToken,
  type AuthUser,
} from '../lib/authSession';
import { apiJson } from '../lib/apiClient';

type AuthState = 'booting' | 'signed-out' | 'signed-in';
type AuthContextValue = {
  state: AuthState;
  user: AuthUser | null;
  signIn(email: string, password: string): Promise<void>;
  signUp(fullName: string, email: string, password: string): Promise<void>;
  signOut(): Promise<void>;
  signOutAll(): Promise<void>;
  refreshUser(): Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: PropsWithChildren) {
  const [state, setState] = useState<AuthState>('booting');
  const [user, setUser] = useState<AuthUser | null>(null);

  useEffect(() => {
    let active = true;
    migrateLegacyAdminRefreshToken();
    async function bootstrap() {
      if (!getRefreshToken()) {
        if (active) setState('signed-out');
        return;
      }
      try {
        // A harmless protected request invokes the shared, concurrency-safe refresh path.
        const current = await apiJson<AuthUser>('/auth/me');
        if (active) { setUser(current); setState('signed-in'); }
      } catch {
        clearAuthSession();
        if (active) { setUser(null); setState('signed-out'); }
      }
    }
    const handleChange = () => {
      const session = getAuthSession();
      if (active && session) { setUser(session.user); setState('signed-in'); }
    };
    const handleRequired = () => {
      if (active) { setUser(null); setState('signed-out'); }
    };
    window.addEventListener('admitly-auth-changed', handleChange);
    window.addEventListener('admitly-auth-required', handleRequired);
    void bootstrap();
    return () => {
      active = false;
      window.removeEventListener('admitly-auth-changed', handleChange);
      window.removeEventListener('admitly-auth-required', handleRequired);
    };
  }, []);

  const value = useMemo<AuthContextValue>(() => ({
    state,
    user,
    signIn: async (email, password) => { const session = await login(email, password); setUser(session.user); setState('signed-in'); },
    signUp: async (name, email, password) => { const session = await register(name, email, password); setUser(session.user); setState('signed-in'); },
    signOut: async () => {
      try { await logout(); } finally { setUser(null); setState('signed-out'); }
    },
    signOutAll: async () => {
      try { await logoutAll(); } finally { setUser(null); setState('signed-out'); }
    },
    refreshUser: async () => { const session = await validateSession(); setUser(session.user); },
  }), [state, user]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error('useAuth must be used within AuthProvider.');
  return value;
}
