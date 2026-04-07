import { createContext, PropsWithChildren, useContext, useEffect, useMemo, useState } from 'react';

import {
  AuthTokens,
  AuthUser,
  getCurrentUser,
  login,
  logout,
  refresh,
  register,
  requestPasswordReset,
  resetPassword,
} from '../api/auth';
import { ApiError, setApiAuthToken } from '../api/client';
import { clearStoredSession, getStoredSession, setStoredSession } from '../storage/sessionStorage';

type SessionState = 'booting' | 'signedOut' | 'signedIn';

type SessionContextValue = {
  state: SessionState;
  user: AuthUser | null;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (fullName: string, email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  requestPasswordReset: (email: string) => Promise<void>;
  resetPassword: (token: string, newPassword: string) => Promise<void>;
};

const SessionContext = createContext<SessionContextValue | undefined>(undefined);

function getErrorMessage(error: unknown) {
  if (error instanceof ApiError) {
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return 'Something went wrong. Please try again.';
}

function normalizeEmail(email: string) {
  return email.trim().toLowerCase();
}

function toStoredSession(tokens: AuthTokens) {
  return {
    accessToken: tokens.access_token,
    refreshToken: tokens.refresh_token,
  };
}

export function SessionProvider({ children }: PropsWithChildren) {
  const [state, setState] = useState<SessionState>('booting');
  const [user, setUser] = useState<AuthUser | null>(null);

  useEffect(() => {
    async function bootstrap() {
      const storedSession = await getStoredSession();

      if (!storedSession?.accessToken) {
        setState('signedOut');
        return;
      }

      try {
        setApiAuthToken(storedSession.accessToken);
        const currentUser = await getCurrentUser();
        setUser(currentUser);
        setState('signedIn');
      } catch (error) {
        if (storedSession.refreshToken) {
          try {
            const refreshed = await refresh(storedSession.refreshToken);
            await setStoredSession(toStoredSession(refreshed.tokens));
            setApiAuthToken(refreshed.tokens.access_token);
            setUser(refreshed.user);
            setState('signedIn');
            return;
          } catch {
            // Continue to sign-out fallback.
          }
        }

        await clearStoredSession();
        setApiAuthToken(null);
        setUser(null);
        setState('signedOut');
      }
    }

    bootstrap();
  }, []);

  const value = useMemo(
    () => ({
      state,
      user,
      signIn: async (email: string, password: string) => {
        const result = await login(normalizeEmail(email), password);
        await setStoredSession(toStoredSession(result.tokens));
        setApiAuthToken(result.tokens.access_token);
        setUser(result.user);
        setState('signedIn');
      },
      signUp: async (fullName: string, email: string, password: string) => {
        const result = await register(fullName.trim(), normalizeEmail(email), password);
        await setStoredSession(toStoredSession(result.tokens));
        setApiAuthToken(result.tokens.access_token);
        setUser(result.user);
        setState('signedIn');
      },
      signOut: async () => {
        try {
          await logout();
        } catch {
          // logout should still complete client-side even if network call fails
        }
        await clearStoredSession();
        setApiAuthToken(null);
        setUser(null);
        setState('signedOut');
      },
      requestPasswordReset: async (email: string) => {
        const normalizedEmail = normalizeEmail(email);
        await requestPasswordReset(normalizedEmail);
      },
      resetPassword: async (token: string, newPassword: string) => {
        await resetPassword(token.trim(), newPassword);
      },
    }),
    [state, user],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession() {
  const ctx = useContext(SessionContext);
  if (!ctx) {
    throw new Error('useSession must be used inside SessionProvider');
  }
  return ctx;
}

export { getErrorMessage };
