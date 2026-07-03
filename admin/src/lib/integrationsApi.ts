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
  endpoint_url: string;
  event_id: string;
  event_type: string;
  attempt_number: number;
  status: string;
  response_status_code: number | null;
  failure_reason: string | null;
  next_retry_at: string | null;
  delivered_at: string | null;
  delivery_kind: string;
  redelivery_of_delivery_id: number | null;
};

export async function listApiKeys() {
  const res = await apiRequest('/admin/integrations/api-keys');
  return (await res.json()) as ApiKeyRecord[];
}

export async function createApiKey(payload: { name: string; scopes: string[] }) {
  const res = await apiRequest('/admin/integrations/api-keys', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  return (await res.json()) as ApiKeyRecord & { raw_key: string };
}

export async function listWebhooks() {
  const res = await apiRequest('/admin/integrations/webhooks');
  return (await res.json()) as WebhookEndpointRecord[];
}

export async function createWebhook(payload: { name: string; target_url: string; subscribed_events: string[] }) {
  const res = await apiRequest('/admin/integrations/webhooks', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  return (await res.json()) as WebhookEndpointRecord & { signing_secret: string };
}

export async function listDeliveries() {
  const res = await apiRequest('/admin/integrations/deliveries');
  return (await res.json()) as DeliveryRecord[];
}


export async function redeliverDelivery(deliveryId: number) {
  const res = await apiRequest(`/admin/integrations/deliveries/${deliveryId}/redeliver`, {
    method: 'POST',
  });
  return (await res.json()) as DeliveryRecord;
}
