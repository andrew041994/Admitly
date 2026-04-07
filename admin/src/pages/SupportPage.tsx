import { FormEvent, useMemo, useState } from 'react';
import { ApiError } from '../lib/apiClient';
import {
  SupportSnapshot,
  createSupportNote,
  fetchSupportSnapshot,
  runSupportAction,
  updateSupportCase,
} from '../lib/supportApi';

const CASE_STATUSES = [
  'open',
  'investigating',
  'waiting_on_customer',
  'waiting_on_payment_provider',
  'resolved',
  'closed',
];
const CASE_PRIORITIES = ['low', 'normal', 'high', 'urgent'];
const SUPPORT_ACTIONS = [
  { action: 'resend_confirmation', label: 'Resend confirmation', needsReason: false, sensitive: false },
  { action: 'resend_transfer_invite', label: 'Resend transfer invite', needsReason: false, sensitive: false },
  { action: 'reopen_refund_review', label: 'Reopen refund review', needsReason: true, sensitive: true },
  { action: 'flag_for_fraud_review', label: 'Flag for fraud review', needsReason: true, sensitive: true },
  { action: 'remove_promo_application', label: 'Remove promo application', needsReason: true, sensitive: true },
  { action: 're-run_reconciliation', label: 'Re-run reconciliation', needsReason: false, sensitive: false },
];

type CaseEditorState = {
  status: string;
  priority: string;
  assignedToUserId: string;
  category: string;
};

function formatDate(value: string | null | undefined) {
  if (!value) return '—';
  return new Date(value).toLocaleString();
}

function formatMoney(amount: number, currency: string) {
  return new Intl.NumberFormat(undefined, { style: 'currency', currency }).format(amount);
}

