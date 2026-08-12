import { Fragment, useCallback, useEffect, useState } from 'react';
import { ApiError } from '../lib/apiClient';
import {
  AdminPendingEvent,
  approveEvent,
  listPendingEventsForApproval,
  recordCreatorAgeIdentityVerification,
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
      await recordCreatorAgeIdentityVerification(event.id, verificationNotes[event.id]);
      setSuccess(`Recorded age and identity verification for "${event.title}".`);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to record creator verification.');
    } finally {
      setVerifyingId(null);
    }
  };

  return (
    <section className="support-page" aria-labelledby="event-approval-title">
      <header>
        <h2 id="event-approval-title">Event Approvals</h2>
        <p className="muted-text">Verify each creator is at least 18 from an emailed government ID before approval. Never copy the ID image or number into Admitly.</p>
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
                  <td>{event.creator_age_identity_verification_status}</td>
                  <td>{formatDate(event.created_at)}</td>
                  <td>
                    <button type="button" onClick={() => setExpandedId(expandedId === event.id ? null : event.id)}>
                      {expandedId === event.id ? 'Hide' : 'Inspect'}
                    </button>{' '}
                    <button
                      type="button"
                      onClick={() => void onApprove(event.id)}
                      disabled={
                        approvingId === event.id
                        || event.approval_status === 'approved'
                        || event.creator_age_identity_verification_status !== 'verified'
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
                        <strong>Verified at:</strong> {formatDate(event.creator_age_identity_verified_at)}
                      </div>
                      {event.creator_age_identity_verification_status !== 'verified' ? (
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
                            {verifyingId === event.id ? 'Recording…' : 'Record 18+ identity verification'}
                          </button>
                        </div>
                      ) : null}
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
