import { apiRequest } from './apiClient';

export interface SupportCase {
  id: number;
  order_id: number;
  status: string;
  priority: string;
  category: string;
  created_by_user_id: number | null;
  assigned_to_user_id: number | null;
  closed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface SupportNote {
  id: number;
  support_case_id: number;
  author_user_id: number;
  body: string;
  is_system_note: boolean;
  created_at: string;
}

export interface SupportTimelineItem {
  timestamp: string;
  type: string;
  title: string;
  description: string;
  actor: string | null;
  metadata: Record<string, unknown> | null;
}

export interface AdminAuditItem {
  id: number;
  actor_user_id: number;
  target_type: string;
  target_id: string;
  action_type: string;
  reason: string | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
}

export interface SupportSnapshot {
  order_id: number;
  event_id: number;
  event_title: string | null;
  buyer_user_id: number;
  order_status: string;
  quantity: number;
  subtotal_amount: number;
  discount_amount: number;
  total_amount: number;
  currency: string;
  payment_reference: string | null;
  payment_verification_status: string;
  payment_submitted_at: string | null;
  paid_at: string | null;
  refund_status: string;
  refunded_at: string | null;
  dispute_count: number;
  transfer_invite_count: number;
  reconciliation_status: string;
  payout_status: string;
  promo_code_text: string | null;
  support_case: SupportCase | null;
  support_notes: SupportNote[];
  timeline: SupportTimelineItem[];
  admin_audits: AdminAuditItem[];
}

export interface SupportCasePatchPayload {
  status?: string;
  priority?: string;
  assigned_to_user_id?: number | null;
  category?: string;
}

export interface SupportActionPayload {
  action_type: string;
  reason?: string;
  payload?: Record<string, unknown>;
}

export interface SupportActionResult {
  action_type: string;
  success: boolean;
  message: string;
}

export async function fetchSupportSnapshot(orderId: number) {
  const response = await apiRequest(`/admin/support/orders/${orderId}`);
  return (await response.json()) as SupportSnapshot;
}

export async function createSupportNote(orderId: number, body: string) {
  const response = await apiRequest(`/admin/support/orders/${orderId}/notes`, {
    method: 'POST',
    body: JSON.stringify({ body }),
  });
  return (await response.json()) as SupportNote;
}

export async function updateSupportCase(orderId: number, payload: SupportCasePatchPayload) {
  const response = await apiRequest(`/admin/support/orders/${orderId}/case`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
  return (await response.json()) as SupportCase;
}

export async function runSupportAction(orderId: number, payload: SupportActionPayload) {
  const response = await apiRequest(`/admin/support/orders/${orderId}/actions`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  return (await response.json()) as SupportActionResult;
}
