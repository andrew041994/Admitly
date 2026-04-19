import { Fragment, useCallback, useEffect, useState } from 'react';
import { ApiError } from '../lib/apiClient';
import { AdminPendingEvent, approveEvent, listPendingEventsForApproval } from '../lib/eventApprovalsApi';

const adminUserId = 1;

function formatDate(value: string | null) {
  return value ? new Date(value).toLocaleString() : '—';
}

export function EventApprovalsPage() {
  const [events, setEvents] = useState<AdminPendingEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [approvingId, setApprovingId] = useState<number | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setEvents(await listPendingEventsForApproval(adminUserId));
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
      const approved = await approveEvent(adminUserId, eventId);
      setSuccess(`Approved \"${approved.title}\".`);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to approve event.');
    } finally {
      setApprovingId(null);
    }
  };

  return (
    <section className="support-page" aria-labelledby="event-approval-title">
      <header>
        <h2 id="event-approval-title">Event Approvals</h2>
        <p className="muted-text">Review events pending approval and approve them for discovery.</p>
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
                  <td>{formatDate(event.created_at)}</td>
                  <td>
                    <button type="button" onClick={() => setExpandedId(expandedId === event.id ? null : event.id)}>
                      {expandedId === event.id ? 'Hide' : 'Inspect'}
                    </button>{' '}
                    <button
                      type="button"
                      onClick={() => void onApprove(event.id)}
                      disabled={approvingId === event.id}
                    >
                      {approvingId === event.id ? 'Approving…' : 'Approve'}
                    </button>
                  </td>
                </tr>
                {expandedId === event.id ? (
                  <tr>
                    <td colSpan={7}>
                      <strong>Slug:</strong> {event.slug} · <strong>Published:</strong> {formatDate(event.published_at)} ·{' '}
                      <strong>Event status:</strong> {event.status}
                    </td>
                  </tr>
                ) : null}
              </Fragment>
            ))}
            {!loading && events.length === 0 ? (
              <tr>
                <td colSpan={7}>No events are currently pending approval.</td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </section>
  );
}
