# Admin and support SOP

This SOP describes the supported operator workflow. It does not grant new product permissions. Admitly has one user model: any authenticated user may create an event; only that event's creator or an administrator may edit an existing event. Event staff and scanners do not gain event-edit rights.

## Access, identity, and case hygiene

- Use an individual administrator account with verified email. Never share sessions, passwords, one-time codes, bearer tokens, QR payloads, or payment credentials.
- The current admin workspace is order-centric. It loads only an exact internal numeric order ID at `/admin/support/orders/{order_id}`. The backend snapshot includes the public order reference, event and buyer user IDs, payment attempts, refunds/disputes, transfers, messages, reconciliation/payout status, notes, and audits.
- Start or locate the order support case. Record the requester, contact channel, UTC time, claimed account, event/order/ticket identifiers, issue, consent for any resend, and evidence source. If there is no related order, record it in the operator's approved restricted support system; the repository has no standalone non-order case. Do not attach an unrelated order merely to create a case.
- Verify identity with at least two existing, non-secret facts appropriate to the claim: authenticated account context, normalized account email, public order reference, event ID/title, ticket display/public ID, purchase amount/date, or transfer direction. Do not ask for passwords, verification/reset codes, full payment credentials, raw QR tokens, or full provider secrets.
- Minimize disclosure. A match confirms only the records the requester is authorized to discuss; it does not permit revealing another user's email, tickets, or payment references.
- Before a sensitive action, add a support note containing the reason, source evidence, expected state change, amount/currency where relevant, and rollback/escalation plan. The same reason must be supplied to action endpoints that accept it.
- The browser confirmation dialog is a last-click guard, not a second approval. With one administrator, perform and record a deliberate second-pass review. Durable two-person approval is a future control when more administrators exist.
- Never edit database rows, fabricate provider confirmation, manually reassign ticket ownership, change financial state to satisfy a customer, or use admin access to bypass an eligibility rule.

## Common case lifecycle

1. Classify priority/category and assign the case. Use `urgent` for active admission, account compromise, or credible financial-integrity risk; declare an incident when scope or severity meets the incident runbook.
2. Establish the authoritative internal IDs. Cross-check the public order reference returned by the backend snapshot against an authorized customer/reporting record before acting; the current admin page does not display that field.
3. Review the support timeline, payment attempts/authenticity, refund/dispute state, ticket ownership/status, transfer history, check-in attempts/scan logs, message delivery history, reconciliation/payout state, and admin audits relevant to the report.
4. Write the verification and decision note before a sensitive action. Separate customer claims from facts observed in Admitly or an authenticated provider system.
5. Execute only a supported endpoint/UI action, then reload and verify the resulting state and audit entry. Record partial/no-op/failed outcomes; do not assume a successful click means an email or provider action succeeded.
6. Send the minimum necessary response, set a follow-up time, and move the case to `waiting_on_customer`, `waiting_on_payment_provider`, `resolved`, or `closed` only when that meaning is accurate.

## Workflow 1: user or account issue

**Identify and verify:** Use authenticated account context or a verified reply to the account email. If the report is tied to an order, use the internal order ID supplied through an approved lookup and cross-check its public reference and buyer user ID. For suspected takeover, compare recent request IDs/security evidence without disclosing it to the claimant.

**Permitted:** Explain and direct the user through existing password-reset and email-verification/resend flows; inspect associated order/message history; document delivery failures; advise sign-out/re-authentication; escalate suspected compromise.

**Prohibited:** Asking for a password/code/token; disclosing whether an unrelated email has an account; changing email, password, `is_admin`, verification, or active status directly; transferring an account or its tickets based only on an email request.

**Audit/evidence:** Record the verification channel, masked account identifier, associated user/order IDs, request ID or message-log ID, guidance given, and outcome. Escalate repeated reset/verification failure, suspected takeover, admin-account impact, or multiple affected users.

## Workflow 2: event-creator issue

**Identify and verify:** Obtain the event ID and verify the creator through `events.organizer_id -> organizer_profiles.user_id`; an admin may act regardless of creator. Do not interpret an event-staff record as creator ownership.

**Permitted:** Inspect event status/approval, timestamps, ticket tiers, orders, staff, and audit history; help the authenticated creator use supported event-edit flows; use an existing admin event action only with a documented reason and policy basis.

**Prohibited:** Granting edit rights to a manager, scanner, check-in, or support staff member; treating creation capability as ownership of another event; changing creator/organizer linkage in the database; cancelling/publishing/editing an event solely from an unverified request.

**Audit/evidence:** Record event ID, creator user ID, verification, requested change, current/expected state, and action/audit ID. Escalate safety/legal reports, cancellation with sales, broad ticket/refund impact, ownership disputes, or unexplained event mutations.

### Event-creator age and identity verification

