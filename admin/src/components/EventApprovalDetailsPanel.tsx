import type { AdminPendingEvent, CreatorVerificationHistory } from '../lib/eventApprovalsApi';

type EventApprovalDetailsPanelProps = {
  event: AdminPendingEvent;
  history: CreatorVerificationHistory[];
  hasPendingDocument: boolean;
  approving: boolean;
  verifying: boolean;
  verificationNote: string;
  revocationReason: string;
  onApprove(): void;
  onCollapse(): void;
  onVerify(): void;
  onRevoke(): void;
  onVerificationNoteChange(value: string): void;
  onRevocationReasonChange(value: string): void;
};

function formatDate(value: string | null) {
  return value ? new Date(value).toLocaleString() : '—';
}

function statusTone(value: string) {
  if (['approved', 'verified', 'published'].includes(value)) return 'review-status-positive';
  if (['revoked', 'rejected', 'cancelled'].includes(value)) return 'review-status-danger';
  if (['pending', 'draft', 'unpublished'].includes(value)) return 'review-status-warning';
  return 'review-status-neutral';
}

function StatusBadge({ label, value }: { label: string; value: string }) {
  return <span className={`review-status-badge ${statusTone(value)}`}>{label}: {value}</span>;
}

function Detail({ label, value }: { label: string; value: string }) {
  return <div><dt>{label}</dt><dd>{value}</dd></div>;
}

export function EventApprovalDetailsPanel({
  event,
  history,
  hasPendingDocument,
  approving,
  verifying,
  verificationNote,
  revocationReason,
  onApprove,
  onCollapse,
  onVerify,
  onRevoke,
  onVerificationNoteChange,
  onRevocationReasonChange,
}: EventApprovalDetailsPanelProps) {
  const canApprove = event.approval_status !== 'approved' && event.creator_account_verification_status === 'verified';

  return <article className="event-approval-details" aria-label={`Review ${event.title}`}>
    <header className="event-review-header">
      <div>
        <p className="review-panel-kicker">Event approval review</p>
        <h3>{event.title}</h3>
        <div className="review-badge-row">
          <StatusBadge label="Approval" value={event.approval_status} />
          <StatusBadge label="Event" value={event.status} />
          <StatusBadge label="Creator" value={event.creator_account_verification_status} />
          <span className="review-created">Created {formatDate(event.created_at)}</span>
        </div>
      </div>
      <div className="review-primary-actions">
        <button type="button" onClick={onApprove} disabled={approving || !canApprove}>
          {event.approval_status === 'approved' ? 'Approved' : approving ? 'Approving…' : 'Approve'}
        </button>
        <button type="button" className="button-link review-collapse-button" onClick={onCollapse}>Hide details</button>
      </div>
    </header>

    <div className="event-review-card-grid">
      <section className="event-review-card" aria-labelledby={`event-details-${event.id}`}>
        <h4 id={`event-details-${event.id}`}>Event details</h4>
        <dl className="event-review-detail-grid">
          <Detail label="Organizer" value={event.organizer_name ?? '—'} />
          <Detail label="Start" value={formatDate(event.start_at)} />
          <Detail label="Venue" value={event.venue_name ?? event.custom_venue_name ?? '—'} />
          <Detail label="Slug" value={event.slug} />
          <Detail label="Published" value={formatDate(event.published_at)} />
          <Detail label="Event status" value={event.status} />
        </dl>
      </section>

      <section className="event-review-card" aria-labelledby={`creator-verification-${event.id}`}>
        <h4 id={`creator-verification-${event.id}`}>Creator verification</h4>
        <dl className="event-review-detail-grid">
          <Detail label="Creator user ID" value={`#${event.creator_user_id}`} />
          <Detail label="Verification status" value={event.creator_account_verification_status} />
          <Detail label="Account verified at" value={formatDate(event.creator_account_verified_at)} />
          <Detail label="Verifier" value={event.creator_account_verified_by_user_id ? `#${event.creator_account_verified_by_user_id}` : '—'} />
          <Detail label="Approval snapshot" value={formatDate(event.creator_age_identity_verification_snapshot_at)} />
          <Detail label="Revoked at" value={formatDate(event.creator_account_revoked_at)} />
        </dl>
        {event.creator_account_revocation_reason ? <div className="review-revocation-summary"><span>Revocation reason</span><p>{event.creator_account_revocation_reason}</p></div> : null}
      </section>
    </div>

    <section className="event-review-card review-actions-card" aria-labelledby={`review-actions-${event.id}`}>
      <h4 id={`review-actions-${event.id}`}>Review actions</h4>
      {event.creator_account_verification_status !== 'verified' && hasPendingDocument ? (
        <p className="verification-status">A private document is pending for this creator. Review and act on it in the verification section above.</p>
      ) : event.creator_account_verification_status !== 'verified' ? (
        <div className="review-standard-action">
          <label>Optional safe audit note (no ID number or image)<input value={verificationNote} maxLength={1000} onChange={(changeEvent) => onVerificationNoteChange(changeEvent.target.value)} /></label>
          <button type="button" disabled={verifying} onClick={onVerify}>{verifying ? 'Recording…' : 'Verify creator account as 18+'}</button>
        </div>
      ) : (
        <div className="review-destructive-action">
          <div><strong>Revoke account verification</strong><p>Future event approvals will be blocked. Existing approved events remain unchanged.</p></div>
          <div className="review-destructive-controls">
            <label>Required revocation reason<input value={revocationReason} maxLength={1000} onChange={(changeEvent) => onRevocationReasonChange(changeEvent.target.value)} /></label>
            <button type="button" className="danger-button" disabled={verifying} onClick={onRevoke}>Revoke account verification</button>
          </div>
        </div>
      )}
    </section>

    <section className="event-review-card verification-history-card" aria-labelledby={`verification-history-${event.id}`}>
      <h4 id={`verification-history-${event.id}`}>Verification history</h4>
      {history.length ? <ol className="verification-timeline">{history.map((row) => <li key={row.id}>
        <span className="timeline-marker" aria-hidden="true" />
        <div><time>{formatDate(row.created_at)}</time><p><strong>{row.previous_status} → {row.new_status}</strong> by admin #{row.actor_user_id}</p>{row.note ? <p className="timeline-note">{row.note}</p> : null}</div>
      </li>)}</ol> : <p className="muted-text">No recorded account verification history.</p>}
    </section>
  </article>;
}