export function SupportPage() {
  const [lookupInput, setLookupInput] = useState('');
  const [loadedOrderId, setLoadedOrderId] = useState<number | null>(null);
  const [snapshot, setSnapshot] = useState<SupportSnapshot | null>(null);
  const [lookupError, setLookupError] = useState<string | null>(null);
  const [lookupStatus, setLookupStatus] = useState<'idle' | 'loading' | 'not-found' | 'forbidden'>('idle');
  const [noteBody, setNoteBody] = useState('');
  const [caseDraft, setCaseDraft] = useState<CaseEditorState | null>(null);
  const [actionReason, setActionReason] = useState<Record<string, string>>({});
  const [feedback, setFeedback] = useState<string | null>(null);
  const [errorFeedback, setErrorFeedback] = useState<string | null>(null);
  const [savingCase, setSavingCase] = useState(false);
  const [savingNote, setSavingNote] = useState(false);
  const [runningAction, setRunningAction] = useState<string | null>(null);

  const loaded = Boolean(snapshot && loadedOrderId !== null);

  const initCaseDraft = (data: SupportSnapshot) => {
    setCaseDraft({
      status: data.support_case?.status ?? 'open',
      priority: data.support_case?.priority ?? 'normal',
      assignedToUserId: data.support_case?.assigned_to_user_id?.toString() ?? '',
      category: data.support_case?.category ?? 'other',
    });
  };

  const loadSnapshot = async (orderId: number) => {
    setLookupStatus('loading');
    setLookupError(null);
    setErrorFeedback(null);
    try {
      const data = await fetchSupportSnapshot(orderId);
      setSnapshot(data);
      setLoadedOrderId(orderId);
      initCaseDraft(data);
      setLookupStatus('idle');
    } catch (error) {
      if (error instanceof ApiError) {
        if (error.status === 404) {
          setLookupStatus('not-found');
          setLookupError('Order not found.');
          return;
        }
        if (error.status === 401 || error.status === 403) {
          setLookupStatus('forbidden');
          setLookupError('You do not have permission to view support data.');
          return;
        }
        setLookupError(error.detail);
      } else {
        setLookupError('Failed to load support snapshot.');
      }
      setLookupStatus('idle');
    }
  };

  const onLookupSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setFeedback(null);
    const trimmed = lookupInput.trim();
    if (!trimmed) {
      setLookupError('Order ID is required.');
      return;
    }
    if (!/^\d+$/.test(trimmed)) {
      setLookupError('Order ID must be numeric.');
      return;
    }
    await loadSnapshot(Number(trimmed));
  };

  const onSaveCase = async () => {
    if (!loadedOrderId || !caseDraft) return;
    setSavingCase(true);
    setFeedback(null);
    setErrorFeedback(null);
    try {
      await updateSupportCase(loadedOrderId, {
        status: caseDraft.status,
        priority: caseDraft.priority,
        assigned_to_user_id: caseDraft.assignedToUserId ? Number(caseDraft.assignedToUserId) : null,
        category: caseDraft.category.trim(),
      });
      const fresh = await fetchSupportSnapshot(loadedOrderId);
      setSnapshot(fresh);
      initCaseDraft(fresh);
      setFeedback('Support case updated.');
    } catch (error) {
      setErrorFeedback(error instanceof ApiError ? error.detail : 'Failed to update support case.');
    } finally {
      setSavingCase(false);
    }
  };

  const onCreateNote = async (event: FormEvent) => {
    event.preventDefault();
    if (!loadedOrderId) return;
    const trimmed = noteBody.trim();
    if (!trimmed) {
      setErrorFeedback('Note cannot be blank.');
      return;
    }
    setSavingNote(true);
    setFeedback(null);
    setErrorFeedback(null);
    try {
      await createSupportNote(loadedOrderId, trimmed);
      setNoteBody('');
      const fresh = await fetchSupportSnapshot(loadedOrderId);
      setSnapshot(fresh);
      initCaseDraft(fresh);
      setFeedback('Internal note added.');
    } catch (error) {
      setErrorFeedback(error instanceof ApiError ? error.detail : 'Failed to create note.');
    } finally {
      setSavingNote(false);
    }
  };

  const onRunAction = async (actionType: string, needsReason: boolean, sensitive: boolean) => {
    if (!loadedOrderId) return;
    const reason = (actionReason[actionType] || '').trim();
    if (needsReason && !reason) {
      setErrorFeedback('A reason is required for this action.');
      return;
    }
    if (sensitive && !window.confirm(`Run sensitive action "${actionType}" for order ${loadedOrderId}?`)) {
      return;
    }
    setRunningAction(actionType);
    setFeedback(null);
    setErrorFeedback(null);
    try {
      const result = await runSupportAction(loadedOrderId, {
        action_type: actionType,
        reason: reason || undefined,
      });
      const fresh = await fetchSupportSnapshot(loadedOrderId);
      setSnapshot(fresh);
      initCaseDraft(fresh);
      setFeedback(result.message);
    } catch (error) {
      setErrorFeedback(error instanceof ApiError ? error.detail : 'Failed to run admin action.');
    } finally {
      setRunningAction(null);
    }
  };

  const summaryRows = useMemo(
    () =>
      snapshot
        ? [
            ['Order ID', `#${snapshot.order_id}`],
            ['Event', snapshot.event_title ? `${snapshot.event_title} (#${snapshot.event_id})` : `#${snapshot.event_id}`],
            ['Buyer', `User #${snapshot.buyer_user_id}`],
            ['Order status', snapshot.order_status],
            ['Quantity', String(snapshot.quantity)],
            ['Total', formatMoney(snapshot.total_amount, snapshot.currency)],
            ['Created', formatDate(snapshot.timeline[0]?.timestamp)],
          ]
        : [],
    [snapshot],
  );

  return (
    <section className="support-page" aria-labelledby="support-title">
      <header>
        <h2 id="support-title">Admin Support Workspace</h2>
      </header>

      <div className="card">
        <form className="lookup-row" onSubmit={onLookupSubmit}>
          <label htmlFor="order-id">Order ID</label>
          <input
            id="order-id"
            value={lookupInput}
            onChange={(event) => setLookupInput(event.target.value)}
            placeholder="Enter order ID"
            disabled={lookupStatus === 'loading'}
          />
          <button type="submit" disabled={lookupStatus === 'loading'}>
            {lookupStatus === 'loading' ? 'Loading…' : 'Load'}
          </button>
        </form>
        {lookupError ? <p className="error-text">{lookupError}</p> : null}
      </div>

      {feedback ? <div className="card success-text">{feedback}</div> : null}
      {errorFeedback ? <div className="card error-text">{errorFeedback}</div> : null}

      {!loaded && lookupStatus === 'idle' ? <div className="card">Load an order to begin support operations.</div> : null}
      {!loaded && lookupStatus === 'loading' ? <div className="card">Loading support snapshot…</div> : null}
      {!loaded && lookupStatus === 'not-found' ? <div className="card">No order found for that ID.</div> : null}
      {!loaded && lookupStatus === 'forbidden' ? <div className="card">Permission denied.</div> : null}

      {snapshot ? (
        <div className="support-grid">
          <div className="card">
            <h3>Support snapshot summary</h3>
            <dl className="kv-list">
              {summaryRows.map(([label, value]) => (
                <div key={label}>
                  <dt>{label}</dt>
                  <dd>{value}</dd>
                </div>
              ))}
            </dl>
            <div className="summary-columns">
              <div>
                <h4>Payment</h4>
                <p>Reference: {snapshot.payment_reference || '—'}</p>
                <p>Verification: {snapshot.payment_verification_status}</p>
                <p>Submitted: {formatDate(snapshot.payment_submitted_at)}</p>
                <p>Paid: {formatDate(snapshot.paid_at)}</p>
              </div>
              <div>
                <h4>Refunds & disputes</h4>
                <p>Refund status: {snapshot.refund_status}</p>
                <p>Refunded at: {formatDate(snapshot.refunded_at)}</p>
                <p>Disputes: {snapshot.dispute_count}</p>
              </div>
              <div>
                <h4>Promo / transfer / reconciliation</h4>
                <p>Promo: {snapshot.promo_code_text || '—'}</p>
                <p>Transfer invites: {snapshot.transfer_invite_count}</p>
                <p>Reconciliation: {snapshot.reconciliation_status}</p>
                <p>Payout: {snapshot.payout_status}</p>
                <p>Subtotal: {formatMoney(snapshot.subtotal_amount, snapshot.currency)}</p>
                <p>Discount: {formatMoney(snapshot.discount_amount, snapshot.currency)}</p>
              </div>
            </div>
          </div>

          <div className="card">
            <h3>Support case editor</h3>
            <div className="form-grid">
              <label>
                Status
                <select
                  value={caseDraft?.status || 'open'}
                  disabled={savingCase}
                  onChange={(event) => setCaseDraft((prev) => (prev ? { ...prev, status: event.target.value } : prev))}
                >
                  {CASE_STATUSES.map((status) => (
                    <option key={status} value={status}>
                      {status}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Priority
                <select
                  value={caseDraft?.priority || 'normal'}
                  disabled={savingCase}
                  onChange={(event) => setCaseDraft((prev) => (prev ? { ...prev, priority: event.target.value } : prev))}
                >
                  {CASE_PRIORITIES.map((priority) => (
                    <option key={priority} value={priority}>
                      {priority}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Assigned admin (user ID)
                <input
                  value={caseDraft?.assignedToUserId || ''}
                  disabled={savingCase}
                  onChange={(event) =>
                    setCaseDraft((prev) => (prev ? { ...prev, assignedToUserId: event.target.value.trim() } : prev))
                  }
                />
              </label>
              <label>
                Category
                <input
                  value={caseDraft?.category || ''}
                  disabled={savingCase}
                  onChange={(event) => setCaseDraft((prev) => (prev ? { ...prev, category: event.target.value } : prev))}
                />
              </label>
            </div>
            <button onClick={onSaveCase} disabled={savingCase}>
              {savingCase ? 'Saving…' : 'Update case'}
            </button>
          </div>

          <div className="card">
            <h3>Internal notes</h3>
            <form onSubmit={onCreateNote} className="notes-form">
              <textarea
                value={noteBody}
                onChange={(event) => setNoteBody(event.target.value)}
                placeholder="Add internal note"
                disabled={savingNote}
              />
              <button type="submit" disabled={savingNote}>
                {savingNote ? 'Saving…' : 'Add note'}
              </button>
            </form>
            <ul className="list-reset">
              {snapshot.support_notes.length === 0 ? (
                <li className="muted-text">No notes yet.</li>
              ) : (
                snapshot.support_notes.map((note) => (
                  <li key={note.id} className="timeline-item">
                    <strong>{note.is_system_note ? 'System note' : `Admin #${note.author_user_id}`}</strong>
                    <p>{note.body}</p>
                    <small>{formatDate(note.created_at)}</small>
                  </li>
                ))
              )}
            </ul>
          </div>

          <div className="card">
            <h3>Timeline / audit trail</h3>
            <ul className="list-reset">
              {snapshot.timeline.length === 0 ? (
                <li className="muted-text">No timeline entries.</li>
              ) : (
                snapshot.timeline.map((item, index) => (
                  <li key={`${item.timestamp}-${index}`} className="timeline-item">
                    <strong>{item.title}</strong> <span className="badge">{item.type}</span>
                    <p>{item.description}</p>
                    <small>
                      {formatDate(item.timestamp)} {item.actor ? `• ${item.actor}` : ''}
                    </small>
                  </li>
                ))
              )}
            </ul>
            {snapshot.admin_audits.length > 0 ? (
              <details>
                <summary>Additional audits ({snapshot.admin_audits.length})</summary>
                <ul className="list-reset">
                  {snapshot.admin_audits.map((audit) => (
                    <li key={audit.id} className="timeline-item">
                      <strong>{audit.action_type}</strong>
                      <p>{audit.reason || 'Admin action recorded.'}</p>
                      <small>{formatDate(audit.created_at)}</small>
                    </li>
                  ))}
                </ul>
              </details>
            ) : null}
          </div>

          <div className="card">
            <h3>Admin actions</h3>
            <div className="actions-grid">
              {SUPPORT_ACTIONS.map((item) => (
                <div key={item.action} className="action-item">
                  <h4>{item.label}</h4>
                  {item.needsReason ? (
                    <input
                      value={actionReason[item.action] || ''}
                      onChange={(event) =>
                        setActionReason((prev) => ({ ...prev, [item.action]: event.target.value }))
                      }
                      placeholder="Reason required"
                      disabled={Boolean(runningAction)}
                    />
                  ) : null}
                  <button
                    onClick={() => onRunAction(item.action, item.needsReason, item.sensitive)}
                    disabled={Boolean(runningAction)}
                  >
                    {runningAction === item.action ? 'Running…' : 'Run action'}
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
