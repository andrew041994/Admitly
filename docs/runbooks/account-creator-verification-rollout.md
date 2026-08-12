# Account-level creator verification rollout

Migration `20260812_0044` adds account-level creator age/identity verification and immutable verification history. It does not remove or rewrite event-level verification evidence.

## Deployment compatibility and order

1. Run the normal pre-deployment checks and take/confirm the database recovery point.
2. Apply migration `20260812_0044`.
3. Inspect the backfill results below before enabling event approval operations.
4. Deploy the matching backend.
5. Deploy the matching admin/web client, then mobile through the normal signed-build process when scheduled.

The old backend can read schema `0044` because the migration is additive, but it still treats verification as event-scoped. Pause event verification/approval during the migration-to-backend window. The new backend requires the new user columns and history table and must not run against schema `0043`.

## Deterministic legacy backfill

A user is backfilled to `verified` only when:

- at least one legacy event has status `verified`;
- every legacy event marked `verified` for that creator has a non-null verified user, verifier, and timestamp;
- every such verified-user value equals the user attached through the event's organizer profile.

For an eligible creator, the earliest complete verification timestamp is selected, with event ID as the deterministic tie-breaker. Its verifier and safe note are retained and one account verification-history record is created. Multiple consistent events do not create duplicate history.

If any verified legacy record is incomplete or points to a different user, that creator remains `pending`. No inference or automatic correction occurs. Existing event-level records remain untouched for manual review.

## Read-only post-migration checks

Run using a read-only role after migration:

```sql
BEGIN TRANSACTION READ ONLY;

SELECT creator_age_identity_verification_status, count(*)
FROM users
GROUP BY creator_age_identity_verification_status
ORDER BY creator_age_identity_verification_status;

SELECT count(*) AS verified_users_without_complete_metadata
FROM users
WHERE creator_age_identity_verification_status = 'verified'
  AND (
    creator_age_identity_verified_at IS NULL
    OR creator_age_identity_verified_by_user_id IS NULL
  );

SELECT count(*) AS verified_users_without_history
FROM users u
WHERE u.creator_age_identity_verification_status = 'verified'
  AND NOT EXISTS (
    SELECT 1
    FROM creator_age_identity_verification_history h
    WHERE h.user_id = u.id AND h.action = 'verified'
  );

SELECT op.user_id, array_agg(e.id ORDER BY e.id) AS event_ids
FROM events e
JOIN organizer_profiles op ON op.id = e.organizer_id
WHERE e.creator_age_identity_verification_status = 'verified'
  AND (
    e.creator_age_identity_verified_user_id IS DISTINCT FROM op.user_id
    OR e.creator_age_identity_verified_by_user_id IS NULL
    OR e.creator_age_identity_verified_at IS NULL
  )
GROUP BY op.user_id
ORDER BY op.user_id;

ROLLBACK;
```

The first query is inventory. Both count queries should return zero. The final query intentionally identifies ambiguous legacy creators who remain pending; review them manually and never bulk-verify them.

## Revocation operations

Revocation requires an admin and a reason. It blocks future publication/approval and creates verification history plus an admin action audit. It does not alter approved events, tickets, orders, refunds, or payouts. The Event Approvals screen flags already-approved events from a revoked creator for separate manual review.

Government ID images, dates of birth, and document numbers must never be entered into notes, history, support records, logs, S3, or application storage.
