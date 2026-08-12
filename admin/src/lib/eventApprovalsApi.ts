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
  creator_user_id: number;
  creator_age_identity_verification_status: string;
  creator_age_identity_verified_user_id: number | null;
  creator_age_identity_verified_by_user_id: number | null;
  creator_age_identity_verified_at: string | null;
};

export async function listPendingEventsForApproval(): Promise<AdminPendingEvent[]> {
  const response = await apiRequest('/events/admin/pending-approval');
  return (await response.json()) as AdminPendingEvent[];
}

export async function approveEvent(eventId: number): Promise<AdminPendingEvent> {
  const response = await apiRequest(`/events/admin/${eventId}/approve`, {
    method: 'POST',
  });
  return (await response.json()) as AdminPendingEvent;
}

export async function recordCreatorAgeIdentityVerification(
  eventId: number,
  note?: string,
): Promise<AdminPendingEvent> {
  const response = await apiRequest(`/events/admin/${eventId}/creator-age-identity-verification`, {
    method: 'POST',
    body: JSON.stringify({ note: note?.trim() || null }),
  });
  return (await response.json()) as AdminPendingEvent;
}
