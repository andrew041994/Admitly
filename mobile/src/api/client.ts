import { env } from '../config/env';

let authToken: string | null = null;

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

export function setApiAuthToken(token: string | null) {
  authToken = token;
}

type ApiOptions = RequestInit & { path: string };

export async function apiRequest<T>({ path, headers, ...init }: ApiOptions): Promise<T> {
  const response = await fetch(`${env.apiBaseUrl}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
      ...(headers ?? {}),
    },
  });

  if (!response.ok) {
    let detail = `API request failed: ${response.status}`;

    try {
      const errorBody = (await response.json()) as { detail?: string };
      if (errorBody.detail) {
        detail = errorBody.detail;
      }
    } catch {
      // ignore body parsing errors and keep generic message
    }

    throw new ApiError(detail, response.status);
  }

  return (await response.json()) as T;
}
