# Production rollout: schema 0044, hardened auth, and authenticated web

This is an operator procedure, not authorization to deploy. Execute it only through approved production access. Never put credentials, tokens, user IDs, personal data, or ID-document data in evidence.

## Release identity and required starting evidence

The reviewed release is commit `b0cb8dd` (record its full SHA), with one Alembic head: `20260812_0044`. Commit `da519ee` introduced session-bound refresh and requires schema `0043` or later. Commit `b0cb8dd` adds account-level creator verification and requires schema `0044`.

Do not infer production state from the repository. Before any change, obtain read-only and record:

- the sole `alembic_version.version_num` row;
- Render API Live deploy ID and full commit SHA (and worker identity separately, if applicable);
- Vercel production deployment ID, full source commit SHA, production aliases, and Ready state;
- `GET https://admitly.onrender.com/health` status/body and `X-Request-ID` response header;
- that Render environment mode is production, without copying environment values;
- Render Key Value/Redis availability and absence of repeating limiter connection errors, without copying its URL;
- current auth/verification behavior inferred from the proven deployed SHA, not customer-token probing.

Abort before migration if any identity is unavailable or inconsistent, or the database has multiple Alembic rows/heads. `/health` proves process availability only, not PostgreSQL or Redis health.

## Migration facts

### 0043 auth sessions

`20260812_0043` creates `auth_sessions`: 64-character primary-key session ID; non-null user FK with cascade delete; unique, non-null 64-character refresh-token hash; absolute expiry; nullable refresh/revocation timestamps and reason; timestamps; and expiry/user/active-family indexes. It changes no users and requires no backfill. Legacy refresh JWTs were never stored and lack `sid`; the hardened backend intentionally returns `401` for them. Access JWTs are not denylisted and can survive only their configured remainder, expected at no more than 15 minutes.

### 0044 account creator verification

`20260812_0044` adds user status (`pending`, `verified`, `revoked`), verification/revocation actor/timestamp/note fields and FKs, immutable `creator_age_identity_verification_history`, and an event approval-snapshot timestamp. It does not delete or rewrite event-level evidence.

The backfill verifies an account only when it has a legacy verified event and every verified event for that creator has a subject matching the organizer's user plus a non-null verifier and timestamp. It deterministically chooses the earliest timestamp, breaking ties by event ID, copies that verifier/note, and creates one history row. Any incomplete or mismatched verified record leaves that creator pending for manual review; no verified evidence leaves the creator pending. Existing approved events and their evidence stay unchanged. Future approvals copy current account evidence into the event snapshot.

## Exact compatibility matrix

Here, **old backend** means schema-0042 code at `2ceb9b6` (or equivalent pre-`da519ee`) and **new backend** means `b0cb8dd`.

| Backend | Schema | Classification | Behavior |
| --- | --- | --- | --- |
| Old | 0042 | Safe baseline | Stateless refresh and event-scoped verification; neither hardening exists. |
| Old | 0043 | Safe temporarily; security-degraded | Additive table is ignored. Auth remains stateless and sessions are not recorded. |
| Old | 0044 | Safe only under event hold; policy-degraded | Schema is readable, but old code can mutate event verification without account/history authority. Prohibit creator verification, event approval, and publication. |
| New | 0042 | Prohibited | Session table, account fields/history, and snapshot are absent; login and user/event ORM paths fail. |
| New | 0043 | Prohibited | Auth schema exists, but account fields/history and snapshot are absent; user/event paths fail. |
| New | 0044 | Required target | Hardened sessions and account-level verification are compatible. |

`da519ee` is a useful emergency intermediate on schema `0044`: it retains hardened sessions but has obsolete event-scoped verification, so event operations must remain held.

Both migrations are additive and may safely run in one `alembic upgrade 20260812_0044` command before backend deployment. Alembic applies `0042 -> 0043 -> 0044` in order. Keep the gap short and never deploy `b0cb8dd` unless the DB reports exactly `0044`.

## Operational holds

Start immediately before migration; end only after backend and admin verification passes.

| Function | Hold? | Reason |
| --- | --- | --- |
| Creator verify/revoke | Yes | Old code does not maintain new account/history authority. |
| Event approval/re-approval | Yes | Must not rely on mixed verification authority. |
| Event publication/unpublication | Yes | Publication/discovery is coupled to verified approval evidence. |
| Login, signup, refresh, logout | No hard hold | Old auth works; tokens it issues require one re-login after cutover. Keep the gap short. |
| Password change/reset submission | No | Valid on old code. Do not send reset email as a smoke test. Pre-cutover refresh tokens fail at cutover regardless. |
| Ticketing for already approved/discoverable events | No | Migrations do not alter orders, inventory, tickets, payments, refunds, or payouts. Do not test with a transaction. |
| Public browsing/legal pages | No | Read-only public behavior is unaffected. |

Abort if the three event holds cannot be enforced procedurally; there is no repository-defined feature kill switch, and this rollout does not authorize an environment change.

## Exact rollout order

