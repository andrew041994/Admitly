# Neon backup and restore runbook

Owner: on-call engineer. Approver for production restore: incident commander plus product/finance owner.

## Recovery architecture

Neon's primary recovery mechanism for Admitly is a point-in-time branch created from the production branch's retained history. A drill must create a separate branch and compute at a chosen UTC timestamp inside the configured restore window. It must never reset, restore, rename, reparent, or replace the production branch.

The current Neon console may also show manual or scheduled snapshots under **Backup & Restore**. Snapshot availability, scheduling, and retention depend on the project plan and configuration. Treat snapshots as an additional recovery source only after recording an actual snapshot and successfully restoring it to a separate preview branch. Do not assume snapshots exist merely because the console supports them.

For this repository, a recent drill performed after the current production migration should report Alembic revision `20260811_0039`. An incident recovery point may legitimately contain an older revision; in that case, select a backend release compatible with that recovered schema and do not migrate during validation.

## Proposed business targets

These are proposed initial targets, not approved service-level requirements:

- **RPO: 5 minutes.** At most five minutes of committed ticketing/payment activity should require reconstruction from provider records, logs, or support evidence.
- **RTO: 60 minutes.** Within one hour of declaring a database recovery incident, operators should have a validated recovery branch and either restore service on a compatible branch or have an incident commander-approved forward-recovery plan.

Product, finance, and engineering must approve these targets. Measure monthly drills before making contractual availability claims. If repeated drills cannot meet them, adopt an interim target and record the funded work needed to close the gap.

## Routine readiness

1. Confirm the production branch, project, region, retention window, and protected-branch settings in Neon. Record them in the private infrastructure inventory; never put connection strings in this repository.
2. Keep a separately controlled break-glass database role. Test access quarterly and after owner changes.
3. Confirm the configured restore window is longer than the approved RPO and long enough for realistic incident detection. Record any scheduled snapshot frequency and retention separately.
4. Monthly, create a temporary recovery branch from a named historical timestamp, connect with read-only credentials, and run the validation below.
5. Record the restore point, actual recovery-point age, tester, duration, validation results, and eventual deletion status using [neon-recovery-drill-evidence.md](neon-recovery-drill-evidence.md).

## Non-destructive console drill

1. Obtain operator approval. Open the Neon Console and select the Admitly production project. Start a UTC timer and record the project ID, region, production branch name/ID, and current production branch badge without copying any connection string into tickets or chat.
2. Open **Branches**, select the production branch, and record whether the protected-branch shield is present. Do not click Reset, Restore, Unprotect, Delete, or Set as default.
3. Open **Settings → Restore window** (or **Backup & Restore → Configure**, if that is how the current console links to it). Record the configured instant-restore window; do not change it.
4. Open **Backup & Restore** and record whether scheduled snapshots exist, their most recent successful timestamp, frequency, and retention. Do not create, restore, reschedule, or delete a snapshot during a PITR-branch drill.
5. Choose a recovery timestamp in UTC that is inside the restore window, after migration `20260811_0039`, and old enough to measure recovery-point age (normally 5–15 minutes before the drill). Record it before creating anything.
6. Open **Branches → New branch**. Set the parent/source to the production branch, choose historical **Time/Timestamp**, enter the recorded UTC timestamp, and name the branch `recovery-drill-YYYYMMDD-HHMM-utc`. Enable a separate compute endpoint for that new branch. Review the summary and confirm that the operation says it will create a new branch—not reset or restore the source branch—before submitting.
7. Wait for the new branch and compute to become ready. Record the recovery branch ID and branch-ready time. Because production may be protected, Neon can generate different passwords for roles on the child branch; obtain connection details only from the recovery branch's **Connect** dialog.
8. Prefer an existing SELECT-only validation role on the recovery branch. If only an owner credential is available, do not create or alter roles during the drill. Connect with `psql`, immediately execute the transaction below, and stop if `transaction_read_only` is not `on`.
9. Run every validation query in the same read-only transaction. Do not run Alembic commands against the branch; read `alembic_version` directly.
10. Record the verification end time, actual RPO (branch creation time minus chosen recovery timestamp), actual RTO (drill start through completed validation), sanitized results, and evidence location.
11. Leave the recovery branch in place for the approver to review. An authorized Neon operator may later delete only the recorded recovery branch after independently matching its name and branch ID. Never delete the production branch. Record who deleted the temporary branch and when; do not automate deletion from this runbook.

