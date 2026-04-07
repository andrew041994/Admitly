import { FormEvent, useMemo, useState } from 'react';
import { ApiError } from '../lib/apiClient';
import {
  CheckInActivityItem,
  CheckInResponse,
  CheckInValidationResponse,
  checkInEventTicket,
  fetchEventCheckInActivity,
  overrideEventCheckIn,
  validateEventTicket,
} from '../lib/checkinApi';

export function CheckInPage() {
  const [eventId, setEventId] = useState('');
  const [lookup, setLookup] = useState('');
  const [overrideNotes, setOverrideNotes] = useState('');
  const [validation, setValidation] = useState<CheckInValidationResponse | null>(null);
  const [result, setResult] = useState<CheckInResponse | null>(null);
  const [activity, setActivity] = useState<CheckInActivityItem[]>([]);
  const [loading, setLoading] = useState(false);
  const parsedEventId = useMemo(() => Number(eventId), [eventId]);

  const ready = Number.isFinite(parsedEventId) && parsedEventId > 0 && lookup.trim().length > 0;

  async function onValidate(e: FormEvent) {
    e.preventDefault();
    if (!ready) return;
    setLoading(true);
    try {
      setValidation(await validateEventTicket(parsedEventId, lookup.trim()));
      setResult(null);
    } catch (error) {
      setValidation(null);
      setResult({
        success: false,
        code: 'error',
        ticket_id: null,
        event_id: parsedEventId,
        status: null,
        checked_in_at: null,
        checked_in_by_user_id: null,
        message: error instanceof ApiError ? error.detail : 'Validation failed.',
      });
    } finally {
      setLoading(false);
    }
  }

  async function onConfirm(method: 'qr' | 'manual') {
    if (!ready) return;
    setLoading(true);
    try {
      setResult(await checkInEventTicket(parsedEventId, lookup.trim(), method));
      setValidation(null);
      setActivity(await fetchEventCheckInActivity(parsedEventId, 20));
    } catch (error) {
      setResult({
        success: false,
        code: 'error',
        ticket_id: null,
        event_id: parsedEventId,
        status: null,
        checked_in_at: null,
        checked_in_by_user_id: null,
        message: error instanceof ApiError ? error.detail : 'Check-in failed.',
      });
    } finally {
      setLoading(false);
    }
  }

  async function onOverride(admit: boolean) {
    if (!ready || !overrideNotes.trim()) return;
    setLoading(true);
    try {
      setResult(await overrideEventCheckIn(parsedEventId, lookup.trim(), admit, overrideNotes.trim()));
      setValidation(null);
      setActivity(await fetchEventCheckInActivity(parsedEventId, 20));
    } catch (error) {
      setResult({
        success: false,
        code: 'error',
        ticket_id: null,
        event_id: parsedEventId,
        status: null,
        checked_in_at: null,
        checked_in_by_user_id: null,
        message: error instanceof ApiError ? error.detail : 'Override failed.',
      });
    } finally {
      setLoading(false);
    }
  }

  async function onRefreshActivity() {
    if (!Number.isFinite(parsedEventId) || parsedEventId <= 0) return;
    setActivity(await fetchEventCheckInActivity(parsedEventId, 20));
  }

  return (
    <section className="card">
      <h2>Door Check-in</h2>
      <p className="muted">Validate ticket codes, admit once, and review recent scan activity.</p>

      <form className="inline-form" onSubmit={onValidate}>
        <input
          type="number"
          placeholder="Event ID"
          value={eventId}
          onChange={(e) => setEventId(e.target.value)}
          min={1}
          required
        />
        <input
          type="text"
          placeholder="Scan payload or ticket code"
          value={lookup}
          onChange={(e) => setLookup(e.target.value)}
          required
        />
        <button type="submit" disabled={!ready || loading}>
          Validate
        </button>
      </form>

      {validation && (
        <div className={`result-panel ${validation.valid ? 'ok' : 'bad'}`}>
          <strong>{validation.code}</strong> — {validation.message}
        </div>
      )}
      {result && (
        <div className={`result-panel ${result.success ? 'ok' : 'bad'}`}>
          <strong>{result.code ?? 'result'}</strong> — {result.message}
        </div>
      )}

      <div className="inline-form">
        <button onClick={() => onConfirm('qr')} disabled={!ready || loading}>
          Admit (QR)
        </button>
        <button onClick={() => onConfirm('manual')} disabled={!ready || loading}>
          Admit (Manual)
        </button>
      </div>

      <div className="inline-form">
        <input
          type="text"
          placeholder="Override note (required)"
          value={overrideNotes}
          onChange={(e) => setOverrideNotes(e.target.value)}
        />
        <button onClick={() => onOverride(true)} disabled={!ready || !overrideNotes.trim() || loading}>
          Override Admit
        </button>
        <button onClick={() => onOverride(false)} disabled={!ready || !overrideNotes.trim() || loading}>
          Override Deny
        </button>
      </div>

      <div className="section-header">
        <h3>Recent Activity</h3>
        <button onClick={onRefreshActivity} disabled={!parsedEventId || loading}>
          Refresh
        </button>
      </div>
      <ul className="timeline-list">
        {activity.map((row) => (
          <li key={row.id}>
            <strong>{row.result_code}</strong> ticket:{' '}
            {row.ticket_id ?? 'n/a'} by user {row.actor_user_id ?? 'n/a'} at {new Date(row.attempted_at).toLocaleString()}
            {row.notes ? ` — ${row.notes}` : ''}
          </li>
        ))}
      </ul>
    </section>
  );
}
