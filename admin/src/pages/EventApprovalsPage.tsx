import { Fragment, useCallback, useEffect, useState } from 'react';
import { ApiError } from '../lib/apiClient';
import {
  AdminPendingEvent,
  CreatorVerificationHistory,
  approveEvent,
  getCreatorAgeIdentityVerificationHistory,
  listPendingEventsForApproval,
  recordCreatorAgeIdentityVerification,
  revokeCreatorAgeIdentityVerification,
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

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setEvents(await listPendingEventsForApproval());
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to load pending event approvals.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

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
      'Confirm that you reviewed a valid government-issued ID, verified this event creator is at least 18, and deleted the ID image from the verification email account. Do not store the image or ID number in Admitly.',
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
        <p className="muted-text">Check the creator account first. Review emailed government ID only when verification is required or justified reverification is necessary. Never copy the ID image or number into Admitly.</p>
      </header>

      <div className="card">
        <button type="button" onClick={() => void load()} disabled={loading}>
          {loading ? 'Refreshing…' : 'Refresh pending events'}
        </button>
        {success ? <p className="success-text">{success}</p> : null}
        {error ? <p className="error-text">{error}</p> : null}

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
                      {event.creator_account_verification_status !== 'verified' ? (
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