First reconcile reality with the intended sequence. If production already serves the new API/web release, do not blindly replay deployment steps. If the DB is already `0044`, treat migration as complete, do not rerun/stamp it, verify the existing backend, and deploy only an artifact whose recorded SHA differs from the target. If the new backend is Live while the DB is below `0044`, declare an incompatible partial-rollout incident, extend the hold to login/signup/refresh and authenticated account/event routes, and choose through incident control either (a) complete the already-approved additive migration immediately, then verify/redeploy the same frozen backend artifact, or (b) roll back to a proven schema-compatible backend before resuming the normal sequence. Do not let Codex choose or execute that production mutation.

1. Open the evidence record. Record UTC start, operator, reviewed full release SHA, expected head, designated testers, current recovery point, and restore readiness (do not restore).
2. Freeze creator verification/revocation, event approval, and event publication/unpublication. Leave public browsing and ordinary ticketing available.
3. With Neon/read-only PostgreSQL access, record the exact revision and run `psql "$READ_ONLY_DATABASE_URL" -X -f scripts/production_rollout_0044_preflight.sql`. Retain only aggregate/schema results. Require read-only on, one revision row, required bases, a revision on the expected chain at or before `0044`, and zero invalid/orphan structural counts. Record all three prospective backfill counts.
4. Record current Render/Vercel deployment IDs/full SHAs/status. Confirm production mode and shared Redis without exposing values. Run repository safety validation against a secure env export if policy permits; it never prints values.
5. If preflight passes, an authorized operator applies `alembic upgrade 20260812_0044` through the approved migration job. If already `0043`, only `0044` runs; if already `0044`, do not rerun or stamp. Codex must not execute this step.
6. In a fresh read-only transaction, require one revision row exactly `20260812_0044`; rerun the SQL and compare actual account/history counts with predictions. Require zero incomplete verified users, missing verified histories, invalid FKs, or invalid states. Do not repair during rollout.
7. Deploy frozen `b0cb8dd` backend through Render. Confirm Live deploy ID/full SHA, startup guards, schema compatibility, and no repeating PostgreSQL/Redis/Sentry errors. Do not restart unrelated services or trigger worker delivery.
8. Run backend smoke checks below.
9. Deploy matching `b0cb8dd` authenticated web/admin through Vercel. Confirm deployment ID/full SHA, Ready state, and intended aliases.
10. Run public, normal-user, admin, authorization, and CTA web checks below.
11. Run one controlled tester account/two-event flow. Never upload a real ID or write ID data in notes.
12. Review Sentry and Render logs by request ID for schema/Redis errors, secret/token logging, unexplained 5xx, and release regressions.
13. End the event hold, record UTC end/disposition, and observe the legacy-session transition through at least the 15-minute access-token window.

### Abort criteria

Abort before application deployment if the DB target is uncertain; revision is off-chain or not singular; read-only is not enforced; required base/0040 structures are absent; an orphan/invalid FK or invalid status exists; partial 0043/0044 objects are unexpected; actual backfill differs from prediction; schema is not exactly `0044`; release SHAs cannot be proven; or recovery readiness is unconfirmed.

Abort/rollback application rollout if startup guards, health/request IDs, DB/Redis, session rotation/reuse/logout, authorization, creator verification/approval/revocation, public/ticketing error rates, or Sentry/log privacy checks fail.

## Backend smoke checklist

Use designated non-customer testers. Store tokens ephemerally with restrictive permissions; print only status, boolean assertions, and request IDs. Never put tokens in shell history, tickets, chat, logs, or evidence.

### Health and dependencies

- `GET /health` returns `200` and `{"status":"ok"}`.
- A unique safe `X-Request-ID` is echoed in the response header.
- Exact Live deploy/SHA, production startup, Redis/limiter health, DB revision `0044`, and clean startup/Sentry logs are confirmed.

### Login/session

- Login normal tester: `200`, access lifetime no more than 15 minutes, refresh lifetime present, one session family created.
- Refresh once: `200`, refresh token changes, same family hash/refresh time changes. Never compare/display plaintext to stored hash.
- Replay previous refresh: `401` and family revoked for reuse. Then use a fresh login.
- Fresh login; logout; subsequent refresh: `401`.
- Two isolated tester logins; authenticated `/auth/logout-all`; both refresh tokens then return `401` (access tokens may survive to expiry).
- Login again for later checks.

### Password/admin

- Do not call `/auth/forgot-password` without email authorization. If an already-issued, unexpired tester reset token is safely available, reset and prove prior refresh sessions fail, old password fails, new password succeeds. Otherwise mark reset delivery/submission deferred-manual.
- Change password through `/account/change-password`; require reauthentication, all sessions revoked, old password failure, and new password success. Never record passwords.
- Admin tester: `/auth/me` shows current DB-backed admin true and `GET /events/admin/pending-approval` succeeds.
- Normal tester: `/auth/me` shows admin false and that admin API returns `403`. JWT/client claims are not authority; protected requests reload the user/admin state from PostgreSQL.

### Creator verification

