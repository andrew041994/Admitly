# Payment reconciliation and refund SOP

This is provider-independent operational guidance. It does not define MMG settlement semantics or authorize live MMG behavior. All times and cutoff windows below use `America/Guyana` (GYT, UTC-04:00) unless the provider statement defines a different timezone; record both the provider timezone and normalized UTC timestamps.

## Ownership, cadence, and evidence

- **Owner:** the designated finance operator owns daily reconciliation and the exception queue. With one administrator, that person performs and records a deliberate second-pass review. Independent two-person approval is a future scaling control.
- **Daily:** by 10:00 GYT, reconcile provider activity from the previous calendar day through 23:59:59 GYT, plus all still-open exceptions and pending refunds. During active/high-volume event sales, reconcile at least once more before payout or event start.
- **Weekly:** reconcile provider opening/closing totals, Admitly completed/refunded totals, fees/net settlement totals, all aged exceptions, disputes/chargebacks, and payout eligibility. Close the week only when totals match or every variance has an owned exception.
- **Before payout:** reconcile every included order and refund regardless of the routine cadence. Unreconciled, disputed, or ambiguous money remains held.
- **Event-creator payout commitment:** process payout, less applicable fees, within five business days after the event concludes. This is currently an operator-owned deadline, not an automated scheduler. Record the event end time/timezone, calculated fifth business-day deadline, reconciliation completion, exceptions, and payout processing evidence.
- **Evidence:** store provider exports/screenshots, generated Admitly finance exports, calculation workbook/query output, exception register, approval notes, and completion evidence in a restricted finance location organized as `YYYY/MM/DD/reconciliation-run-id`. The repository and general support chat are not evidence storage.

Each run records operator, second-pass reviewer status, source/export identifiers, provider and Admitly cutoff timestamps/timezones, extraction times, hash or immutable file identity where available, row counts, currency totals, exceptions by aging bucket, approvals, and final disposition. Do not store credentials, full callback payloads, or unnecessary customer data.

## Exact comparison fields

Match at transaction level before comparing aggregates:

- provider name and payment method;
- Admitly internal order ID and public order reference;
- stored provider/payment reference and payment-attempt provider reference;
- order status and payment verification/authenticity status;
- provider transaction status and effective/settlement timestamp;
- gross/order total amount and three-letter currency;
- discount/subtotal context where diagnosing, without substituting subtotal for amount paid;
- provider fee, net amount, settlement/batch reference, and settlement date when supplied;
- refund ID, refund amount/currency, status, provider refund reference/status, submitted/verified/processed timestamps;
- dispute/chargeback state;
- Admitly reconciliation status/time/actor/note and payout status/batch/date.

Use exact reference, amount, and currency matches. Do not normalize away material whitespace/case differences without documenting the provider contract. Never infer provider payment from an Admitly `completed` state alone or infer Admitly fulfillment from a provider `paid` row alone.

## Daily reconciliation procedure

1. Obtain the provider settlement/transaction export through its approved authenticated channel. Store it in the restricted evidence location and record source, cutoff, timezone, export time, and file identity.
2. Generate the matching Admitly finance/order/payment-attempt/refund data for the same half-open interval `[cutoff_start, cutoff_end)`. Keep the original exports immutable.
3. Match the exact fields above. Reconcile counts and totals by currency; never net different currencies together.
4. Classify every unmatched or inconsistent item, create/link a support exception, assign an owner and next review time, and preserve both source rows.
5. Mark an order reconciled only after authoritative provider evidence matches its provider/reference, amount, currency, and status and Admitly fulfillment is consistent. Supply a meaningful reconciliation note. A re-run is idempotent only after reloading state; it must not be used to manufacture provider proof.
6. Do not make an order payout-eligible/included/paid while it is unreconciled, disputed, refunded inconsistently, or in manual review.
7. Perform the recorded second-pass review of row counts, gross/refund/fee/net totals, exceptions, and all state changes. With one admin this is a same-person second pass, explicitly labeled—not two-person approval.
8. For concluded events, place the reconciled payout in the operator queue early enough to meet the five-business-day commitment. Delay only for a documented reconciliation, fraud/security, dispute/refund, legal, or incomplete payout-information issue; record owner, reason, next review time, and revised expectation. Do not mark `paid` until authoritative payout evidence exists.

## Discrepancy classification and aging

Use one primary classification:

- `provider_paid_admitly_pending`: authoritative provider paid, Admitly not completed;
- `admitly_complete_provider_missing`: Admitly completed/verified, no authoritative provider payment;
- `amount_mismatch` or `currency_mismatch`;
- `provider_or_reference_mismatch`;
- `duplicate_reference_or_callback`;
- `fulfillment_mismatch`: completed order ticket count differs from ordered quantity;
- `refund_admitly_only`, `refund_provider_only`, or `refund_amount_status_mismatch`;
- `dispute_or_chargeback`;
- `settlement_fee_or_net_mismatch`;
- `stale_pending_or_manual_review`;
- `timing_cutoff`: verified activity belongs to an adjacent provider cutoff;
- `unknown`: evidence is insufficient or contradictory.

