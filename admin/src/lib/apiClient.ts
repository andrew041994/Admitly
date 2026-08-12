import { apiBaseUrl } from './config';
import {
  clearAuthSession,
  getAuthSession,
  getRefreshToken,
  setAuthSession,
  type AuthTokens,
  type AuthUser,
} from './authSession';

type RequestOptions = Omit<RequestInit, 'headers'> & {
  headers?: HeadersInit;
  skipAuth?: boolean;
  skipRefresh?: boolean;
};

export class ApiError extends Error {
  status: number;
  detail: string;
  rawDetail: unknown;
  requestId: string | null;

  constructor(status: number, detail: unknown, requestId: string | null = null) {
    const message = typeof detail === 'string'
      ? detail
      : detail && typeof detail === 'object' && 'message' in detail && typeof detail.message === 'string'
        ? detail.message
        : `API request failed (${status})`;
    super(`${message}${requestId ? ` (Reference: ${requestId})` : ''}`);
    this.status = status;
    this.detail = message;
    this.rawDetail = detail;
    this.requestId = requestId;
  }
}

let refreshInFlight: Promise<boolean> | null = null;

async function refreshBrowserSession(): Promise<boolean> {
  if (refreshInFlight) return refreshInFlight;
  const refreshToken = getRefreshToken();
  if (!refreshToken) return false;
  refreshInFlight = (async () => {
    try {
      const response = await fetch(`${apiBaseUrl}/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      if (!response.ok) return false;
      const payload = await response.json() as { user: AuthUser; tokens: AuthTokens };
      try {
        setAuthSession(payload.user, payload.tokens);
      } catch {
        await fetch(`${apiBaseUrl}/auth/logout`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token: payload.tokens.refresh_token }),
        }).catch(() => undefined);
        return false;
      }
      return true;
    } catch {
      return false;
    } finally {
      refreshInFlight = null;
    }
  })();
  const refreshed = await refreshInFlight;
  if (!refreshed) {
    clearAuthSession();
    window.dispatchEvent(new CustomEvent('admitly-auth-required'));
  }
  return refreshed;
}

async function requestOnce(path: string, options: RequestOptions) {
  const { skipAuth = false, skipRefresh: _skipRefresh = false, ...requestOptions } = options;
  const headers = new Headers(requestOptions.headers);
  const isFormData = typeof FormData !== 'undefined' && requestOptions.body instanceof FormData;
  if (!isFormData && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  if (!skipAuth) {
    const token = getAuthSession()?.accessToken;
    if (token) headers.set('Authorization', `Bearer ${token}`);
  }
  return fetch(`${apiBaseUrl}${path}`, { ...requestOptions, headers });
}

export async function apiRequest(path: string, options: RequestOptions = {}) {
  const accessTokenUsed = getAuthSession()?.accessToken;
  let response = await requestOnce(path, options);
  if (!options.skipAuth && !options.skipRefresh && response.status === 401) {
    const newerAccessToken = getAuthSession()?.accessToken;
    if (newerAccessToken && newerAccessToken !== accessTokenUsed) {
      response = await requestOnce(path, { ...options, skipRefresh: true });
    } else if (await refreshBrowserSession()) {
      response = await requestOnce(path, { ...options, skipRefresh: true });
    }
  }
  if (!response.ok) {
    let detail: unknown = `API request failed (${response.status})`;
    try {
      const payload = await response.json() as { detail?: unknown };
      if (payload.detail !== undefined) detail = payload.detail;
    } catch {
      // Preserve the generic error for non-JSON responses.
    }
    if (!options.skipAuth && response.status === 401) {
      clearAuthSession();
      window.dispatchEvent(new CustomEvent('admitly-auth-required'));
    }
    throw new ApiError(response.status, detail, response.headers.get('X-Request-ID'));
  }
  return response;
}

export async function apiJson<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const response = await apiRequest(path, options);
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
