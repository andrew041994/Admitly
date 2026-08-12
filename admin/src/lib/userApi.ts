import { apiJson } from './apiClient';

export type TicketDisplayStatus = 'active' | 'used' | 'expired' | 'refunded';
export type WalletTicket = {
  id: number; ticket_code: string; manual_code: string; manual_code_display: string; display_code: string | null;
  ticket_status: string; display_status: TicketDisplayStatus; is_valid_for_entry: boolean; can_display_entry_code: boolean;
  can_transfer: boolean; transfer_unavailable_reason: string | null;
  event: { id: number; title: string; start_at: string; end_at: string | null; timezone: string | null; banner_image_url: string | null; is_upcoming: boolean; status: string | null };
  venue: { name: string | null; address_summary: string | null }; organizer: { name: string | null };
  ticket_tier_name: string; order_id: number; order_reference: string | null; issued_at: string; checked_in_at: string | null;
  ownership: { is_current_owner: boolean; purchaser_user_id: number; owner_user_id: number; acquired_via_transfer: boolean };
  transferred_at: string | null; transfer_count: number;
};
export type WalletTicketDetail = WalletTicket & { qr_payload: string; check_in_token: string; check_in_method: string | null; voided_at: string | null; void_reason: string | null; order_status: string; order_refund_status: string };

export const listTickets = () => apiJson<WalletTicket[]>('/me/tickets');
export const getTicket = (id: number) => apiJson<WalletTicketDetail>(`/me/tickets/${id}`);
export const getTicketQr = (id: number) => apiJson<{ qr_data_uri: string; qr_payload: string }>(`/tickets/${id}/qr`);
export const resolveTransferRecipient = (id: number, email: string) => apiJson<{ recipient_display_name: string; masked_email: string; recipient_resolution_reference: string }>(`/tickets/${id}/transfer-recipient-resolutions`, { method: 'POST', body: JSON.stringify({ email }) });
export const createTransfer = (id: number, reference: string) => apiJson<{ id: number; status: string }>(`/tickets/${id}/transfers`, { method: 'POST', body: JSON.stringify({ recipient_resolution_reference: reference }) });
export type TicketTransfer = { id: number; ticket_id: number; direction: 'incoming' | 'outgoing'; status: string; recipient_identifier: string; event_title: string; ticket_tier_name: string; starts_at: string; expires_at: string | null; created_at: string };
export const listTransfers = () => apiJson<TicketTransfer[]>('/me/ticket-transfers?direction=all');
export const actOnTransfer = (id: number, action: 'accept' | 'decline' | 'cancel') => apiJson(`/ticket-transfers/${id}/${action}`, { method: 'POST' });

export type WebNotification = { id: number; title: string; body: string; is_read: boolean; read_at: string | null; route_key: string | null; route_params: Record<string, string | number>; created_at: string };
export const listNotifications = () => apiJson<{ items: WebNotification[]; next_cursor: number | null }>('/me/notifications');
export const markNotificationRead = (id: number) => apiJson<WebNotification>(`/me/notifications/${id}/read`, { method: 'POST' });
export const markAllNotificationsRead = () => apiJson<{ updated_count: number }>('/me/notifications/read-all', { method: 'POST' });

export type AccountProfile = { id: number; email: string; full_name: string; is_active: boolean; is_verified: boolean; email_verified_at: string | null; requires_email_verification: boolean; my_tickets_count: number; my_events_count: number; staff_events_count: number; creator_age_identity_verification_status: 'pending' | 'verified' | 'revoked' };
export const getAccount = () => apiJson<AccountProfile>('/account/profile');
export const updateProfile = (fullName: string) => apiJson('/account/profile', { method: 'PATCH', body: JSON.stringify({ full_name: fullName }) });
export const changePassword = (currentPassword: string, newPassword: string) => apiJson<{ success: boolean; reauthentication_required: boolean }>('/account/change-password', { method: 'POST', body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }) });

export type OrganizerEvent = { id: number; title: string; cover_image_url: string | null; venue_name: string | null; city: string | null; start_at: string; end_at: string; status: string; approval_status: string; is_publicly_visible: boolean; visibility_state: string | null; total_ticket_types: number; total_quantity: number; sold_count: number; gross_revenue: number; created_at: string; updated_at: string };
export type OrganizerEventDetail = OrganizerEvent & { short_description: string | null; long_description: string | null; category: string | null; doors_open_at: string | null; sales_start_at: string | null; sales_end_at: string | null; timezone: string; visibility: string; venue_id: number | null; venue_address_text: string | null; custom_venue_name: string | null; custom_address_text: string | null; latitude: string | null; longitude: string | null; is_location_pinned: boolean; ticket_tiers: Array<{ id: number; name: string; description: string | null; price_amount: string; currency: string; quantity_total: number; min_per_order: number; max_per_order: number; is_active: boolean }> };
export const listMyEvents = () => apiJson<OrganizerEvent[]>('/events/organizer/events');
export const getMyEvent = (id: number) => apiJson<OrganizerEventDetail>(`/events/organizer/events/${id}`);
export const getEventDashboard = (id: number) => apiJson<{ tickets_sold: number; gross_revenue: number; attendees_admitted: number; attendees_remaining: number; total_ticket_capacity: number }>(`/events/${id}/dashboard`);
export const updateMyEvent = (id: number, payload: Record<string, unknown>) => apiJson<OrganizerEventDetail>(`/events/organizer/events/${id}`, { method: 'PATCH', body: JSON.stringify(payload) });
export const publishMyEvent = (id: number) => apiJson<OrganizerEventDetail>(`/events/organizer/events/${id}/publish`, { method: 'POST' });
export const unpublishMyEvent = (id: number) => apiJson<OrganizerEventDetail>(`/events/organizer/events/${id}/unpublish`, { method: 'POST' });
export const uploadCover = (id: number, file: File) => { const body = new FormData(); body.append('file', file); return apiJson<{ url: string }>(`/events/${id}/cover-image`, { method: 'POST', body }); };

export type CreateEventInput = { title: string; short_description?: string; start_at: string; end_at: string; doors_open_at?: string | null; sales_start_at?: string | null; sales_end_at?: string | null; timezone: string; custom_venue_name: string; custom_address_text?: string; ticket_tiers: Array<{ name: string; price_amount: string; currency: string; quantity_total: number; min_per_order: number; max_per_order: number }> };
export const createEvent = (payload: CreateEventInput) => apiJson<{ id: number }>('/events', { method: 'POST', body: JSON.stringify(payload) });
export const rescheduleEvent = (id: number, payload: Record<string, unknown>) => apiJson(`/events/organizer/events/${id}/reschedule`, { method: 'POST', body: JSON.stringify(payload) });
