import { clearAdminSession, getAdminSession } from './authSession';
import { apiBaseUrl } from './config';

type RequestOptions = Omit<RequestInit, 'headers'> & {
  headers?: HeadersInit;
  skipAuth?: boolean;
};

export class ApiError extends Error {
  status: number;
  detail: string;
  requestId: string | null;

  constructor(status: number, detail: string, requestId: string | null = null) {
    super(`${detail || `API request failed (${status})`}${requestId ? ` (Reference: ${requestId})` : ''}`);
    this.status = status;
    this.detail = detail || `API request failed (${status})`;
    this.requestId = requestId;
  }
}

export async function apiRequest(path: string, options: RequestOptions = {}) {
  const { skipAuth = false, ...requestOptions } = options;
  const headers = new Headers(requestOptions.headers);
  if (!headers.has('Content-Type')) headers.set('Content-Type', 'application/json');

  const session = getAdminSession();
  if (!skipAuth && session?.accessToken) {
    headers.set('Authorization', `Bearer ${session.accessToken}`);
  }

  const response = await fetch(`${apiBaseUrl}${path}`, {
    ...requestOptions,
    headers,
  });

  if (!response.ok) {
    let detail = `API request failed (${response.status})`;
    try {
      const payload = (await response.json()) as { detail?: string };
      if (payload?.detail) detail = payload.detail;
    } catch {
      // Keep generic message when response body is not JSON.
    }
    if (!skipAuth && (response.status === 401 || response.status === 403)) {
      clearAdminSession();
      window.dispatchEvent(new CustomEvent('admin-auth-required', { detail }));
    }
    throw new ApiError(response.status, detail, response.headers.get('X-Request-ID'));
  }

  return response;
}
