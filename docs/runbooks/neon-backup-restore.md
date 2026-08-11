# Neon backup and restore runbook

Owner: on-call engineer. Approver for production restore: incident commander plus product/finance owner.

## Routine readiness

1. Confirm the production branch, project, region, retention window, and protected-branch settings in Neon. Record them in the private infrastructure inventory; never put connection strings in this repository.
2. Keep a separately controlled break-glass database role. Test access quarterly and after owner changes.
3. Monthly, create a temporary restore branch from a named restore point, connect with read-only credentials, and verify row counts for users, events, orders, payment attempts, tickets, refunds, and financial entries.
4. Record the restore point, tester, duration, validation results, and deletion of the temporary branch.

## Restore during an incident

1. Declare the incident, stop writes or put the API into maintenance mode, and record the UTC cutoff and current database branch ID.
2. Preserve the damaged branch. Do not delete or overwrite it.
3. In Neon, create a new branch from the latest restore point before the incident. Use a new branch so the operation is reversible.
4. Run `alembic current` and compare with `alembic heads`. Do not migrate until the application version and target schema have been confirmed.
5. Validate critical counts and sample order-to-ticket/payment ledger relationships using read-only queries. Finance must validate a sample of settled MMG references.
6. Update the Render database secret to the restored branch, redeploy the known-compatible release, and run health plus read-only smoke tests before restoring writes.
7. Monitor errors, latency, checkout callbacks, notification jobs, and reconciliation. Retain the old branch until the incident review authorizes deletion.

Never restore production data into an unsecured local machine. Mask personal data in non-production recovery exercises.
