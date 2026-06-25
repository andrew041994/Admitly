import { env } from '../config/env';

let authToken: string | null = null;

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(message: string, status: number, detail?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
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

    throw new ApiError(message, response.status, parsedDetail);
  }

  return (await response.json()) as T;
}
