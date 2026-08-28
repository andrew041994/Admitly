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

export type AdminCreatorVerificationDocument = {
  id: number;
  user_id: number;
  account_verification_status: string;
  status: 'uploading' | 'pending' | 'reviewed' | 'deleted' | 'cleanup_required';
  review_outcome: string | null;
  uploaded_at: string | null;
  reviewed_at: string | null;
  reviewed_by_user_id: number | null;
  deleted_at: string | null;
  cleanup_required_at: string | null;
  cleanup_attempts: number;
  created_at: string;
  updated_at: string;
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

export async function listCreatorVerificationDocuments(
  status: 'pending' | 'cleanup_required',
): Promise<AdminCreatorVerificationDocument[]> {
  const response = await apiRequest(`/admin/creator-verification/documents?status=${status}`);
  return (await response.json()) as AdminCreatorVerificationDocument[];
}

export async function getCreatorVerificationDocumentContent(documentId: number): Promise<Blob> {
  const response = await apiRequest(`/admin/creator-verification/documents/${documentId}/content`);
  return response.blob();
}

export async function verifyCreatorVerificationDocument(
  documentId: number,
  note?: string,
): Promise<AdminCreatorVerificationDocument> {
  const response = await apiRequest(`/admin/creator-verification/documents/${documentId}/verify`, {
    method: 'POST',
    body: JSON.stringify({ note: note?.trim() || null }),
  });
  return (await response.json()) as AdminCreatorVerificationDocument;
}

export async function rejectCreatorVerificationDocument(
  documentId: number,
  reason: string,
): Promise<AdminCreatorVerificationDocument> {
  const response = await apiRequest(`/admin/creator-verification/documents/${documentId}/reject`, {
    method: 'POST',
    body: JSON.stringify({ reason: reason.trim() }),
  });
  return (await response.json()) as AdminCreatorVerificationDocument;
}

export async function retryCreatorVerificationDocumentCleanup(
  documentId: number,
): Promise<{ success: boolean; status: string }> {
  const response = await apiRequest(`/admin/creator-verification/documents/${documentId}/cleanup`, {
    method: 'POST',
  });
  return (await response.json()) as { success: boolean; status: string };
}
