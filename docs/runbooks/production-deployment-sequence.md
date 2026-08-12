# Production deployment sequence

This is a future operator procedure. It does not authorize a deployment, migration, callback, payment, notification, or configuration change.

## Compatibility matrix

| Combination | Compatibility |
| --- | --- |
| Existing deployed backend + schema 0040 | Database-compatible. Migration 0040 is additive and its new non-null verification status has a retained `pending` server default. The old backend does not enforce the new age-verification publication/discovery policy, so do not perform event approval/publication while it is serving. |
| Age-verification backend + schema 0039 | Not compatible. ORM event reads reference columns introduced by 0040. |
| Age-verification backend + schema 0040 | Compatible and required target state. Existing events remain stored and unverified; no event is auto-verified. Approved-but-unverified events are hidden from discovery until reviewed. |
| Age-verification admin + existing backend | Not compatible for event approvals because the verification endpoint and response fields are absent. Deploy it only after the backend. |
| New mobile + existing backend | Core auth/order APIs remain compatible, but do not release clients ahead of the backend hardening and production configuration verification. |

The retained database defaults are intentional expand-first compatibility protections. Do not remove them until all old backend versions are permanently retired, and then only through a later reviewed migration.

## Recommended order

1. Freeze the exact reviewed source commit and record backend/admin/mobile release identifiers.
2. Confirm backup/restore readiness and the Render rollback target.
3. Validate the production configuration through the local preflight command using a securely obtained local env export:

   ```bash
   backend/.venv/bin/python scripts/verify_production_safety.py --production-env-file /secure/path/production.env
   ```

4. Confirm production is still at `20260811_0039`, record counts of total events and approved events, and confirm the operator understands that 0040 does not auto-verify them. No ID data preflight or backfill is required.
5. Keep `MMG_ENABLED=false` while the official provider implementation remains unavailable.
6. Pause event approval/publication operationally for the short migration/backend transition. The repository has no feature-specific kill switch.
7. Apply migration 0040 using the approved production migration procedure. Do not run it through Codex or against an unverified database target.
8. Verify the database reports exactly `20260811_0040`; the five event verification columns, two foreign keys, two indexes, status check constraint, and retained `pending` server default exist.
9. Deploy the age-verification backend immediately after the migration. Until it is live, the old backend is schema-compatible but does not enforce the new policy.
10. Perform non-financial smoke checks: health, request ID, CORS, authentication, event creation as pending/draft through an approved test account, approval rejection before verification, logs, and Sentry. Do not send an ID, payment, or notification as a smoke test.
11. Deploy the age-verification admin bundle. Verify legal routes and that Event Approvals requires verification before approval and displays no ID upload/storage capability.
12. Manually review existing approved events. Record verification only after the email-ID process is completed; do not bulk backfill or auto-verify. Approved legacy events remain hidden from discovery until verified.
13. End the event approval/publication hold only after backend/admin verification passes.
14. Produce signed mobile builds only on the separately approved schedule. Do not use OTA to introduce native SecureStore or Sentry dependencies.

## Rollback points

- **Before migration:** abort without database or service changes.
- **After migration, before backend deployment:** leave schema 0040 in place. The old backend remains database-compatible, but keep event approval/publication operationally paused because it lacks the verification gate.
- **After backend deployment:** an application rollback may keep schema 0040, but it reintroduces the missing verification enforcement. Roll back only with event approval/publication held and a plan to restore the compliant backend promptly.
- **After admin deployment:** roll back the static admin bundle independently; it has no direct database dependency.
- **During mobile rollout:** pause/stage the store rollout. Previously installed clients remain API-compatible, but any binary exposing development checkout must not be promoted.
- **Database downgrade:** last resort only. Downgrading 0040 deletes verification metadata and audit notes from `events`; preserve required evidence and obtain explicit incident/privacy approval first. Routine rollback keeps schema 0040.

## Downtime and lock considerations

The unique constraints and refund reference index are created non-concurrently. Even with clean data, PostgreSQL must scan/lock the affected tables. Measure table size and lock behavior on a production-like copy, set an approved lock timeout at the operational layer, and use a short maintenance window rather than assuming zero downtime.
