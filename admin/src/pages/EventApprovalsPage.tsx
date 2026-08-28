import { Fragment, useCallback, useEffect, useRef, useState } from 'react';
import { ApiError } from '../lib/apiClient';
import {
  AdminCreatorVerificationDocument,
  AdminPendingEvent,
  CreatorVerificationHistory,
  approveEvent,
  getCreatorAgeIdentityVerificationHistory,
  getCreatorVerificationDocumentContent,
  listCreatorVerificationDocuments,
  listPendingEventsForApproval,
  recordCreatorAgeIdentityVerification,
  rejectCreatorVerificationDocument,
  retryCreatorVerificationDocumentCleanup,
  revokeCreatorAgeIdentityVerification,
  verifyCreatorVerificationDocument,
} from '../lib/eventApprovalsApi';

function formatDate(value: string | null) {
  return value ? new Date(value).toLocaleString() : '—';
}

export function EventApprovalsPage() {
  const [events, setEvents] = useState<AdminPendingEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [approvingId, setApprovingId] = useState<number | null>(null);
  const [verifyingId, setVerifyingId] = useState<number | null>(null);
  const [verificationNotes, setVerificationNotes] = useState<Record<number, string>>({});
  const [revocationReasons, setRevocationReasons] = useState<Record<number, string>>({});
  const [history, setHistory] = useState<Record<number, CreatorVerificationHistory[]>>({});
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [documents, setDocuments] = useState<AdminCreatorVerificationDocument[]>([]);
  const [cleanupDocuments, setCleanupDocuments] = useState<AdminCreatorVerificationDocument[]>([]);
  const [documentNotes, setDocumentNotes] = useState<Record<number, string>>({});
  const [documentRejectionReasons, setDocumentRejectionReasons] = useState<Record<number, string>>({});
  const [documentActionId, setDocumentActionId] = useState<number | null>(null);
  const [viewer, setViewer] = useState<{ documentId: number; url: string } | null>(null);
  const viewerUrlRef = useRef<string | null>(null);

  const clearViewer = useCallback(() => {
    if (viewerUrlRef.current) URL.revokeObjectURL(viewerUrlRef.current);
    viewerUrlRef.current = null;
    setViewer(null);
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [pendingEvents, pendingDocuments, pendingCleanup] = await Promise.all([
        listPendingEventsForApproval(),
        listCreatorVerificationDocuments('pending'),
        listCreatorVerificationDocuments('cleanup_required'),
      ]);
      setEvents(pendingEvents);
      setDocuments(pendingDocuments);
      setCleanupDocuments(pendingCleanup);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to load pending event approvals.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => () => {
    if (viewerUrlRef.current) URL.revokeObjectURL(viewerUrlRef.current);
  }, []);

  const viewDocument = async (documentId: number) => {
    if (viewer?.documentId === documentId) { clearViewer(); return; }
    setDocumentActionId(documentId); setError(null);
    try {
      const blob = await getCreatorVerificationDocumentContent(documentId);
      if (!['image/jpeg', 'image/png', 'image/webp'].includes(blob.type)) throw new Error('Unexpected image type.');
      clearViewer();
      const url = URL.createObjectURL(blob);
      viewerUrlRef.current = url;
      setViewer({ documentId, url });
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to load the private verification image.');
    } finally { setDocumentActionId(null); }
  };

  const verifyDocument = async (document: AdminCreatorVerificationDocument) => {
    if (viewer?.documentId !== document.id) { setError('Open and review this private image before recording verification.'); return; }
    if (!window.confirm('Confirm that the private document was reviewed and this creator is at least 18. The backend will record verification and immediately attempt to delete the temporary image.')) return;
    setDocumentActionId(document.id); setError(null); setSuccess(null);
    try {
      await verifyCreatorVerificationDocument(document.id, documentNotes[document.id]);
      clearViewer();
      setSuccess('Creator account verified. Temporary document cleanup was requested by the backend.');
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to verify the creator account.');
    } finally { setDocumentActionId(null); }
  };

  const rejectDocument = async (document: AdminCreatorVerificationDocument) => {
    if (viewer?.documentId !== document.id) { setError('Open and review this private image before rejecting the submission.'); return; }
    const reason = (documentRejectionReasons[document.id] ?? '').trim();
    if (!reason) { setError('A safe rejection reason is required. Do not include ID numbers or image details.'); return; }
    if (!window.confirm('Reject this verification submission? The backend will record the result and immediately attempt to delete the temporary image.')) return;
    setDocumentActionId(document.id); setError(null); setSuccess(null);
    try {
      await rejectCreatorVerificationDocument(document.id, reason);
      clearViewer();
      setSuccess('Verification rejected. The creator may submit a new ID after cleanup completes.');
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to reject the verification submission.');
    } finally { setDocumentActionId(null); }
  };

  const retryCleanup = async (documentId: number) => {
    setDocumentActionId(documentId); setError(null); setSuccess(null);
    try {
      const result = await retryCreatorVerificationDocumentCleanup(documentId);
      setSuccess(result.success ? 'Temporary document cleanup completed.' : 'Cleanup is still required; retry safely later.');
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to retry temporary document cleanup.');
    } finally { setDocumentActionId(null); }
  };

  const onApprove = async (eventId: number) => {
    setApprovingId(eventId);
    setError(null);
    setSuccess(null);
    try {
      const approved = await approveEvent(eventId);
      setSuccess(`Approved \"${approved.title}\".`);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to approve event.');
    } finally {
      setApprovingId(null);
    }
  };

  const onRecordVerification = async (event: AdminPendingEvent) => {
    const confirmed = window.confirm(
      'Confirm that authorized verification evidence was reviewed and this event creator is at least 18. Do not put document details into the audit note.',
    );
    if (!confirmed) return;

    setVerifyingId(event.id);
    setError(null);
    setSuccess(null);
    try {
      await recordCreatorAgeIdentityVerification(event.id, event.creator_user_id, verificationNotes[event.id]);
      setSuccess(`Verified creator account #${event.creator_user_id}. Future events from this account reuse this verification.`);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to record creator verification.');
    } finally {
      setVerifyingId(null);
    }
  };

  const onRevokeVerification = async (event: AdminPendingEvent) => {
    const reason = (revocationReasons[event.id] ?? '').trim();
    if (!reason) { setError('A revocation reason is required.'); return; }
    const confirmed = window.confirm(
      'Revoke this creator account verification? Future event approvals will be blocked. Already-approved events remain active and must be reviewed separately.',
    );
    if (!confirmed) return;
    setVerifyingId(event.id); setError(null); setSuccess(null);
    try {
      await revokeCreatorAgeIdentityVerification(event.id, event.creator_user_id, reason);
      setSuccess(`Revoked verification for creator account #${event.creator_user_id}. Existing approved events were not changed.`);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to revoke creator verification.');
    } finally { setVerifyingId(null); }
  };

  const inspect = async (event: AdminPendingEvent) => {
    if (expandedId === event.id) { setExpandedId(null); return; }
    setExpandedId(event.id);
    try {
      const rows = await getCreatorAgeIdentityVerificationHistory(event.creator_user_id);
      setHistory((current) => ({ ...current, [event.creator_user_id]: rows }));
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to load verification history.');
    }
  };

  return (
    <section className="support-page" aria-labelledby="event-approval-title">
      <header>
        <h2 id="event-approval-title">Event Approvals</h2>
        <p className="muted-text">Review temporary government-ID submissions only when verification or justified reverification is required. Never copy an image, date of birth, or ID number into notes.</p>
      </header>

      <div className="card">
        <button type="button" onClick={() => void load()} disabled={loading}>
          {loading ? 'Refreshing…' : 'Refresh verification and events'}
        </button>
        {success ? <p className="success-text">{success}</p> : null}
        {error ? <p className="error-text">{error}</p> : null}

        <section className="verification-review" aria-labelledby="verification-documents-heading">
          <h3 id="verification-documents-heading">Pending creator verification documents</h3>
          <p className="muted-text">Images load privately through the authenticated backend and remain only in browser memory while open.</p>
          {documents.length ? documents.map((document) => (
            <article className="verification-document-card" key={document.id}>
              <div className="verification-document-summary">
                <div><strong>Creator account #{document.user_id}</strong><br /><span className="muted-text">Submitted {formatDate(document.uploaded_at)}</span></div>
                <button type="button" onClick={() => void viewDocument(document.id)} disabled={documentActionId === document.id}>
                  {viewer?.documentId === document.id ? 'Close private image' : documentActionId === document.id ? 'Loading…' : 'Review private image'}
                </button>
              </div>
              {viewer?.documentId === document.id ? (
                <div className="verification-document-viewer">
                  <img src={viewer.url} alt="Government-issued ID submitted for creator age and identity review" />
                  <p className="muted-text">Do not download, copy, photograph, or transcribe document details.</p>
                </div>
              ) : null}
              <div className="verification-review-actions">
                <label>Optional safe verification note (no document details)<input maxLength={1000} value={documentNotes[document.id] ?? ''} onChange={(event) => setDocumentNotes((current) => ({ ...current, [document.id]: event.target.value }))} /></label>
                <button type="button" disabled={documentActionId === document.id} onClick={() => void verifyDocument(document)}>Verify creator as 18+</button>
                <label>Required rejection reason (no document details)<input maxLength={1000} value={documentRejectionReasons[document.id] ?? ''} onChange={(event) => setDocumentRejectionReasons((current) => ({ ...current, [document.id]: event.target.value }))} /></label>
                <button type="button" className="danger-button" disabled={documentActionId === document.id} onClick={() => void rejectDocument(document)}>Reject verification</button>
              </div>
            </article>
          )) : <p>No temporary documents are awaiting review.</p>}
        </section>

        {cleanupDocuments.length ? <section className="cleanup-review" aria-labelledby="cleanup-heading">
          <h3 id="cleanup-heading">Temporary documents requiring cleanup</h3>
          <p className="muted-text">These records indicate that immediate storage deletion did not complete. Retry is idempotent.</p>
          {cleanupDocuments.map((document) => <div className="cleanup-row" key={document.id}>
            <span>Creator account #{document.user_id} · {document.cleanup_attempts} cleanup attempt(s)</span>
            <button type="button" disabled={documentActionId === document.id} onClick={() => void retryCleanup(document.id)}>{documentActionId === document.id ? 'Retrying…' : 'Retry cleanup'}</button>
          </div>)}
        </section> : null}

        <h3>Events awaiting approval</h3>

        <table className="finance-table">
          <thead>
            <tr>
              <th>Title</th>
              <th>Organizer</th>
              <th>Start</th>
              <th>Venue</th>
              <th>Status</th>
              <th>Creator verification</th>
              <th>Created</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {events.map((event) => (
              <Fragment key={event.id}>
                <tr>
                  <td>{event.title}</td>
                  <td>{event.organizer_name ?? '—'}</td>
                  <td>{formatDate(event.start_at)}</td>
                  <td>{event.venue_name ?? event.custom_venue_name ?? '—'}</td>
                  <td>{event.approval_status}</td>
                  <td>{event.creator_account_verification_status}{event.creator_verification_manual_review_required ? ' · review existing event' : ''}</td>
                  <td>{formatDate(event.created_at)}</td>
                  <td>
                    <button type="button" onClick={() => void inspect(event)}>
                      {expandedId === event.id ? 'Hide' : 'Inspect'}
                    </button>{' '}
                    <button
                      type="button"
                      onClick={() => void onApprove(event.id)}
                      disabled={
                        approvingId === event.id
                        || event.approval_status === 'approved'
                        || event.creator_account_verification_status !== 'verified'
                      }
                    >
                      {event.approval_status === 'approved' ? 'Approved' : approvingId === event.id ? 'Approving…' : 'Approve'}
                    </button>
                  </td>
                </tr>
                {expandedId === event.id ? (
                  <tr>
                    <td colSpan={8}>
                      <strong>Slug:</strong> {event.slug} · <strong>Published:</strong> {formatDate(event.published_at)} ·{' '}
                      <strong>Event status:</strong> {event.status} · <strong>Creator user:</strong> #{event.creator_user_id}
                      <div>
                        <strong>Account verified at:</strong> {formatDate(event.creator_account_verified_at)} · <strong>Verifier:</strong> {event.creator_account_verified_by_user_id ? `#${event.creator_account_verified_by_user_id}` : '—'}
                      </div>
                      <div><strong>Event approval snapshot recorded:</strong> {formatDate(event.creator_age_identity_verification_snapshot_at)}</div>
                      {event.creator_account_revoked_at ? <p><strong>Revoked:</strong> {formatDate(event.creator_account_revoked_at)} · {event.creator_account_revocation_reason}</p> : null}
                      {event.creator_account_verification_status !== 'verified' && documents.some((document) => document.user_id === event.creator_user_id) ? (
                        <p className="verification-status">A private document is pending for this creator. Review and act on it in the verification section above.</p>
                      ) : event.creator_account_verification_status !== 'verified' ? (
                        <div className="form-grid">
                          <label>
                            Optional safe audit note (no ID number or image)
                            <input
                              value={verificationNotes[event.id] ?? ''}
                              maxLength={1000}
                              onChange={(changeEvent) => setVerificationNotes((current) => ({
                                ...current,
                                [event.id]: changeEvent.target.value,
                              }))}
                            />
                          </label>
                          <button
                            type="button"
                            disabled={verifyingId === event.id}
                            onClick={() => void onRecordVerification(event)}
                          >
                            {verifyingId === event.id ? 'Recording…' : 'Verify creator account as 18+'}
                          </button>
                        </div>
                      ) : <div className="form-grid"><label>Required revocation reason<input value={revocationReasons[event.id] ?? ''} maxLength={1000} onChange={(changeEvent) => setRevocationReasons((current) => ({ ...current, [event.id]: changeEvent.target.value }))} /></label><button type="button" className="danger-button" disabled={verifyingId === event.id} onClick={() => void onRevokeVerification(event)}>Revoke account verification</button></div>}
                      <h3>Verification history</h3>
                      {(history[event.creator_user_id] ?? []).length ? <ul>{history[event.creator_user_id].map((row) => <li key={row.id}>{formatDate(row.created_at)} · {row.previous_status} → {row.new_status} by admin #{row.actor_user_id}{row.note ? ` · ${row.note}` : ''}</li>)}</ul> : <p>No recorded account verification history.</p>}
                    </td>
                  </tr>
                ) : null}
              </Fragment>
            ))}
            {!loading && events.length === 0 ? (
              <tr>
                <td colSpan={8}>No events currently require approval or creator verification.</td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </section>
  );
}