- Pending/unverified tester creates a draft.
- Approval attempt returns `409` before verification.
- Admin verifies the tester ACCOUNT once with a bland non-ID note; account status/history/audit succeeds.
- Approve event one; approval and complete immutable snapshot succeed.
- Create event two for the same account: no second ID action/history; normal approval is still required and succeeds.
- Revoke account with a non-sensitive reason. Future/pending approval is blocked; prior approved event remains approved with its snapshot.
- Never use real ID, customer data, payment, ticket purchase, notification, callback, or external delivery as smoke data.

## Web/admin smoke checklist

- Public: `/`, `/events`, one event detail, `/privacy`, `/refund-policy`, `/terms`, `/organizer-terms`, `/buyer-terms` render.
- Auth: `/login`, `/signup`, `/forgot-password`; `/reset-password` without token shows safe missing-token UI; `/verify-email` without token shows safe invalid-token UI. Do not submit flows that send email.
- Normal tester: `/tickets`, `/notifications`, `/account`, `/my-events`, `/create-event` render under shared auth.
- Admin tester: `/admin` redirects to `/admin/support`; `/admin/support`, `/admin/finance`, `/admin/event-approvals` render.
- Normal user cannot enter admin shell and gets `403` from admin API; admin can enter admin shell and still use normal pages.
- Landing Log In/Sign Up/Create Event/account CTAs use `/login`, `/signup`, `/create-event`, not forced `admitly://` links. Reset/verification pages may retain an optional app link alongside working web flows.
- Require no new browser console or Sentry errors; do not capture token-bearing URLs or credentials.

## Legacy-session transition and communication

All pre-rollout refresh tokens lack `sid` and return `401` after `b0cb8dd` is Live. Existing access tokens may continue only their remaining configured lifetime, expected at no more than 15 minutes. One new login creates `auth_sessions` authority and normal rotation begins. This is intentional.

- Test-only/internal population: no broad communication; note it for testers/operators.
- Real active users: separately authorize a brief banner/release note: “You may be asked to sign in again as we improve account security.” Do not suggest compromise.
- This runbook does not authorize sending communication.

## Creator backfill evidence

Use the preflight's mutually exclusive aggregate counts: accounts `0044` will verify; accounts pending with no prior verified evidence; accounts pending for manual review due to incomplete/mismatched evidence. After migration, match status/history totals to predictions. Never list names/emails. Confirm event verification rows were unchanged, approved events retained their snapshot evidence, and a future approval uses current account verification.

## Rollback

Routine rollback is application-only; leave additive schema `0044`. Never automatically downgrade or stamp. Downgrade deletes session authority, account history, and snapshot metadata and requires separate incident/data-preservation approval.

The rollback target is the latest prior Render deploy proven healthy by full SHA, smoke evidence, and Sentry baseline. Repository candidate `da519ee` runs on schema `0044` and preserves hardened sessions, but uses event-scoped verification: keep creator verify/approval/publication held throughout. Do not call it known-good until Render evidence proves it. Candidate `2ceb9b6` is DB-compatible because migrations are additive, but re-enables stateless refresh and obsolete verification; use only with explicit security incident approval and the event hold.

Roll back Vercel independently to its recorded prior Ready deployment if only web fails. Prove API compatibility and do not change environment values.

Abort rollback if candidate identity/schema/security cannot be proven; startup/health/DB/Redis fails; revoked/replayed tokens might be accepted; event hold is absent for policy-incompatible code; symptoms worsen; or financial/ticket integrity becomes ambiguous. Keep the hold until compliant backend/admin is restored and reverified.

## Evidence template

```text
Release / full reviewed SHA:
UTC start / end:
Operator:
Final disposition: GO / ABORTED / ROLLED BACK / HELD

DB revision before (row count + revision):
DB revision after (row count + revision):
Read-only role/transaction confirmed (no value):
Recovery readiness reference:
Backend deploy ID/full SHA before:
Backend deploy ID/full SHA after:
Web/admin deployment ID/full SHA before:
Web/admin deployment ID/full SHA after:
Redis check (no URL): PASS / FAIL
Production-mode check (no value): PASS / FAIL

Health/request ID:
Auth rotation/reuse/logout/logout-all:
Password change:
Password reset: PASS / FAIL / DEFERRED
Admin authorization/server authority:
Creator verify/reuse/revoke/snapshot:
Public/legal routes:
Normal-user routes:
Admin routes:
Landing CTA web-auth behavior:
Sentry/Render logs (sanitized reference):
Legacy-session transition observed: YES / NO / NOT YET

Users / events / approved events / legacy verified events:
0044 predicted verified accounts:
0044 predicted pending/no-evidence accounts:
0044 predicted manual-review accounts:
0044 actual verified / pending / manual-review counts:
Operational hold start/end UTC:
Abort/rollback decision and reason:
Open manual steps:
No-side-effect attestation:
```

## Repository validation

```bash
backend/.venv/bin/python scripts/verify_production_safety.py
cd backend && .venv/bin/alembic history
cd backend && .venv/bin/alembic heads
git diff --check
```

The safety preflight checks migration chain/head and static production guards, and warns when no production env file is supplied. `alembic heads` must print exactly `20260812_0044 (head)`. Run DB preflight separately with a read-only production role; never give Codex a writable production connection.