## Read-only validation SQL

Run with `psql -X --set ON_ERROR_STOP=on` against only the temporary recovery branch. Do not put the connection string in shell history, logs, or the evidence record. Paste the following as one session:

```sql
BEGIN TRANSACTION READ ONLY;

SELECT
    current_user AS validation_role,
    current_setting('transaction_read_only') AS transaction_read_only,
    pg_is_in_recovery() AS postgres_replica_mode;

-- Must return transaction_read_only = on. A dedicated validation role should
-- have SELECT=true and all write privileges=false for every listed table.
WITH critical_tables(table_name) AS (
    VALUES
        ('users'), ('events'), ('orders'), ('payment_attempts'),
        ('tickets'), ('refunds'), ('financial_entries')
)
SELECT
    table_name,
    has_table_privilege(current_user, format('public.%I', table_name), 'SELECT') AS can_select,
    has_table_privilege(current_user, format('public.%I', table_name), 'INSERT') AS can_insert,
    has_table_privilege(current_user, format('public.%I', table_name), 'UPDATE') AS can_update,
    has_table_privilege(current_user, format('public.%I', table_name), 'DELETE') AS can_delete,
    has_table_privilege(current_user, format('public.%I', table_name), 'TRUNCATE') AS can_truncate
FROM critical_tables
ORDER BY table_name;

-- Exactly one row is expected. For a recent drill it must be 20260811_0039.
SELECT version_num FROM alembic_version;

-- Every regclass must be non-NULL.
WITH critical_tables(table_name) AS (
    VALUES
        ('users'), ('events'), ('orders'), ('payment_attempts'),
        ('tickets'), ('refunds'), ('financial_entries')
)
SELECT table_name, to_regclass(format('public.%I', table_name)) AS relation
FROM critical_tables
ORDER BY table_name;

-- Record and compare these counts with the latest approved production baseline.
SELECT
    (SELECT count(*) FROM users) AS users,
    (SELECT count(*) FROM events) AS events,
    (SELECT count(*) FROM orders) AS orders,
    (SELECT count(*) FROM payment_attempts) AS payment_attempts,
    (SELECT count(*) FROM tickets) AS tickets,
    (SELECT count(*) FROM refunds) AS refunds,
    (SELECT count(*) FROM financial_entries) AS financial_entries;

-- Referential and event/order consistency anomaly counts should all be zero.
SELECT
    count(*) FILTER (WHERE o.id IS NULL) AS tickets_missing_order,
    count(*) FILTER (WHERE oi.id IS NULL) AS tickets_missing_order_item,
    count(*) FILTER (WHERE e.id IS NULL) AS tickets_missing_event,
    count(*) FILTER (WHERE o.id IS NOT NULL AND t.event_id <> o.event_id) AS ticket_order_event_mismatch,
    count(*) FILTER (WHERE oi.id IS NOT NULL AND t.order_id <> oi.order_id) AS ticket_order_item_mismatch,
    count(*) FILTER (WHERE oi.id IS NOT NULL AND t.ticket_tier_id <> oi.ticket_tier_id) AS ticket_tier_item_mismatch
FROM tickets t
LEFT JOIN orders o ON o.id = t.order_id
LEFT JOIN order_items oi ON oi.id = t.order_item_id
LEFT JOIN events e ON e.id = t.event_id;

-- Completed orders should have one ticket per ordered quantity. Expect zero.
WITH completed_order_counts AS (
    SELECT
        o.id,
        COALESCE((SELECT sum(oi.quantity) FROM order_items oi WHERE oi.order_id = o.id), 0) AS ordered_quantity,
        (SELECT count(*) FROM tickets t WHERE t.order_id = o.id) AS ticket_count
    FROM orders o
    WHERE o.status = 'completed'
)
SELECT count(*) AS completed_order_ticket_count_mismatches
FROM completed_order_counts
WHERE ordered_quantity <> ticket_count;

-- Payment attempts must resolve to an order. Provider/reference mismatch counts
-- should be zero or have a documented, reviewed explanation for historical attempts.
SELECT
    count(*) FILTER (WHERE o.id IS NULL) AS payment_attempts_missing_order,
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
    ) AS provider_reference_mismatches
FROM payment_attempts pa
LEFT JOIN orders o ON o.id = pa.order_id;

-- Sanitized recent order samples: internal IDs and financial/status fields only.
SELECT
    o.id AS order_id,
    o.status,
    o.currency,
    o.total_amount,
    COALESCE((SELECT sum(oi.quantity) FROM order_items oi WHERE oi.order_id = o.id), 0) AS ordered_quantity,
    (SELECT count(*) FROM tickets t WHERE t.order_id = o.id) AS ticket_count,
    (SELECT count(*) FROM payment_attempts pa WHERE pa.order_id = o.id) AS payment_attempt_count
FROM orders o
ORDER BY o.id DESC
LIMIT 10;

-- Sanitized payment/order samples; do not select provider_reference or payloads.
SELECT
    pa.id AS payment_attempt_id,
    pa.order_id,
    pa.provider,
    pa.status AS payment_status,
    pa.verification_status,
    pa.authenticity_status,
    (pa.provider_reference IS NOT NULL) AS provider_reference_present,
    o.status AS order_status,
    o.currency,
    o.total_amount
FROM payment_attempts pa
JOIN orders o ON o.id = pa.order_id
ORDER BY pa.id DESC
LIMIT 10;

-- Refunds must resolve to orders; approved/processed totals must not exceed the order total.
SELECT count(*) AS refunds_missing_order
FROM refunds r
LEFT JOIN orders o ON o.id = r.order_id
WHERE o.id IS NULL;

WITH refund_totals AS (
    SELECT r.order_id, sum(r.amount) AS refunded_amount
    FROM refunds r
    WHERE r.status IN ('approved', 'processed')
    GROUP BY r.order_id
)
SELECT count(*) AS orders_over_refunded
FROM refund_totals rt
JOIN orders o ON o.id = rt.order_id
WHERE rt.refunded_amount > o.total_amount;

ROLLBACK;
```

A clean drill has `transaction_read_only=on`, one expected Alembic revision, all required relations present, no unexplained row-count drop from the recorded baseline, zero referential/ticket-quantity/refund anomalies, and payment/provider mismatches either zero or explicitly reconciled. `pg_is_in_recovery()` may be false on a writable Neon branch and is not the read-only control; the transaction setting and role privileges are the relevant evidence.

## Restore during an incident

1. Declare the incident, stop writes or put the API into maintenance mode, and record the UTC cutoff and current database branch ID.
2. Preserve the damaged branch. Do not delete or overwrite it.
3. In Neon, create a new branch from the latest restore point before the incident. Use a new branch so the operation is reversible.
4. Run `alembic current` and compare with `alembic heads`. Do not migrate until the application version and target schema have been confirmed.
5. Validate critical counts and sample order-to-ticket/payment ledger relationships using read-only queries. Finance must validate a sample of settled MMG references.
6. Update the Render database secret to the restored branch, redeploy the known-compatible release, and run health plus read-only smoke tests before restoring writes.
7. Monitor errors, latency, checkout callbacks, notification jobs, and reconciliation. Retain the old branch until the incident review authorizes deletion.

Never restore production data into an unsecured local machine. Mask personal data in non-production recovery exercises.
