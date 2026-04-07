import { createContext, PropsWithChildren, useContext, useEffect, useMemo, useState } from 'react';

import { setApiAuthToken } from '../api/client';
import {
  clearStoredSessionToken,
  getStoredSessionToken,
  setStoredSessionToken,
} from '../storage/sessionStorage';

type SessionState = 'booting' | 'signedOut' | 'signedIn';

type SessionContextValue = {
  state: SessionState;
  token: string | null;
  signInPlaceholder: () => Promise<void>;
  signOut: () => Promise<void>;
};

const SessionContext = createContext<SessionContextValue | undefined>(undefined);

export function SessionProvider({ children }: PropsWithChildren) {
  const [state, setState] = useState<SessionState>('booting');
  const [token, setToken] = useState<string | null>(null);

  useEffect(() => {
    async function bootstrap() {
      const storedToken = await getStoredSessionToken();
      if (storedToken) {
        setToken(storedToken);
        setApiAuthToken(storedToken);
        setState('signedIn');
        return;
      }

      setState('signedOut');
    }

    bootstrap();
  }, []);

  const value = useMemo(
    () => ({
      state,
      token,
      signInPlaceholder: async () => {
        const placeholderToken = 'phase-1-placeholder-token';
        await setStoredSessionToken(placeholderToken);
        setApiAuthToken(placeholderToken);
        setToken(placeholderToken);
        setState('signedIn');
      },
      signOut: async () => {
        await clearStoredSessionToken();
        setApiAuthToken(null);
        setToken(null);
        setState('signedOut');
      },
    }),
    [state, token],
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
