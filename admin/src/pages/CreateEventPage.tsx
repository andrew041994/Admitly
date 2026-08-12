import { type FormEvent, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { useAuth } from '../auth/AuthContext';
import { createEvent } from '../lib/userApi';

function iso(value: string) { return new Date(value).toISOString(); }

export function CreateEventPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const creatorVerified = user?.creator_age_identity_verification_status === 'verified';
  const [form, setForm] = useState({
    title: '', description: '', start: '', end: '', venue: '', address: '',
    tier: 'General Admission', price: '0', quantity: '100',
  });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(null);
    try {
      const created = await createEvent({
        title: form.title,
        short_description: form.description,
        start_at: iso(form.start),
        end_at: iso(form.end),
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'America/Guyana',
        custom_venue_name: form.venue,
        custom_address_text: form.address,
        ticket_tiers: [{
          name: form.tier, price_amount: form.price, currency: 'GYD',
          quantity_total: Number(form.quantity), min_per_order: 1, max_per_order: 10,
        }],
      });
      navigate(`/my-events/${created.id}`, { replace: true });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to create event.');
    } finally { setBusy(false); }
  }

  return <section className="user-page narrow-page">
    <p className="eyebrow">Creator workspace</p><h1>Create Event</h1>
    <div className="verification-notice">
      <strong>{creatorVerified ? 'Creator account verified' : 'Verification required before approval'}</strong>
      <p>{creatorVerified
        ? 'Your age has already been verified. You do not need to submit ID again unless Admitly asks you to reverify. This event still requires normal review and approval.'
        : 'Event creators must be 18+. Government ID is reviewed separately by email and is not uploaded through this website or stored in the application.'}</p>
    </div>
    <form className="panel web-form two-column-form" onSubmit={submit}>
      {error ? <p className="form-error form-wide">{error}</p> : null}
      <label className="form-wide">Event title<input value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} required /></label>
      <label className="form-wide">Short description<textarea value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} /></label>
      <label>Starts<input type="datetime-local" value={form.start} onChange={(event) => setForm({ ...form, start: event.target.value })} required /></label>
      <label>Ends<input type="datetime-local" value={form.end} onChange={(event) => setForm({ ...form, end: event.target.value })} required /></label>
      <label>Venue name<input value={form.venue} onChange={(event) => setForm({ ...form, venue: event.target.value })} required /></label>
      <label>Address<input value={form.address} onChange={(event) => setForm({ ...form, address: event.target.value })} /></label>
      <label>Ticket tier<input value={form.tier} onChange={(event) => setForm({ ...form, tier: event.target.value })} required /></label>
      <label>Price (GYD)<input type="number" min="0" step="0.01" value={form.price} onChange={(event) => setForm({ ...form, price: event.target.value })} required /></label>
      <label>Quantity<input type="number" min="1" value={form.quantity} onChange={(event) => setForm({ ...form, quantity: event.target.value })} required /></label>
      <button className="form-wide" disabled={busy}>{busy ? 'Creating…' : 'Create draft event'}</button>
    </form>
  </section>;
}
