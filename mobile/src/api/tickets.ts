import { apiRequest } from './client';

export type WalletTicketCard = {
  id: number;
  ticket_code: string;
  ticket_status: string;
  display_status: 'active' | 'used' | 'invalid' | string;
  is_valid_for_entry: boolean;
  can_display_entry_code: boolean;
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
