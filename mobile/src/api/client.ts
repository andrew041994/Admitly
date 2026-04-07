import { env } from '../config/env';

let authToken: string | null = null;

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
    throw new Error(`API request failed: ${response.status}`);
  }

  return (await response.json()) as T;
}