1. Direct the creator to send a valid government-issued ID to the designated Admitly verification email recorded in the private operations inventory. Do not publish the address in source unless it is approved as a public support address.
2. In the email account, compare the identity to the authenticated account/event creator and confirm the creator is at least 18. Do not copy an ID number unless a specific lawful necessity has been approved and documented.
3. In **Event Approvals**, inspect the correct event and creator user ID. Add only an optional non-document note, confirm the ID was reviewed and deleted, and choose **Record 18+ identity verification**.
4. Verify the event now shows `verified`, the creator snapshot matches the event creator, the verifier admin and UTC timestamp are present, and an admin audit record exists.
5. Permanently delete the ID image and message attachment from the verification mailbox as soon as verification is complete, including the mailbox trash/deleted-items location according to the provider's controls. Record completion in the restricted operational evidence log without copying the image or ID number.
6. Never download or copy the image into support cases, S3, application storage, database fields, logs, local folders, issue trackers, or chat. The application intentionally has no ID upload endpoint.
7. If age or identity cannot be verified, do not record `verified` and do not approve or publish the event. Record a minimal support outcome without document details and request corrected evidence through the designated email process if appropriate.

The application retains only the event ID, verified creator user ID, verification status, verifier administrator ID, verification timestamp, optional safe note, and corresponding admin audit. It does not retain the ID image or require an ID number.

## Workflow 3: order or ticket issue

**Identify and verify:** Load the numeric order ID, then match its public order reference, buyer user ID, event, amount/currency, quantity, and ticket count. For a ticket-specific issue, match its internal ID or display/public ID to that order without requesting the QR token.

**Permitted:** Review fulfillment, ticket status, transfers/check-in, payment verification, and message history; resend an order/ticket confirmation only after consent and only for a completed order; reopen a refund review; explain a no-op or failed delivery.

**Prohibited:** Issuing a duplicate ticket, changing order ownership/status, exposing QR data, voiding or checking in a ticket merely to resolve a display problem, or marking payment verified from customer evidence.

**Audit/evidence:** Record the expected quantity versus ticket count, ticket state, message-log outcome, request ID, and action reason. Escalate count mismatch, duplicate credentials, completed order without tickets, verified/payment mismatch, or any admission-integrity concern.

## Workflow 4: ticket-transfer ownership dispute

See the dedicated decision procedure below. Do not manually reassign ownership.

## Workflow 5: check-in or scanning issue

**Identify and verify:** Confirm event ID and ticket display/public ID; verify the operator is the event creator, an admin, or active staff with the exact check-in permission. Check-in permission does not grant event editing. Review current owner, order paid/refund state, event status, ticket state, recent `ticket_check_in_attempts`, and `ticket_scan_logs`.

**Permitted:** Validate before confirming; explain wrong-event, already-used, cancelled/refunded/voided, or invalid results; an authorized creator/admin may review check-in activity; use an existing override only when the authorized venue operator has independently established the admission decision and supplies required notes.

**Prohibited:** Sharing QR/manual codes; admitting on a screenshot or buyer claim alone; resetting a checked-in ticket by database edit; allowing support-only staff to scan; using override to hide duplicate/unauthorized admission; changing event ownership/edit permissions.

**Audit/evidence:** Retain event/ticket internal IDs, result/reason code, scan/check-in attempt IDs, actor user ID, UTC time, device/context, and override notes. Escalate multiple successful scans, credential leakage, unauthorized actor, widespread scan failure, or contradictory ticket/check-in state as an incident.

## Workflow 6: payment manual-review issue

**Identify and verify:** Match internal/public order references, buyer, provider and method, stored payment reference, amount, currency, order state, every payment attempt, authenticity/verification state, and prior audits. Provider evidence must come from an authenticated provider channel, never a screenshot supplied by the buyer.

**Permitted now:** Put the case in `waiting_on_payment_provider` or `investigating`, flag fraud review, preserve evidence, and leave fulfillment unchanged. Run read-only reconciliation reporting.

**Prohibited now:** Live MMG is disabled and official lookup/authenticity behavior is unimplemented. Do not use manual MMG verification operationally, mark an order paid, issue tickets, or reconcile it as confirmed without authoritative provider verification. A matching typed reference/amount/currency is necessary but not proof of payment.

**Audit/evidence:** Record all compared fields, the provider evidence location, discrepancy class, and decision reason. Escalate paid/provider-pending, amount/currency mismatch, duplicate reference, callback anomaly, unexpected fulfillment, or financial impact.

## Workflow 7: refund issue

**Identify and verify:** Confirm requester authority, internal/public order reference, current ticket owner where relevant, order completed/verified state, event timing/status and policy, currency/full order total, existing refund/dispute records, ticket transfer/check-in/void state, payout status, and provider reference/status.

**Permitted:** Open/reopen refund review; approve, reject, or provider-confirm only through existing admin endpoints after the payment SOP checks and a mandatory case reason; keep MMG refunds pending while the live provider operation is unavailable; reconcile only after authoritative confirmation.

