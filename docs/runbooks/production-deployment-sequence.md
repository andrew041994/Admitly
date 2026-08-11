# Production deployment sequence

This is a future operator procedure. It does not authorize a deployment, migration, callback, payment, notification, or configuration change.

## Compatibility matrix

| Combination | Compatibility |
| --- | --- |
| Existing backend + schema 0039 | Compatible after the 0039 preflight succeeds. Migration 0039 is additive, and retained server defaults supply `payment_attempts.authenticity_status` and `refunds.provider_status` for old inserts. New uniqueness constraints can reject a newly duplicated provider reference, which is safe but may surface as an old-backend conflict response. |
| New backend + schema 0038 | Not compatible. New ORM queries and inserts reference payment-attempt and refund columns introduced by 0039. |
| New backend + schema 0039 | Compatible and required target state. |
| New admin + existing backend | Not fully compatible. The new support UI expects payment-attempt authenticity data and new payment/refund operations supplied by the new backend. |
| New mobile + existing backend | Core auth/order APIs remain compatible, but do not release clients ahead of the backend hardening and production configuration verification. |

The retained database defaults are intentional expand-first compatibility protections. Do not remove them until all old backend versions are permanently retired, and then only through a later reviewed migration.

## Recommended order

1. Freeze the exact reviewed source commit and record backend/admin/mobile release identifiers.
2. Confirm backup/restore readiness and the Render rollback target.
3. Validate the production configuration through the local preflight command using a securely obtained local env export:

   ```bash
   backend/.venv/bin/python scripts/verify_production_safety.py --production-env-file /secure/path/production.env
   ```

4. Run [migration-0039-preflight.md](migration-0039-preflight.md) through a verified SELECT-only Neon role.
5. Resolve and recheck every blocking result. Do not continue with exact duplicates.
6. Keep `MMG_ENABLED=false` while the official provider implementation remains unavailable.
7. Begin a short payment/refund write-maintenance window. This closes the race between the final duplicate query and unique-constraint creation and limits exposure to non-concurrent DDL locks.
8. Apply migration 0039 using the approved production migration procedure.
9. Verify the database reports exactly `20260811_0039`, both unique constraints exist, and the retained defaults are present. Do not run application writes as a migration test.
10. Deploy the new backend release immediately after the migration.
11. Perform non-financial smoke checks: health, request ID, CORS allow/deny behavior, authentication authorization boundaries using an approved test account, logs, and Sentry controlled test procedure. Do not invoke payment callbacks or real notifications.
12. End the maintenance window only after backend health and safety checks pass.
13. Deploy the admin bundle. Verify the public legal routes, API base URL, Sentry release, support payment-attempt display, and absence of test-checkout paths.
14. Produce signed mobile builds from the same approved release. Test Android/iOS physically before staged store release. Do not use OTA to introduce native SecureStore or Sentry dependencies.
15. Complete push, organizer, transfer, scan, and—after MMG is officially integrated—payment lifecycle verification before final release sign-off.

## Rollback points

- **Before migration:** abort without database or service changes.
- **After migration, before backend deployment:** leave schema 0039 in place and restore normal service on the old backend if necessary. Retained defaults keep old payment-attempt/refund inserts compatible. Investigate any uniqueness conflict rather than weakening the constraint.
- **After backend deployment:** roll the backend back to the recorded old release while keeping schema 0039. This is the preferred application rollback.
- **After admin deployment:** roll back the static admin bundle independently; it has no direct database dependency.
- **During mobile rollout:** pause/stage the store rollout. Previously installed clients remain API-compatible, but any binary exposing development checkout must not be promoted.
- **Database downgrade:** last resort only. First restore the old backend and stop new writes. Downgrade 0039 removes callback authenticity and refund provider audit data, so it requires explicit incident approval and preservation of relevant records before execution.

## Downtime and lock considerations

The unique constraints and refund reference index are created non-concurrently. Even with clean data, PostgreSQL must scan/lock the affected tables. Measure table size and lock behavior on a production-like copy, set an approved lock timeout at the operational layer, and use a short maintenance window rather than assuming zero downtime.
