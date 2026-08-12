import { apiJson } from './apiClient';
import {
  clearAuthSession,
  getAuthSession,
  getRefreshToken,
  setAuthSession,
  updateAuthUser,
  type AuthSession,
  type AuthTokens,
  type AuthUser,
} from './authSession';

type AuthResponse = { user: AuthUser; tokens: AuthTokens };

async function revokeUnstoredSession(refreshToken: string) {
  try {
    await apiJson('/auth/logout', {
      method: 'POST',
      body: JSON.stringify({ refresh_token: refreshToken }),
      skipAuth: true,
      skipRefresh: true,
    });
  } catch {
    // The original storage error remains authoritative.
  }
}

export async function login(email: string, password: string): Promise<AuthSession> {
  const payload = await apiJson<AuthResponse>('/auth/login', {
    method: 'POST', body: JSON.stringify({ email: email.trim().toLowerCase(), password }), skipAuth: true,
  });
  try {
    setAuthSession(payload.user, payload.tokens);
  } catch (error) {
    await revokeUnstoredSession(payload.tokens.refresh_token);
    throw error;
  }
  return getAuthSession()!;
}

export async function register(fullName: string, email: string, password: string): Promise<AuthSession> {
  const payload = await apiJson<AuthResponse>('/auth/register', {
    method: 'POST',
    body: JSON.stringify({ full_name: fullName.trim(), email: email.trim().toLowerCase(), password }),
    skipAuth: true,
  });
  try {
    setAuthSession(payload.user, payload.tokens);
  } catch (error) {
    await revokeUnstoredSession(payload.tokens.refresh_token);
    throw error;
  }
  return getAuthSession()!;
}

export async function validateSession(): Promise<AuthSession> {
  const session = getAuthSession();
  if (!session) throw new Error('Authentication required.');
  const user = await apiJson<AuthUser>('/auth/me');
  updateAuthUser(user);
  return getAuthSession()!;
}

export async function validateAdminSession() {
  const session = await validateSession();
  if (!session.user.is_admin) throw new Error('Admin access required.');
  return session;
}

export async function logout() {
  try {
    const refreshToken = getRefreshToken();
    if (refreshToken) await apiJson<{ success: boolean }>('/auth/logout', {
      method: 'POST',
      body: JSON.stringify({ refresh_token: refreshToken }),
      skipRefresh: true,
    });
  } finally {
    clearAuthSession();
  }
}

export async function logoutAll() {
  try {
    await apiJson<{ success: boolean; revoked_sessions: number }>('/auth/logout-all', { method: 'POST' });
  } finally {
    clearAuthSession();
  }
}

export const requestPasswordReset = (email: string) => apiJson<{ success: boolean }>('/auth/forgot-password', {
  method: 'POST', body: JSON.stringify({ email: email.trim().toLowerCase() }), skipAuth: true,
});
export const resetPassword = (token: string, newPassword: string) => apiJson<{ success: boolean }>('/auth/reset-password', {
  method: 'POST', body: JSON.stringify({ token, new_password: newPassword }), skipAuth: true,
});
export const verifyEmail = (token: string) => apiJson<{ success: boolean }>('/auth/verify', {
  method: 'POST', body: JSON.stringify({ token }), skipAuth: true,
});
export const requestVerification = (email: string) => apiJson<{ success: boolean }>('/auth/request-verification', {
  method: 'POST', body: JSON.stringify({ email }), skipAuth: true,
});