**Prohibited:** Direct row edits; partial or per-ticket refunds; treating approval/submission as provider completion; inventing a provider refund reference; retrying an ambiguous provider request; promising timing/fees not established by policy; automatically invalidating an already checked-in ticket without escalation. Historical partial records require manual reconciliation and must not be topped up through another partial refund.

**Audit/evidence:** Record refund/order IDs, amount/currency, reason, eligibility findings, provider evidence, approval/rejection rationale, prior attempts, and final reconciliation. Because not every refund endpoint creates a separate `admin_action_audits` row, the support-case note is mandatory. Escalate ambiguity, duplicate reference, disputed payment, post-payout refund, checked-in/transferred ticket, or provider mismatch.

## Workflow 8: suspicious or fraudulent activity

**Identify and verify:** Preserve the report and correlate internal user/event/order/ticket/payment/transfer IDs, request IDs, IP/request metadata available in logs, audit history, failed/successful attempts, and deploy timeline. Minimize copied personal data.

**Permitted:** Flag the order for fraud review with a reason, set urgent priority, hold operational financial actions, stop repeating a harmful admin action, and declare an incident when scope, account compromise, payment, or admission integrity may be affected.

**Prohibited:** Accusing the user as fact before investigation; deleting evidence; revealing detection logic; changing payment/ticket ownership; revoking infrastructure credentials without incident authorization; using event-staff status as proof of event ownership.

**Audit/evidence:** Record claims versus verified facts, preserved evidence links, affected IDs, containment, financial/admission exposure, and escalation owner. Follow the incident runbook for credential compromise, administrator misuse, automation at scale, or multiple affected entities.

## Transfer dispute decision procedure

1. Obtain the ticket's internal or display/public ID and its order. Verify the sender through the authenticated account and `sender_user_id`; verify the intended recipient through their authenticated, active, verified Admitly account and normalized recipient email. Do not disclose the full recipient address to the sender beyond information already shown by the product.
2. Inspect the ticket's `purchaser_user_id`, current `owner_user_id`, `transferred_at`, `transfer_count`, status/check-in state, and order paid/refund state. Ownership is the current `owner_user_id`, not necessarily the purchaser.
3. Inspect every invite for the ticket: sender/recipient IDs, masked email context, status (`pending`, `accepted`, `declined`, `canceled`, `expired`), timestamps, and accepted/declined/canceled actor. Inspect support/admin audit and check-in history.
4. If pending, only the sender may cancel and only the intended recipient may accept/decline through supported flows. Admin support may resend the latest pending invite after identity and consent checks; a resend does not change ownership.
5. If accepted, confirm that current owner equals the accepted recipient and that credentials were rotated. Do not manually reverse or reassign ownership. If those facts disagree, declare an admission-integrity incident.
6. If checked in, refunded, voided, ownership has changed again, or claims/evidence are ambiguous, freeze support action, tell both parties not to share/use the ticket, retain evidence, and escalate. Never decide ambiguous ownership from possession of a screenshot, QR code, or email thread alone.
7. Record both identity checks, current owner, transfer/invite IDs and statuses, check-in state, evidence links, decision, and exact response. Do not copy QR tokens into the case.

## Support lookup limitation and safe future improvement

The deployed workspace cannot resolve a public order reference, event, email, or ticket public ID to an order; it accepts a numeric order ID only. Although the snapshot response includes `order_reference`, the current admin UI neither displays it nor accepts it for lookup. Operators must obtain the internal order ID through an already-authorized reporting/support context and then cross-check the public reference in the API data. Do not use unrestricted SQL or broad user search as a workaround.

A future implementation should be a separate admin-only, rate-limited, audited exact-match resolver with minimum fields and bounded results:

- public order reference -> one order;
- ticket display/public ID -> its order (never QR token/payload);
- event ID -> paginated orders, not free-text event search;
- normalized full email -> bounded orders only after an operator supplies a case ID/reason.

It must not support fuzzy/wildcard email search or return passwords, tokens, raw QR data, payment payloads, or unrelated profile data. This requires backend and UI tests and is not a documentation-only change.

## Sensitive-action review and escalation

For manual payment verification, refunds, financial adjustments, event cancellation/refund batches, ticket void/check-in override, promo removal, fraud flags, and reconciliation/payout changes:

1. Write the mandatory reason and source evidence before acting.
2. Re-read target IDs, amount/currency, current state, expected transition, eligibility, and downstream notification/ticket effects.
3. With one admin, record `single-admin second-pass completed` plus UTC time. This is not independent approval.
4. Execute once. Reload state and audit history before any retry. An unknown/timeout result is ambiguous; investigate rather than retrying blindly.
5. Preserve action/audit IDs and the post-action state.

Introduce durable two-person approval only when another trusted administrator exists. Until then, ambiguous financial actions and conflicts of interest must be held for external owner/accountant/counsel review rather than self-approved under pressure.
