# Refresh-session rollout and operations

## Deployment transition

Migration `20260812_0043` adds `auth_sessions`; it does not modify or backfill users. Deploy the migration before backend code that issues session-bound refresh tokens. Refresh JWTs issued by older backend releases have no `sid` claim and are intentionally rejected by the hardened refresh endpoint. Existing access JWTs continue working until their normal 15-minute expiry, after which affected users must sign in once to create a durable session.

Do not attempt to import, decode, or backfill legacy refresh tokens. They were never stored server-side.

## Session behavior

- Each login or signup creates one session family with an absolute 30-day expiry.
- PostgreSQL stores only the SHA-256 hash of the currently valid refresh JWT.
- Every refresh rotates the token under a row lock. A mismatched token for a valid session ID is treated as reuse and revokes that session family.
- Current-session logout revokes the supplied refresh family and is idempotent.
- Log out all devices, password reset, and password change revoke every active family for the user.
- Access JWTs are not denylisted and expire after 15 minutes. Current account and admin authorization is still loaded from PostgreSQL on every protected request.

## Cleanup and retention

Login, signup, and refresh perform bounded cleanup only. Each call deletes at most `AUTH_SESSION_CLEANUP_BATCH_SIZE` rows whose expiry or revocation is older than `AUTH_SESSION_RETENTION_DAYS`. Defaults are 100 rows and 90 days. This retains security investigation metadata without an unbounded request-time scan. Review table growth after launch; a scheduled maintenance command can be added later if bounded opportunistic cleanup does not keep pace.

## Operator verification

After a non-production migration and backend deployment:

1. Sign in on two test clients and confirm two active rows with different IDs and hashes.
2. Confirm no stored hash equals either plaintext refresh JWT.
3. Refresh one client and confirm its hash and `last_refreshed_at` change.
4. Confirm its previous refresh JWT returns `401` and the family becomes revoked for reuse.
5. Sign in again, log out normally, and confirm that family is revoked with reason `logout`.
6. Sign in on two clients, use log out all, and confirm both families are revoked.
7. Reset and change the test password separately, confirming all earlier refresh JWTs return `401`.
8. Confirm structured logs contain session/user IDs but no JWTs, passwords, or reset tokens.

Never copy real tokens into tickets, chat, logs, or drill evidence.
