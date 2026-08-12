export type AuthUser = {
  id: number;
  email: string;
  full_name: string;
  is_active: boolean;
  is_verified: boolean;
  email_verified_at: string | null;
  requires_email_verification: boolean;
  is_admin: boolean;
  auth_provider: string;
  created_at: string;
  updated_at: string;
  last_login_at: string | null;
  creator_age_identity_verification_status: 'pending' | 'verified' | 'revoked';
};

export type AuthTokens = {
  access_token: string;
  refresh_token: string;
  token_type: string;
  access_expires_in_seconds: number;
  refresh_expires_in_seconds: number;
};

export type AuthSession = { user: AuthUser; accessToken: string };

const refreshKey = 'admitly.web.refresh-token';
const legacyAdminKey = 'admitly.admin.session';
let currentSession: AuthSession | null = null;

export function getAuthSession() {
  return currentSession;
}

export function getRefreshToken() {
  return window.sessionStorage.getItem(refreshKey);
}

export function setAuthSession(user: AuthUser, tokens: AuthTokens) {
  currentSession = { user, accessToken: tokens.access_token };
  window.sessionStorage.setItem(refreshKey, tokens.refresh_token);
  window.localStorage.removeItem(legacyAdminKey);
  window.dispatchEvent(new Event('admitly-auth-changed'));
}

export function updateAuthUser(user: AuthUser) {
  if (!currentSession) return;
  currentSession = { ...currentSession, user };
  window.dispatchEvent(new Event('admitly-auth-changed'));
}

export function clearAuthSession() {
  currentSession = null;
  window.sessionStorage.removeItem(refreshKey);
  window.localStorage.removeItem(legacyAdminKey);
  window.dispatchEvent(new Event('admitly-auth-changed'));
}

/** One-time compatibility migration for an already signed-in legacy admin tab. */
export function migrateLegacyAdminRefreshToken() {
  if (getRefreshToken()) return;
  const raw = window.localStorage.getItem(legacyAdminKey);
  if (!raw) return;
  try {
    const parsed = JSON.parse(raw) as { refreshToken?: unknown };
    if (typeof parsed.refreshToken === 'string' && parsed.refreshToken) {
      window.sessionStorage.setItem(refreshKey, parsed.refreshToken);
    }
  } catch {
    // A malformed legacy value must never prevent the application from booting.
  } finally {
    window.localStorage.removeItem(legacyAdminKey);
  }
}
