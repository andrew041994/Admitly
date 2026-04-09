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
    let completed = false;
    const BOOT_TIMEOUT_MS = 5000;

    const completeBootAsSignedOut = async (reason: string, options?: { clearSession?: boolean }) => {
      if (completed) {
        return;
      }
      completed = true;

      if (__DEV__) {
        console.log(`[session] init fallback -> signedOut (${reason})`);
      }

      if (options?.clearSession ?? true) {
        await clearStoredSession();
      }
      setApiAuthToken(null);
      setUser(null);
      setState('signedOut');
    };

    const completeBootAsSignedIn = (currentUser: AuthUser, reason: string) => {
      if (completed) {
        return;
      }
      completed = true;

      if (__DEV__) {
        console.log(`[session] init success -> signedIn (${reason})`);
      }

      setUser(currentUser);
      setState('signedIn');
    };

    const timeoutId = setTimeout(() => {
      if (__DEV__) {
        console.warn('[session] init timeout fired, forcing signedOut');
      }
      void completeBootAsSignedOut('timeout');
    }, BOOT_TIMEOUT_MS);

    async function bootstrap() {
      let storedSession: Awaited<ReturnType<typeof getStoredSession>> | null = null;
      try {
        if (__DEV__) {
          console.log('[session] init started');
          console.log('[session] token/session restore started');
        }
        storedSession = await getStoredSession();

        if (!storedSession?.accessToken) {
          await completeBootAsSignedOut('no stored access token', { clearSession: false });
          return;
        }

        setApiAuthToken(storedSession.accessToken);
        if (__DEV__) {
          console.log('[session] backend validation started');
        }
        const currentUser = await getCurrentUser();
        completeBootAsSignedIn(currentUser, 'validated current user');
      } catch (error) {
        if (__DEV__) {
          console.warn('[session] init error', error);
        }

        if (storedSession?.refreshToken) {
          try {
            if (__DEV__) {
              console.log('[session] backend validation started (refresh fallback)');
            }
            const refreshed = await refresh(storedSession.refreshToken);
            await setStoredSession(toStoredSession(refreshed.tokens));
            setApiAuthToken(refreshed.tokens.access_token);
            completeBootAsSignedIn(refreshed.user, 'refreshed session');
            return;
          } catch (refreshError) {
            if (__DEV__) {
              console.warn('[session] refresh during init failed', refreshError);
            }
          }
        }

        await completeBootAsSignedOut('init error');
      } finally {
        clearTimeout(timeoutId);
      }
    }

    void bootstrap();

    return () => {
      clearTimeout(timeoutId);
      completed = true;
    };
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
