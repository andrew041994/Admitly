export type AdminUser = {
  id: number;
  email: string;
  full_name: string | null;
  is_admin: boolean;
};

export type AdminSession = {
  user: AdminUser;
  accessToken: string;
  refreshToken: string;
};

const sessionKey = 'admitly.admin.session';

export function getAdminSession(): AdminSession | null {
  const raw = window.localStorage.getItem(sessionKey);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as AdminSession;
  } catch {
    window.localStorage.removeItem(sessionKey);
    return null;
  }
}

export function setAdminSession(session: AdminSession) {
  window.localStorage.setItem(sessionKey, JSON.stringify(session));
}

export function clearAdminSession() {
  window.localStorage.removeItem(sessionKey);
}
