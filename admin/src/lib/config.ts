const DEFAULT_API_BASE_URL = 'postgresql://neondb_owner:npg_jKSZablLD72J@ep-purple-rain-anzfvs86-pooler.c-6.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require';

export const apiBaseUrl =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim() || DEFAULT_API_BASE_URL;
