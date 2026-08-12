# Incident-response procedure

This runbook is for operational incidents affecting Admitly. Use UTC throughout. It does not authorize an operator to bypass access controls, edit database rows directly, expose credentials, or perform financial actions without the checks in the payment runbook.

## Severity and escalation

Classify by the highest applicable impact. Reassess whenever scope or financial/data-integrity risk changes.

| Severity | Definition | Admitly examples | Response target |
| --- | --- | --- | --- |
| **SEV1** | Active platform-wide or safety-critical outage; confirmed or credible security compromise; financial or admission integrity at risk; destructive or widespread data loss. | Checkout broadly unavailable during active sales; duplicate ticket issuance; unauthorized ticket admission or reusable ticket credentials; incorrect paid/refunded state affecting multiple orders; confirmed administrator/account compromise; production database corruption. | Declare immediately. Work continuously. Update at least every 15 minutes. |
| **SEV2** | A core workflow is materially degraded for a meaningful set of users, but impact is contained or a safe workaround exists. | Login outage for a subset of users; event creation/publishing unavailable; check-in degraded with an approved manual venue process; broad email/push failure near an event; a single event's checkout failing; payment reconciliation backlog without incorrect fulfillment. | Declare promptly. Update at least every 30 minutes. |
| **SEV3** | Limited impact, no known safety/financial/data-integrity risk, and a reasonable workaround exists. | Isolated admin-only display issue; delayed non-time-critical email/push; one support case; cosmetic event-creation defect; reporting mismatch that does not change stored financial state. | Track to resolution during normal operations. Escalate if scope grows. |

A suspected duplicate ticket, unauthorized admission, payment-state corruption, or unexplained data mutation starts at SEV1 until disproved. An admin-only problem becomes SEV1 or SEV2 if it prevents incident containment, event-day admission, refund review, or financial reconciliation.

## Roles

Assign roles at declaration. While Admitly has one primary administrator, one person may hold every role; say so in the incident record and deliberately switch hats before approving a high-impact decision. Split the roles as additional operators become available.

- **Incident commander:** owns severity, priorities, decision log, approvals, update cadence, and closure.
- **Technical/operator lead:** gathers evidence, diagnoses, contains, rolls back or applies the reviewed recovery procedure, and runs verification.
- **Communications lead:** sends accurate, minimum-necessary internal, customer, and event-creator updates.
- **Scribe:** maintains the UTC timeline, links evidence, records hypotheses separately from facts, and captures every state-changing action.
- **Finance reviewer:** for payment, refund, duplicate fulfillment, payout, or reconciliation impact, validates amounts/references and decides whether financial processing must remain held. While there is one administrator this is a documented second-pass review by the same operator, not independent approval. Independent two-person review is a future scaling control.

## Declaration, detection, and evidence

Detection sources are the backend and admin Sentry projects, Render API/worker logs and deploy history, Neon metrics/branch history, Render Key Value/Redis health, request IDs in responses and logs, `admin_action_audits`, support-case notes/timeline, check-in attempts/scan logs, and customer or event-creator reports. There is no repository-defined public status page.

Immediately record:

- incident ID, severity, UTC detection/declaration time, reporter, assigned roles, and latest known healthy time;
- observed user impact, affected endpoints/workflows/events, scope estimate, and workaround status;
- current API deploy ID and commit SHA, relevant worker deploy IDs/SHAs, admin release, and Alembic revision;
- representative request/correlation IDs, Sentry issue/event links, sanitized Render log links, and screenshots;
- internal event, order, ticket, payment-attempt, refund, transfer, or support-case IDs needed to reproduce the issue—never QR tokens, credentials, raw callback payloads, or unnecessary personal data;
- confirmed and potential financial impact: affected order count, currency, gross amount, refunds/payouts at risk, and whether ticket fulfillment or admission may be wrong;
- every containment/recovery action, operator, UTC time, expected effect, actual result, and approval.

Preserve the original evidence. Do not paste secrets, full provider payloads, access tokens, email contents, or customer payment evidence into general chat or issue trackers.

## Initial triage

1. Confirm the symptom with a harmless request or the smallest safe reproduction. Do not create orders, send notifications, or mutate tickets merely to test.
2. Correlate a request ID across the client error, Render JSON logs, and Sentry. Compare the first failing time with Render deploy history and configuration-event history.
3. Check `/health`, database connectivity/revision, Redis/rate-limiter errors, and the affected dependency. A healthy `/health` does not prove checkout, ticket issuance, or a worker is healthy.
4. Establish whether the problem is read-path, write-path, delivery-only, financial-state, admission-state, or data-integrity related.
5. If payment or ticket integrity is uncertain, hold manual verification, refunds, reconciliation completion, and payouts until the finance review is complete.

## Read-only database health query pack

Use a Neon SELECT-only role. Run with `psql -X --set ON_ERROR_STOP=on` so a missing table or failed query stops the pack. Do not include connection strings in the incident record. Every statement is inside a read-only transaction and the session ends with `ROLLBACK`.

