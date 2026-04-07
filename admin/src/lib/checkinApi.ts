import { apiRequest } from './apiClient';

export interface CheckInValidationResponse {
  valid: boolean;
  code: string;
  message: string;
  ticket_id: number | null;
  ticket_code: string | null;
  event_id: number;
  checked_in_at: string | null;
}

export interface CheckInResponse {
  success: boolean;
  code: string | null;
  ticket_id: number | null;
  event_id: number;
  status: string | null;
  checked_in_at: string | null;
  checked_in_by_user_id: number | null;
  message: string;
}

export interface CheckInActivityItem {
  id: number;
  ticket_id: number | null;
  event_id: number;
  actor_user_id: number | null;
  attempted_at: string;
  result_code: string;
  reason_code: string | null;
  reason_message: string | null;
  method: string | null;
  source: string | null;
  notes: string | null;
}

export async function validateEventTicket(eventId: number, lookup: string) {
  const response = await apiRequest(`/events/${eventId}/check-in/validate`, {
    method: 'POST',
    body: JSON.stringify({ ticket_code: lookup, qr_payload: lookup }),
  });
  return (await response.json()) as CheckInValidationResponse;
}

export async function checkInEventTicket(eventId: number, lookup: string, method: 'qr' | 'manual') {
  const response = await apiRequest(`/events/${eventId}/check-in/confirm`, {
    method: 'POST',
    body: JSON.stringify({ ticket_code: lookup, qr_payload: lookup, method }),
  });
  return (await response.json()) as CheckInResponse;
}

export async function overrideEventCheckIn(
  eventId: number,
  lookup: string,
  admit: boolean,
  notes: string,
) {
  const response = await apiRequest(`/events/${eventId}/check-in/override`, {
    method: 'POST',
    body: JSON.stringify({ ticket_code: lookup, qr_payload: lookup, admit, notes }),
  });
  return (await response.json()) as CheckInResponse;
}

export async function fetchEventCheckInActivity(eventId: number, limit = 20) {
  const response = await apiRequest(`/events/${eventId}/check-in/activity?limit=${limit}`);
  return (await response.json()) as CheckInActivityItem[];
}
