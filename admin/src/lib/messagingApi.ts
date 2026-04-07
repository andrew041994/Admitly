import { apiRequest } from './apiClient';

export interface MessageLog {
  id: number;
  template_type: string;
  channel: string;
  status: string;
  provider_status: string | null;
  created_at: string;
  is_manual_resend: boolean;
}

export async function fetchEventMessages(eventId: number) {
  const response = await apiRequest(`/events/${eventId}/messages`);
  return (await response.json()) as MessageLog[];
}

export async function sendEventBroadcast(eventId: number, payload: { subject: string; body: string; include_email: boolean; include_push: boolean }) {
  const response = await apiRequest(`/events/${eventId}/messages/broadcast`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  return (await response.json()) as { success: boolean; attempted_recipients: number; sent_attempts: number };
}
