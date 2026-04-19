const DEFAULT_API_BASE_URL = 'https://admitly.onrender.com';

export const apiBaseUrl =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim() || DEFAULT_API_BASE_URL;
