import { apiRequest } from './client';

export type WalletTicketCard = {
  id: number;
  ticket_code: string;
  manual_code: string;
  manual_code_display: string;
  ticket_status: string;
  display_status: 'active' | 'used' | 'expired' | 'refunded';
  is_valid_for_entry: boolean;
  can_display_entry_code: boolean;
  can_transfer: boolean;
  transfer_unavailable_reason: string | null;
  event: {
    id: number;
    title: string;
    start_at: string;
    end_at: string | null;
    timezone: string | null;
    banner_image_url: string | null;
    is_upcoming: boolean;
    status: string | null;
  };
  venue: {
    name: string | null;
    address_summary: string | null;
  };
  organizer: {
    name: string | null;
  };
  ticket_tier_name: string;
  order_id: number;
  order_reference: string | null;
  issued_at: string;
  checked_in_at: string | null;
};

export type WalletTicketDetail = WalletTicketCard & {
  qr_payload: string;
  check_in_token: string;
  check_in_method: string | null;
  voided_at: string | null;
  void_reason: string | null;
  order_status: string;
  order_refund_status: string;
};

export async function listMyTickets(): Promise<WalletTicketCard[]> {
  return apiRequest<WalletTicketCard[]>({ path: '/me/tickets', method: 'GET' });
}

export async function getMyTicket(ticketId: number): Promise<WalletTicketDetail> {
  return apiRequest<WalletTicketDetail>({ path: `/me/tickets/${ticketId}`, method: 'GET' });
}

export type TicketQrResponse = {
  ticket_public_token: string;
  qr_payload: string;
  public_ticket_url: string;
  qr_image_url: string;
  qr_data_uri: string;
};

export async function getMyTicketQr(ticketId: number): Promise<TicketQrResponse> {
  return apiRequest<TicketQrResponse>({ path: `/tickets/${ticketId}/qr`, method: 'GET' });
}

export type TicketScanResponse = {
  success?: boolean;
  code?: string;
  state?: 'success' | 'already_used' | 'invalid' | 'wrong_event' | string;
  status?: string;
  result?: string;
  message?: string;
  attendee_name?: string;
  ticket_type?: string;
  checked_in_at?: string;
};

export async function scanTicket(payload: string, eventId: number): Promise<TicketScanResponse> {
  return apiRequest<TicketScanResponse>({
    path: '/tickets/scan',
    method: 'POST',
    body: JSON.stringify({ payload, selected_event_id: eventId }),
  });
}


export async function checkInTicketManually(manualCode: string, eventId: number): Promise<TicketScanResponse> {
  return apiRequest<TicketScanResponse>({
    path: `/events/${eventId}/check-in/manual`,
    method: 'POST',
    body: JSON.stringify({ ticket_code: manualCode }),
  });
}

export type TicketTransfer = {
  id: number;
  ticket_id: number;
  direction: 'incoming' | 'outgoing';
  status: 'pending' | 'accepted' | 'declined' | 'canceled' | 'expired' | string;
  recipient_identifier: string;
  event_title: string;
  ticket_tier_name: string;
  starts_at: string;
  expires_at: string | null;
  accepted_at: string | null;
  declined_at: string | null;
  canceled_at: string | null;
  created_at: string;
  updated_at: string;
};

export type TicketTransferRecipientResolution = {
  recipient_display_name: string;
  recipient_email: string;
  masked_email: string;
  recipient_resolution_reference: string;
  resolution_expires_at: string;
};

export async function resolveTicketTransferRecipient(
  ticketId: number,
  email: string,
): Promise<TicketTransferRecipientResolution> {
  return apiRequest({
    path: `/tickets/${ticketId}/transfer-recipient-resolutions`,
    method: 'POST',
    body: JSON.stringify({ email }),
  });
}

export async function createTicketTransfer(
  ticketId: number,
  recipientResolutionReference: string,
): Promise<{ id: number; ticket_id: number; status: string }> {
  return apiRequest({
    path: `/tickets/${ticketId}/transfers`,
    method: 'POST',
    body: JSON.stringify({ recipient_resolution_reference: recipientResolutionReference }),
  });
}

export async function listMyTicketTransfers(direction: 'all' | 'incoming' | 'outgoing' = 'all'): Promise<TicketTransfer[]> {
  return apiRequest({ path: `/me/ticket-transfers?direction=${direction}`, method: 'GET' });
}

async function actOnTransfer(transferId: number, action: 'accept' | 'decline' | 'cancel'): Promise<void> {
  await apiRequest({ path: `/ticket-transfers/${transferId}/${action}`, method: 'POST' });
}

export const acceptTicketTransfer = (transferId: number) => actOnTransfer(transferId, 'accept');
export const declineTicketTransfer = (transferId: number) => actOnTransfer(transferId, 'decline');
export const cancelTicketTransfer = (transferId: number) => actOnTransfer(transferId, 'cancel');
