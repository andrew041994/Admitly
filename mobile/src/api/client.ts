import { env } from '../config/env';

let authToken: string | null = null;
let unauthorizedHandler: (() => void | Promise<void>) | null = null;

export class ApiError extends Error {
  status: number;
  detail: unknown;
  requestId: string | null;

  constructor(message: string, status: number, detail?: unknown, requestId: string | null = null) {
    super(`${message}${requestId ? ` (Reference: ${requestId})` : ''}`);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
    this.requestId = requestId;
  }
}

export function setApiAuthToken(token: string | null) {
  authToken = token;
}

export function setApiUnauthorizedHandler(handler: (() => void | Promise<void>) | null) {
  unauthorizedHandler = handler;
}

type ApiOptions = RequestInit & { path: string };

export async function apiRequest<T>({ path, headers, body, ...init }: ApiOptions): Promise<T> {
  const isFormData = typeof FormData !== 'undefined' && body instanceof FormData;
  const requestHeaders = new Headers(headers);
  if (!isFormData && !requestHeaders.has('Content-Type')) {
    requestHeaders.set('Content-Type', 'application/json');
  }
  // Authentication is session-owned; individual feature calls cannot override it.
  if (authToken) {
    requestHeaders.set('Authorization', `Bearer ${authToken}`);
  } else {
    requestHeaders.delete('Authorization');
  }
  const response = await fetch(`${env.apiBaseUrl}${path}`, {
    ...init,
    body,
    headers: requestHeaders,
  });

  if (!response.ok) {
    let message = `API request failed: ${response.status}`;
    let parsedDetail: unknown;

    try {
      const errorBody = (await response.json()) as { detail?: unknown };
      parsedDetail = errorBody.detail;
      if (typeof errorBody.detail === 'string') {
        message = errorBody.detail;
      } else if (errorBody.detail && typeof errorBody.detail === 'object' && 'message' in errorBody.detail) {
        const detailMessage = (errorBody.detail as { message?: unknown }).message;
        if (typeof detailMessage === 'string') {
          message = detailMessage;
        }
      }
    } catch {
      // ignore body parsing errors and keep generic message
    }

    if (response.status === 401 && authToken && unauthorizedHandler) {
      const handler = unauthorizedHandler;
      authToken = null;
      void handler();
    }
    throw new ApiError(message, response.status, parsedDetail, response.headers.get('X-Request-ID'));
  }

  return (await response.json()) as T;
}