```sql
BEGIN TRANSACTION READ ONLY;

-- Connectivity and transaction safety. transaction_read_only must be on.
SELECT
    now() AT TIME ZONE 'UTC' AS checked_at_utc,
    current_database() AS database_name,
    current_user AS validation_role,
    current_setting('transaction_read_only') AS transaction_read_only;

-- Exactly one revision is expected. Record the value; do not run Alembic here.
SELECT version_num FROM alembic_version;

-- Every relation must be non-NULL.
WITH critical_tables(table_name) AS (
    VALUES
        ('users'), ('organizer_profiles'), ('events'), ('orders'),
        ('order_items'), ('payment_attempts'), ('tickets'), ('refunds'),
        ('ticket_transfer_invites'), ('ticket_check_in_attempts'),
        ('ticket_scan_logs'), ('admin_action_audits')
)
SELECT table_name, to_regclass(format('public.%I', table_name)) AS relation
FROM critical_tables
ORDER BY table_name;

-- Record recent volume and compare it with the same time window before the incident.
SELECT 'orders' AS entity, count(*) AS last_60_minutes
FROM orders WHERE created_at >= now() - interval '60 minutes'
UNION ALL
SELECT 'tickets', count(*) FROM tickets WHERE created_at >= now() - interval '60 minutes'
UNION ALL
SELECT 'payment_attempts', count(*) FROM payment_attempts WHERE created_at >= now() - interval '60 minutes'
UNION ALL
SELECT 'refunds', count(*) FROM refunds WHERE created_at >= now() - interval '60 minutes'
ORDER BY entity;

-- Expect zero duplicate groups. References are fingerprinted rather than displayed.
SELECT
    payment_provider,
    md5(payment_reference) AS reference_fingerprint,
    count(*) AS row_count,
    array_agg(id ORDER BY id) AS order_ids
FROM orders
WHERE payment_provider IS NOT NULL AND payment_reference IS NOT NULL
GROUP BY payment_provider, payment_reference
HAVING count(*) > 1;

SELECT
    payment_provider,
    md5(provider_refund_reference) AS reference_fingerprint,
    count(*) AS row_count,
    array_agg(id ORDER BY id) AS refund_ids
FROM refunds
WHERE payment_provider IS NOT NULL AND provider_refund_reference IS NOT NULL
GROUP BY payment_provider, provider_refund_reference
HAVING count(*) > 1;

-- Completed orders must have one ticket for every ordered unit. Expect zero rows.
WITH fulfillment AS (
    SELECT
        o.id AS order_id,
        o.event_id,
        COALESCE(sum(oi.quantity), 0) AS ordered_quantity,
        (SELECT count(*) FROM tickets t WHERE t.order_id = o.id) AS ticket_count
    FROM orders o
    LEFT JOIN order_items oi ON oi.order_id = o.id
    WHERE o.status = 'completed'
    GROUP BY o.id, o.event_id
)
SELECT *
FROM fulfillment
WHERE ordered_quantity <> ticket_count
ORDER BY order_id;

-- Paid-state consistency. Investigate every non-zero count before financial work resumes.
SELECT
    count(*) FILTER (
        WHERE status = 'completed' AND payment_verification_status <> 'verified'
    ) AS completed_not_verified,
    count(*) FILTER (
        WHERE payment_verification_status = 'verified' AND status <> 'completed'
    ) AS verified_not_completed,
    count(*) FILTER (
        WHERE status = 'completed'
          AND total_amount > 0
          AND is_comp IS FALSE
          AND paid_at IS NULL
    ) AS paid_order_without_paid_at,
    count(*) FILTER (
        WHERE payment_reference IS NOT NULL AND payment_provider IS NULL
    ) AS reference_without_provider
FROM orders;

-- Payment attempts must belong to an order and agree when both sides have identifiers.
SELECT
    count(*) FILTER (WHERE o.id IS NULL) AS attempts_missing_order,
    count(*) FILTER (
        WHERE o.id IS NOT NULL
          AND o.payment_provider IS NOT NULL
          AND pa.provider <> o.payment_provider
    ) AS provider_mismatches,
    count(*) FILTER (
        WHERE o.id IS NOT NULL
          AND o.payment_reference IS NOT NULL
          AND pa.provider_reference IS NOT NULL
          AND pa.provider_reference <> o.payment_reference
    ) AS reference_mismatches
FROM payment_attempts pa
LEFT JOIN orders o ON o.id = pa.order_id;

-- Obvious ticket/check-in state contradictions. Every count should be zero.
SELECT
    count(*) FILTER (
        WHERE check_in_status = 'checked_in' AND checked_in_at IS NULL
    ) AS checked_in_without_timestamp,
    count(*) FILTER (
        WHERE check_in_status = 'not_checked_in' AND checked_in_at IS NOT NULL
    ) AS timestamp_without_checked_in,
    count(*) FILTER (
        WHERE status = 'checked_in' AND check_in_status <> 'checked_in'
    ) AS ticket_status_mismatch,
    count(*) FILTER (
        WHERE check_in_status = 'checked_in' AND checked_in_by_user_id IS NULL
    ) AS checked_in_without_actor
FROM tickets;

-- More than one successful scan for a ticket is an admission-integrity concern.
SELECT ticket_id, count(*) AS successful_scan_count
FROM ticket_scan_logs
WHERE status = 'SUCCESS' AND ticket_id IS NOT NULL
GROUP BY ticket_id
HAVING count(*) > 1
ORDER BY ticket_id;

ROLLBACK;
```

