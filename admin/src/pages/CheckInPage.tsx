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
  const [scanLookup, setScanLookup] = useState('');
  const [manualDigits, setManualDigits] = useState('');
  const [manualCodeError, setManualCodeError] = useState<string | null>(null);
  const [overrideNotes, setOverrideNotes] = useState('');
  const [validation, setValidation] = useState<CheckInValidationResponse | null>(null);
  const [result, setResult] = useState<CheckInResponse | null>(null);
  const [activity, setActivity] = useState<CheckInActivityItem[]>([]);
  const [loading, setLoading] = useState(false);
  const parsedEventId = useMemo(() => Number(eventId), [eventId]);

  const scanLookupValue = scanLookup.trim();
  const manualLookupValue = `ADM-${manualDigits}`;
  const hasEvent = Number.isFinite(parsedEventId) && parsedEventId > 0;
  const scanReady = hasEvent && scanLookupValue.length > 0;

  function updateManualDigits(value: string) {
    const digitsOnly = value.replace(/\D/g, '').slice(0, 6);
    setManualDigits(digitsOnly);
    setManualCodeError(/\D/.test(value) ? 'Check-in code must be 6 numbers.' : null);
  }

  function validateManualDigits() {
    if (manualDigits.length !== 6) {
      setManualCodeError('Enter the 6-digit check-in code.');
      return false;
    }
    setManualCodeError(null);
    return true;
  }

  async function onValidate(e: FormEvent) {
    e.preventDefault();
    if (!scanReady) return;
    setLoading(true);
    try {
      setValidation(await validateEventTicket(parsedEventId, scanLookupValue));
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
    const lookup = method === 'manual' ? manualLookupValue : scanLookupValue;
    if (method === 'manual' ? !validateManualDigits() : !scanReady) return;
    setLoading(true);
    try {
      setResult(await checkInEventTicket(parsedEventId, lookup, method));
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
    if (!scanReady || !overrideNotes.trim()) return;
    setLoading(true);
    try {
      setResult(await overrideEventCheckIn(parsedEventId, scanLookupValue, admit, overrideNotes.trim()));
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
          placeholder="Scan payload or secure ticket code"
          value={scanLookup}
          onChange={(e) => setScanLookup(e.target.value)}
          required
        />
        <button type="submit" disabled={!scanReady || loading}>
          Validate Scan
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
        <button onClick={() => onConfirm('qr')} disabled={!scanReady || loading}>
          Admit QR
        </button>
      </div>

      <div className="manual-checkin-section">
        <label className="manual-checkin-label" htmlFor="manual-checkin-digits">Manual check-in code</label>
        <div className="manual-code-input">
          <span className="manual-code-prefix">ADM -</span>
          <input
            id="manual-checkin-digits"
            type="text"
            inputMode="numeric"
            pattern="\d{6}"
            maxLength={6}
            placeholder="123456"
            value={manualDigits}
            onChange={(e) => updateManualDigits(e.target.value)}
          />
        </div>
        {manualCodeError && <p className="error-text">{manualCodeError}</p>}
        <button onClick={() => onConfirm('manual')} disabled={!hasEvent || loading}>
          Admit Manual
        </button>
      </div>

      <div className="inline-form">
        <input
          type="text"
          placeholder="Override note (required)"
          value={overrideNotes}
          onChange={(e) => setOverrideNotes(e.target.value)}
        />
        <button onClick={() => onOverride(true)} disabled={!scanReady || !overrideNotes.trim() || loading}>
          Override Admit
        </button>
        <button onClick={() => onOverride(false)} disabled={!scanReady || !overrideNotes.trim() || loading}>
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
