import { apiRequest } from './apiClient';

export type ApiKeyRecord = {
  id: number;
  name: string;
  key_prefix: string;
  scopes: string[];
  created_at: string;
  revoked_at: string | null;
  last_used_at: string | null;
};

export type WebhookEndpointRecord = {
  id: number;
  name: string;
  target_url: string;
  subscribed_events: string[];
  schema_version: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  disabled_at: string | null;
};

export type DeliveryRecord = {
  id: number;
  endpoint_id: number;
  event_id: string;
  event_type: string;
  attempt_number: number;
  status: string;
  response_status_code: number | null;
  failure_reason: string | null;
  next_retry_at: string | null;
  delivered_at: string | null;
};

export async function listApiKeys(userId: number) {
  const res = await apiRequest('/admin/integrations/api-keys', { headers: { 'X-User-Id': String(userId) } });
  return (await res.json()) as ApiKeyRecord[];
}

export async function createApiKey(userId: number, payload: { name: string; scopes: string[] }) {
  const res = await apiRequest('/admin/integrations/api-keys', {
    method: 'POST',
    headers: { 'X-User-Id': String(userId) },
    body: JSON.stringify(payload),
  });
  return (await res.json()) as ApiKeyRecord & { raw_key: string };
}

export async function listWebhooks(userId: number) {
  const res = await apiRequest('/admin/integrations/webhooks', { headers: { 'X-User-Id': String(userId) } });
  return (await res.json()) as WebhookEndpointRecord[];
}

export async function createWebhook(userId: number, payload: { name: string; target_url: string; subscribed_events: string[] }) {
  const res = await apiRequest('/admin/integrations/webhooks', {
    method: 'POST',
    headers: { 'X-User-Id': String(userId) },
    body: JSON.stringify(payload),
  });
  return (await res.json()) as WebhookEndpointRecord & { signing_secret: string };
}

export async function listDeliveries(userId: number) {
  const res = await apiRequest('/admin/integrations/deliveries', { headers: { 'X-User-Id': String(userId) } });
  return (await res.json()) as DeliveryRecord[];
}
