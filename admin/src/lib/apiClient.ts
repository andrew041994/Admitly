import { apiBaseUrl } from './config';

type RequestOptions = Omit<RequestInit, 'headers'> & {
  headers?: HeadersInit;
};

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail || `API request failed (${status})`);
    this.status = status;
    this.detail = detail || `API request failed (${status})`;
  }
}

export async function apiRequest(path: string, options: RequestOptions = {}) {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  });

  if (!response.ok) {
    let detail = `API request failed (${response.status})`;
    try {
      const payload = (await response.json()) as { detail?: string };
      if (payload?.detail) {
        detail = payload.detail;
      }
    } catch {
      // Keep generic message when response body is not JSON.
    }
    throw new ApiError(response.status, detail);
  }

  return response;
}
