import { apiRequest } from './client';

export type AuthUser = {
  id: number;
  email: string;
  full_name: string;
  phone_number: string | null;
  is_active: boolean;
  is_verified: boolean;
  is_admin: boolean;
  auth_provider: string;
  created_at: string;
  updated_at: string;
  last_login_at: string | null;
};

export type AuthTokens = {
  access_token: string;
  refresh_token: string;
  token_type: string;
  access_expires_in_seconds: number;
  refresh_expires_in_seconds: number;
};

type AuthResponse = {
  user: AuthUser;
  tokens: AuthTokens;
};

export async function login(email: string, password: string): Promise<AuthResponse> {
  return apiRequest<AuthResponse>({
    path: '/auth/login',
    method: 'POST',
    body: JSON.stringify({ email, password }),
  });
}

export async function register(fullName: string, email: string, password: string): Promise<AuthResponse> {
  return apiRequest<AuthResponse>({
    path: '/auth/register',
    method: 'POST',
    body: JSON.stringify({ full_name: fullName, email, password }),
  });
}

export async function refresh(refreshToken: string): Promise<AuthResponse> {
  return apiRequest<AuthResponse>({
    path: '/auth/refresh',
    method: 'POST',
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
}

export async function getCurrentUser(): Promise<AuthUser> {
  return apiRequest<AuthUser>({
    path: '/auth/me',
    method: 'GET',
  });
}

export async function requestPasswordReset(email: string): Promise<{ success: boolean }> {
  return apiRequest<{ success: boolean }>({
    path: '/auth/forgot-password',
    method: 'POST',
    body: JSON.stringify({ email }),
  });
}

export async function resetPassword(token: string, newPassword: string): Promise<{ success: boolean }> {
  return apiRequest<{ success: boolean }>({
    path: '/auth/reset-password',
    method: 'POST',
    body: JSON.stringify({ token, new_password: newPassword }),
  });
}

export async function logout(): Promise<{ success: boolean }> {
  return apiRequest<{ success: boolean }>({
    path: '/auth/logout',
    method: 'POST',
  });
}
