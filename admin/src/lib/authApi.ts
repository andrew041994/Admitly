import { apiRequest } from './apiClient';
import { AdminSession, clearAdminSession, getAdminSession, setAdminSession } from './authSession';

export async function loginAdmin(email: string, password: string): Promise<AdminSession> {
  const response = await apiRequest('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
    skipAuth: true,
  });
  const payload = (await response.json()) as {
    user: AdminSession['user'];
    tokens: { access_token: string; refresh_token: string };
  };
  if (!payload.user.is_admin) {
    throw new Error('Admin access required.');
  }
  const session = {
    user: payload.user,
    accessToken: payload.tokens.access_token,
    refreshToken: payload.tokens.refresh_token,
  };
  setAdminSession(session);
  return session;
}

export async function validateAdminSession(): Promise<AdminSession> {
  const session = getAdminSession();
  if (!session) throw new Error('Authentication required.');
  const response = await apiRequest('/auth/me');
  const user = (await response.json()) as AdminSession['user'];
  if (!user.is_admin) {
    clearAdminSession();
    throw new Error('Admin access required.');
  }
  const refreshedSession = { ...session, user };
  setAdminSession(refreshedSession);
  return refreshedSession;
}