A query failure, missing table, unexpected revision, non-zero anomaly count, or unexplained row is evidence—not permission to repair it. Preserve sanitized results and escalate. Use the Neon recovery runbook only when recovery is explicitly approved.

## Containment

Choose the least invasive supported option and record the authorization. Preserve evidence before changing state when safe.

Supported controls:

- Pause Render automatic deploys in the dashboard and stop initiating new deploys while diagnosis is active.
- Roll back the API and any affected worker using [render-rollback.md](render-rollback.md) after schema/security compatibility review.
- Keep MMG disabled with `MMG_ENABLED=false`. If MMG is ever enabled, an authorized production configuration change back to false followed by the platform-required restart/deploy is the supported kill switch; capture the before/after setting state without its secrets.
- Hold manual payment verification, reconciliation completion, refunds, payouts, and event refund batches operationally. Do not invoke those endpoints while the hold is active.
- Stop the operator from repeating a harmful admin action, sign out the affected local admin session, preserve its audit trail, and begin credential/session containment under the security incident process. Local sign-out alone does not revoke an already stolen token.
- Email and push delivery have supported enable/provider settings, but changing them affects all delivery and requires an authorized configuration change. Use only when delivery itself is causing harm, not as a general incident switch.
- A separately deployed notification worker may be suspended or rolled back in Render when it is the failing component. Record queued-message impact before doing so.

Unavailable controls:

- There is no repository-defined global maintenance mode or checkout-only kill switch.
- There is no supported pause switch for callback processing, ticket issuance, event creation, or check-in independent of the API.
- Do not simulate a missing switch by editing database rows, changing routes ad hoc, blocking arbitrary traffic, or disabling authentication.

If safe containment requires an unavailable control, decide between a schema-compatible rollback, temporarily suspending the whole API through an authorized Render action, or a reviewed forward fix. A full service suspension is a SEV1 decision because it blocks all workflows.

## Communications templates

Do not claim a cause, resolution time, refund, or data breach before it is confirmed. Use the existing support channels; Admitly has no declared public status page.

**Internal declaration**

> `[SEV#] [INC-ID] declared at [UTC]. Impact: [confirmed impact and scope]. First observed: [UTC]. Incident commander: [name]. Technical lead: [name]. Financial/data-integrity risk: [yes/no/unknown]. Current containment: [action/none]. Next update: [UTC]. Evidence: [restricted link].`

**Customer-facing outage/update**

> `We are investigating an issue affecting [workflow] that began around [UTC]. [What still works / safe workaround, if confirmed]. Please do not repeat [checkout/transfer/check-in action] while we investigate. We will provide another update by [UTC].`

**Event-creator update**

> `Admitly is investigating [workflow] for [event reference/title]. Current confirmed impact: [scope]. [Admission/sales guidance, only if approved]. Preserve any relevant order or ticket references and do not share QR codes. Next update: [UTC].`

**Resolved message**

> `The issue affecting [workflow] was resolved at [UTC]. Service has remained stable for [observation period]. Confirmed impact: [scope]. [Any specific customer next step]. We are reviewing the incident and will contact affected users directly if further action is required.`

## Recovery, observation, and closure

1. Recover using the relevant rollback, Neon recovery, storage, or payment runbook. Never combine diagnosis with unreviewed data repair.
2. Verify the affected path plus `/health`, production CORS, invalid login, request IDs, Redis/rate limiting, structured logs, Sentry, Alembic revision, and absence of schema errors. For financial/admission incidents, reconcile affected orders and ticket/check-in state read-only before writes resume.
3. Observe a SEV1 recovery for at least 60 minutes and a SEV2 recovery for at least 30 minutes. Extend through the next peak-sales or event-admission window when the fault was load- or time-dependent. SEV3 requires the affected check to remain stable through one normal verification cycle.
4. During observation, require no recurrence in Sentry/Render, stable health and dependency errors, normal latency/error rate for the affected endpoint, no growing reconciliation/notification backlog, and no new financial or ticket-integrity anomalies.
5. Preserve the UTC timeline, decision log, deploy/config history, request IDs, Sentry and sanitized log links, read-only query results, communications, affected internal IDs, financial impact calculation, and verification evidence in the restricted incident record.
6. The incident commander declares resolved only after the technical lead's checks and, where relevant, the finance review. Record remaining customer remediation separately.
7. For SEV1 and SEV2, complete an internal postmortem within five business days: impact, timeline, root cause, contributing factors, detection and response gaps, what worked, corrective actions with owner/due date, and evidence-retention location. SEV3 needs a concise review when recurring or control-relevant.

Security or privacy incidents also require a documented legal assessment of notification obligations and evidence retention. Do not promise notification timing or legal conclusions without counsel.
