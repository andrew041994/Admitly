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
  creator_age_identity_verification_snapshot_at: string | null;
  creator_account_verification_status: string;
  creator_account_verified_at: string | null;
  creator_account_verified_by_user_id: number | null;
  creator_account_revoked_at: string | null;
  creator_account_revoked_by_user_id: number | null;
  creator_account_verification_note: string | null;
  creator_account_revocation_reason: string | null;
  creator_verification_manual_review_required: boolean;
};

export type CreatorVerificationHistory = {
  id: number;
  user_id: number;
  action: string;
  actor_user_id: number;
  previous_status: string;
  new_status: string;
  note: string | null;
  created_at: string;
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
  creatorUserId: number,
  note?: string,
): Promise<AdminPendingEvent> {
  const response = await apiRequest(`/events/admin/creators/${creatorUserId}/age-identity-verification?event_id=${eventId}`, {
    method: 'POST',
    body: JSON.stringify({ note: note?.trim() || null }),
  });
  return (await response.json()) as AdminPendingEvent;
}

export async function revokeCreatorAgeIdentityVerification(
  eventId: number,
  creatorUserId: number,
  reason: string,
): Promise<AdminPendingEvent> {
  const response = await apiRequest(`/events/admin/creators/${creatorUserId}/age-identity-verification/revoke?event_id=${eventId}`, {
    method: 'POST',
    body: JSON.stringify({ reason: reason.trim() }),
  });
  return (await response.json()) as AdminPendingEvent;
}

export async function getCreatorAgeIdentityVerificationHistory(
  creatorUserId: number,
): Promise<CreatorVerificationHistory[]> {
  const response = await apiRequest(`/events/admin/creators/${creatorUserId}/age-identity-verification/history`);
  return (await response.json()) as CreatorVerificationHistory[];
}
