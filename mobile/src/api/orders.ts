import { apiRequest } from './client';

export type EventTicketTier = {
  id: number;
  name: string;
  description: string | null;
  price_amount: string;
  currency: string;
  min_per_order: number;
  max_per_order: number;
  available_quantity: number;
  is_active: boolean;
};

export type PurchaseSelectionItem = { ticket_tier_id: number; quantity: number };

export type EventEndedDetail = {
  code: 'EVENT_ENDED';
  event_id: number;
  event_title: string;
  event_end_at: string;
  server_now: string;
  message: string;
};

export type StartedEventConfirmationDetail = {
  code: 'EVENT_ALREADY_STARTED_CONFIRMATION_REQUIRED';
  event_id: number;
  event_title: string;
  event_start_at: string;
  event_end_at: string;
  server_now: string;
  seconds_until_event_end: number;
  human_readable_time_remaining: string;
  message: string;
};

export type OrderItem = { id: number; ticket_tier_id: number; quantity: number; unit_price: number };

export type Order = {
  id: number;
  event_id: number;
  status: string;
  subtotal_amount: number;
  discount_amount: number;
  total_amount: number;
  currency: string;
  reference_code: string;
  payment_method: string | null;
  payment_verification_status: string;
  items: OrderItem[];
};

export type MmgCheckoutResponse = {
  order_id: number;
  payment_reference: string;
  checkout_url: string | null;
  status: string;
  payment_verification_status: string;
};

export type MmgAgentResponse = {
  order_id: number;
  payment_reference: string;
  instructions: string | null;
  status: string;
  payment_verification_status: string;
};

export type CompleteMmgAgentResponse = {
  order_id: number;
  payment_reference: string;
  status: string;
  payment_verification_status: string;
  message: string;
};

export type DevTestCheckoutResponse = {
  order_id: number;
  payment_reference: string;
  status: string;
  payment_verification_status: string;
  message: string;
};

export async function createOrderFromSelection(
  eventId: number,
  items: PurchaseSelectionItem[],
  acknowledgeStartedEvent = false,
): Promise<Order> {
  return apiRequest<Order>({
    path: '/orders',
    method: 'POST',
    body: JSON.stringify({ event_id: eventId, items, acknowledge_started_event: acknowledgeStartedEvent }),
  });
}

export async function initiateMmgCheckout(orderId: number): Promise<MmgCheckoutResponse> {
  return apiRequest<MmgCheckoutResponse>({ path: `/orders/${orderId}/payments/mmg/initiate`, method: 'POST' });
}

export async function initiateMmgAgentCheckout(orderId: number): Promise<MmgAgentResponse> {
  return apiRequest<MmgAgentResponse>({ path: `/orders/${orderId}/payments/mmg-agent/initiate`, method: 'POST' });
}

export async function completeMmgAgentPayment(orderId: number, submittedReferenceCode: string): Promise<CompleteMmgAgentResponse> {
  return apiRequest<CompleteMmgAgentResponse>({
    path: `/orders/${orderId}/payments/mmg-agent/complete`,
    method: 'POST',
    body: JSON.stringify({ submitted_reference_code: submittedReferenceCode }),
  });
}

export async function getOrder(orderId: number): Promise<Order> {
  return apiRequest<Order>({ path: `/orders/${orderId}`, method: 'GET' });
}

export async function completeDevTestCheckout(orderId: number): Promise<DevTestCheckoutResponse> {
  return apiRequest<DevTestCheckoutResponse>({ path: `/orders/${orderId}/payments/dev-test/complete`, method: 'POST' });
}
