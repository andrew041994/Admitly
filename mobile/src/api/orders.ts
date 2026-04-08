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

export async function createOrderFromSelection(eventId: number, items: PurchaseSelectionItem[]): Promise<Order> {
  return apiRequest<Order>({ path: '/orders', method: 'POST', body: JSON.stringify({ event_id: eventId, items }) });
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
