import { type ChangeEvent, type FormEvent, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { useAuth } from '../auth/AuthContext';
import { ApiError } from '../lib/apiClient';
import {
  type CreatorVerificationDocumentStatus,
  createEvent,
  getCreatorVerificationDocumentStatus,
  uploadCreatorVerificationDocument,
} from '../lib/userApi';

type TierFormState = { name: string; price: string; quantity: string };

const initialTier = (): TierFormState => ({ name: 'General Admission', price: '0', quantity: '100' });
const additionalTier = (): TierFormState => ({ name: '', price: '0', quantity: '' });

function iso(value: string) { return new Date(value).toISOString(); }

function formatBytes(value: number) {
  return value >= 1024 * 1024 ? `${Math.floor(value / (1024 * 1024))} MB` : `${Math.floor(value / 1024)} KB`;
}

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
  const { user, refreshUser } = useAuth();
  const [form, setForm] = useState({ title: '', description: '', start: '', end: '', venue: '', address: '' });
  const [tiers, setTiers] = useState<TierFormState[]>([initialTier()]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [verification, setVerification] = useState<CreatorVerificationDocumentStatus | null>(null);
  const [verificationLoading, setVerificationLoading] = useState(true);
  const [verificationError, setVerificationError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<File | null>(null);
  const [uploadingId, setUploadingId] = useState(false);
  const [uploadSuccess, setUploadSuccess] = useState(false);

  useEffect(() => {
    let active = true;
    void getCreatorVerificationDocumentStatus()
      .then((status) => { if (active) setVerification(status); })
      .catch(() => { if (active) setVerificationError('Verification status is temporarily unavailable. You can still create a draft event.'); })
      .finally(() => { if (active) setVerificationLoading(false); });
    return () => { active = false; };
  }, []);

  function selectVerificationFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] ?? null;
    setVerificationError(null);
    setUploadSuccess(false);
    if (!file) { setSelectedId(null); return; }
    const allowed = verification?.allowed_content_types ?? [];
    if (!allowed.includes(file.type)) {
      setSelectedId(null);
      event.target.value = '';
      setVerificationError('Choose a JPEG, PNG, or WEBP image.');
      return;
    }
    if (verification && file.size > verification.max_upload_bytes) {
      setSelectedId(null);
      event.target.value = '';
      setVerificationError(`The image must be ${formatBytes(verification.max_upload_bytes)} or smaller.`);
      return;
    }
    setSelectedId(file);
  }

  async function uploadVerificationId() {
    if (!selectedId || uploadingId) return;
    setUploadingId(true);
    setVerificationError(null);
    try {
      const status = await uploadCreatorVerificationDocument(selectedId);
      setVerification(status);
      setSelectedId(null);
      setUploadSuccess(true);
      await refreshUser();
    } catch (reason) {
      setVerificationError(reason instanceof ApiError ? reason.detail : 'The ID could not be uploaded safely. Please try again.');
    } finally {
      setUploadingId(false);
    }
  }

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
    <div className="verification-notice" aria-live="polite">
      {(verification?.account_verification_status ?? user?.creator_age_identity_verification_status) === 'verified' ? <>
        <strong>Age verified</strong>
        <p>Your account is verified. You do not need to submit ID again for future events unless Admitly requests reverification. Each event still requires normal review and approval.</p>
      </> : <>
        <strong>{(verification?.account_verification_status ?? user?.creator_age_identity_verification_status) === 'revoked' ? 'Reverification required' : 'Verify your age'}</strong>
        <p>Event creators must be at least 18. Upload a valid government-issued ID for age and identity verification. Your document is stored privately and deleted after review. Once your account is verified, you generally will not need to submit ID again for future events.</p>
        {verification?.review_outcome === 'rejected' ? <p className="form-error">Verification could not be completed. Please submit a new ID.</p> : null}
        {verificationLoading ? <p className="muted-text">Checking verification availability…</p> : null}
        {verification?.document_pending_review ? <p className="verification-status"><strong>ID submitted — awaiting review</strong>{verification.uploaded_at ? ` · ${new Date(verification.uploaded_at).toLocaleString()}` : ''}</p> : null}
        {verification?.document_status === 'cleanup_required' || verification?.document_status === 'uploading' ? <p className="verification-status">A previous submission is being safely processed. Upload will become available after cleanup completes.</p> : null}
        {!verificationLoading && verification && !verification.document_pending_review && !['cleanup_required', 'uploading'].includes(verification.document_status ?? '') ? (
          verification.upload_enabled ? <div className="verification-upload-controls">
            <label className="verification-file-label">
              Upload ID
              <input type="file" accept="image/jpeg,image/png,image/webp" onChange={selectVerificationFile} disabled={uploadingId} />
            </label>
            <p className="muted-text">JPEG, PNG, or WEBP · maximum {formatBytes(verification.max_upload_bytes)}</p>
            {selectedId ? <p>Selected: <span className="selected-file-name">{selectedId.name}</span></p> : null}
            <button type="button" className="button" disabled={!selectedId || uploadingId} onClick={() => void uploadVerificationId()}>
              {uploadingId ? 'Uploading securely…' : 'Submit ID for review'}
            </button>
          </div> : <p className="verification-status">Online ID submission is temporarily unavailable. You can still create a draft event; contact Admitly support for verification help.</p>
        ) : null}
        {uploadSuccess ? <p className="success-text"><strong>ID submitted for review</strong></p> : null}
        {verificationError ? <p className="form-error" role="alert">{verificationError}</p> : null}
      </>}
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
