import { apiBaseUrl } from './config';

type RequestOptions = Omit<RequestInit, 'headers'> & {
  headers?: HeadersInit;
};

export async function apiRequest(path: string, options: RequestOptions = {}) {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  });

  if (!response.ok) {
    throw new Error(`API request failed (${response.status})`);
  }

  return response;
}