Age from the earliest of provider effective time, Admitly payment/refund submission time, or detection time:

- **0–24 hours:** new; validate cutoffs and source completeness before intervention.
- **24–72 hours:** aged; daily owner follow-up and no payout inclusion.
- **3–7 days:** escalated; finance owner review and documented provider follow-up when live integration exists.
- **Over 7 days:** critical backlog; incident review if systemic, explicit financial exposure, and owner/due date.

Any duplicate reference, fulfillment mismatch, unexpected completed order, or refund that could cause financial loss escalates immediately regardless of age.

## Manual-review rules

- Buyer screenshots, copied messages, typed references, or matching amount/currency are not proof of payment or refund.
- Authoritative evidence must come from an authenticated provider portal/API/export whose transaction identity, amount, currency, status, and order mapping can be verified.
- Until official MMG lookup/authenticity behavior is implemented, do not use the manual MMG verification endpoint operationally and do not provider-confirm an MMG refund. Leave the case pending/`waiting_on_payment_provider` and fulfillment unchanged.
- An ambiguous provider timeout or unknown response must not be retried blindly. First search by the same idempotency/reference key and verify whether the provider created or processed the transaction.
- Preserve the originally generated Admitly/provider identifiers. Never create a new order/refund merely to obtain a different reference for the same intended operation.
- Callback receipt and stored payload are not authenticity. Only a successfully verified provider mechanism may prove a callback.

## Retry and idempotency expectations

1. Generate or reuse one stable business identifier for one payment/refund intent; do not issue concurrent retries.
2. On timeout/5xx/connection loss, classify the result as unknown. Query authoritative provider status using the original identifier before retrying.
3. If the provider supports idempotency keys, reuse the exact original key and follow its documented retention window. If support is unknown, do not invent semantics or retry a financial submission.
4. Reload the Admitly order/refund and audit history before any local action. Terminal states are not replayed. Duplicate callback/reference evidence is investigated, not manually “cleared.”
5. Record attempt time, operator/system actor, request identifier (not secrets/payload), observed response class, lookup result, decision, and next review.

## Refund approval and rejection

1. Identify the refund, internal/public order reference, requester/current eligible owner, event, and original payment. Verify completed/paid status, payment authenticity, provider/reference, amount/currency, remaining refundable amount, prior refunds/disputes, transfer/check-in/void state, event timing/policy, payout status, and applicable approved policy.
2. Calculate the maximum remaining refundable amount from processed refunds and the order total. Do not include a pending/approved amount twice, approve above remaining value, or silently assume fees are refundable.
3. Write the support-case reason before the action: decision, policy basis, evidence, exact amount/currency, provider state, ticket effects, post-payout adjustment impact, and follow-up owner. The current refund approve/reject services do not uniformly create a separate `admin_action_audits` row, so the support note is mandatory.
4. **Approve:** use only the supported admin refund endpoint. Approval is not provider completion. For MMG, the repository leaves it approved and awaiting provider confirmation; do not mark it processed while live provider calls/verification are unavailable.
5. **Reject:** require a specific rejection reason, use the supported endpoint, verify status is `rejected`, and communicate only the approved policy basis. Never reject to conceal a reconciliation discrepancy.
6. **Provider confirmation:** require authoritative provider evidence and the unique provider refund reference. The confirm action is audited and row-locked, but a typed reference is not independent provider verification. Do not use it for MMG until official lookup/status validation exists.
7. After verified completion, confirm financial reversal, order refund state, ticket effects, post-payout adjustment if applicable, provider reference uniqueness, and reconciliation totals. A checked-in ticket or ambiguous transfer/refund claim requires escalation rather than an automatic state change.

Record approval/rejection actor, UTC time, reason, case ID, refund/order IDs, amount/currency, policy/evidence location, original and final statuses, provider reference fingerprint or restricted evidence link, downstream ticket/ledger state, and notification decision. Never paste a full provider payload into the audit note.

## Ambiguous payment or refund

When provider and Admitly disagree or a result is unknown:

1. Do not mark paid/processed, issue tickets, retry submission, reconcile, pay out, or promise a refund.
2. Set/retain the support case as `waiting_on_payment_provider` or `investigating`; classify and age the exception.
3. Preserve both systems' identifiers, timestamps, amount/currency/status, attempt/audit history, request IDs, and source evidence.
4. Check cutoff/timezone and duplicate/reference collisions before assuming loss.
5. Escalate to the finance owner and, once live integration exists, the provider through an authenticated support channel. Security, duplicate fulfillment, or broad discrepancy becomes an incident.
6. Resolve only from authoritative evidence. Record why the losing record was incorrect and how aggregates/fulfillment were verified afterward.

## Release blocker

The repository's live MMG checkout creation, callback authenticity verification, live transaction/reference lookup, refund submission/status lookup, and provider settlement contract are not implemented. Keep `MMG_ENABLED=false`. Do not enable `MMG_PROVIDER_MODE=live`, use manual MMG completion, or claim live MMG reconciliation readiness until official API/signature/idempotency/refund/settlement documentation, sandbox certification, credentials, and reviewed tests exist.
