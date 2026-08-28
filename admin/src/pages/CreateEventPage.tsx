import { type FormEvent, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { useAuth } from '../auth/AuthContext';
import { createEvent } from '../lib/userApi';

type TierFormState = { name: string; price: string; quantity: string };

const initialTier = (): TierFormState => ({ name: 'General Admission', price: '0', quantity: '100' });
const additionalTier = (): TierFormState => ({ name: '', price: '0', quantity: '' });

function iso(value: string) { return new Date(value).toISOString(); }

function validateTiers(tiers: TierFormState[]): string | null {
  if (!tiers.length) return 'At least one ticket tier is required.';
  for (let index = 0; index < tiers.length; index += 1) {
    const tier = tiers[index];
    if (!tier.name.trim()) return `Tier ${index + 1}: name is required.`;
    const price = Number(tier.price);
    if (!tier.price.trim() || !Number.isFinite(price) || price < 0) return `Tier ${index + 1}: price must be zero or greater.`;
    const quantity = Number(tier.quantity);
    if (!tier.quantity.trim() || !Number.isInteger(quantity) || quantity <= 0) return `Tier ${index + 1}: quantity must be a positive integer.`;
  }
  return null;
}

export function CreateEventPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const creatorVerified = user?.creator_age_identity_verification_status === 'verified';
  const [form, setForm] = useState({ title: '', description: '', start: '', end: '', venue: '', address: '' });
  const [tiers, setTiers] = useState<TierFormState[]>([initialTier()]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function updateTier(index: number, values: Partial<TierFormState>) {
    setTiers((current) => current.map((tier, tierIndex) => tierIndex === index ? { ...tier, ...values } : tier));
  }

  function removeTier(index: number) {
    if (index === 0) return;
    setTiers((current) => current.filter((_tier, tierIndex) => tierIndex !== index));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setError(null);
    const tierError = validateTiers(tiers);
    if (tierError) { setError(tierError); return; }
    setBusy(true);
    try {
      const created = await createEvent({
        title: form.title,
        short_description: form.description,
        start_at: iso(form.start),
        end_at: iso(form.end),
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'America/Guyana',
        custom_venue_name: form.venue,
        custom_address_text: form.address,
        ticket_tiers: tiers.map((tier) => ({
          name: tier.name.trim(),
          price_amount: Number(tier.price).toFixed(2),
          currency: 'GYD',
          quantity_total: Number(tier.quantity),
          min_per_order: 1,
          max_per_order: 10,
        })),
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
      {error ? <p className="form-error form-wide" role="alert">{error}</p> : null}
      <label className="form-wide">Event title<input value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} required /></label>
      <label className="form-wide">Short description<textarea value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} /></label>
      <label>Starts<input type="datetime-local" value={form.start} onChange={(event) => setForm({ ...form, start: event.target.value })} required /></label>
      <label>Ends<input type="datetime-local" value={form.end} onChange={(event) => setForm({ ...form, end: event.target.value })} required /></label>
      <label>Venue name<input value={form.venue} onChange={(event) => setForm({ ...form, venue: event.target.value })} required /></label>
      <label>Address<input value={form.address} onChange={(event) => setForm({ ...form, address: event.target.value })} /></label>
      <section className="ticket-tier-list form-wide" aria-labelledby="ticket-tiers-heading">
        <div className="ticket-tier-heading">
          <div><h2 id="ticket-tiers-heading">Ticket tiers</h2><p>Add the ticket options buyers can choose from.</p></div>
          <button type="button" className="button-link" onClick={() => setTiers((current) => [...current, additionalTier()])}>Add another ticket tier</button>
        </div>
        {tiers.map((tier, index) => (
          <fieldset className="ticket-tier-card" key={`ticket-tier-${index}`}>
            <legend>Tier {index + 1}</legend>
            <div className="ticket-tier-fields">
              <label>Tier name<input value={tier.name} maxLength={120} onChange={(event) => updateTier(index, { name: event.target.value })} required /></label>
              <label>Price (GYD)<input type="number" min="0" step="0.01" value={tier.price} onChange={(event) => updateTier(index, { price: event.target.value })} required /></label>
              <label>Quantity<input type="number" min="1" step="1" value={tier.quantity} onChange={(event) => updateTier(index, { quantity: event.target.value })} required /></label>
            </div>
            {index > 0 ? <button type="button" className="button-link remove-tier-button" onClick={() => removeTier(index)}>Remove tier</button> : null}
          </fieldset>
        ))}
      </section>
      <button className="form-wide" disabled={busy}>{busy ? 'Creating…' : 'Create draft event'}</button>
    </form>
  </section>;
}
