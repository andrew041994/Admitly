import { apiRequest } from './apiClient';

export type AdminPendingEvent = {
  id: number;
  title: string;
  slug: string;
  organizer_name: string | null;
  start_at: string;
  venue_name: string | null;
  custom_venue_name: string | null;
  approval_status: string;
  status: string;
  created_at: string;
  published_at: string | null;
};

function adminHeaders(userId: number) {
  return { 'X-User-Id': String(userId) };
}

export async function listPendingEventsForApproval(userId: number): Promise<AdminPendingEvent[]> {
  const response = await apiRequest('/events/admin/pending-approval', {
    headers: adminHeaders(userId),
  });
  return (await response.json()) as AdminPendingEvent[];
}

export async function approveEvent(userId: number, eventId: number): Promise<AdminPendingEvent> {
  const response = await apiRequest(`/events/admin/${eventId}/approve`, {
    method: 'POST',
    headers: adminHeaders(userId),
  });
  return (await response.json()) as AdminPendingEvent;
}
