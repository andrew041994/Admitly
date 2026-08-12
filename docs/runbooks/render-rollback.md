# Render rollback runbook

Owner: on-call engineer. Use for a bad API or worker deployment; database rollback is a separate decision.

Official controls: [Render rollbacks](https://render.com/docs/rollbacks) and [Render deploys](https://render.com/docs/deploys).

## Admitly deployment topology

- The API is a Render Web Service rooted at `backend`, serving `app.main:app`, with public health endpoint `/health`.
- The repository has no Render Blueprint. Render service IDs, linked branch, commands, environment groups, health-check setting, auto-deploy mode, and deploy history exist only in the Render dashboard.
- The notification processor, if deployed, is a separate Render Background Worker from the same repository and backend root. Its start command is `python scripts/run_notification_worker.py`; it shares the database and notification schema but has an independent deploy history and auto-deploy setting.
- No Render cron job or other scheduled service is declared in this repository. Inventory the dashboard before every drill because manually created services cannot be inferred from source.
- The Vercel admin is independently deployed. Do not roll it back merely because the API rolls back, but restrict admin financial/support operations if its expected API contract is unavailable after rollback.

## Required incident evidence

Use [render-rollback-evidence.md](render-rollback-evidence.md). Record sanitized IDs and SHAs, not secrets, environment values, request bodies, access tokens, or customer data.

## Identify current and rollback releases

1. Open the Render workspace and the Admitly API service. On **Deploys**, identify the entry marked **Live**. Record its deploy ID, full commit SHA, commit message, deploy start/live times, runtime release (`admitly-backend@<sha>` in Sentry), and whether it is the suspected failing release.
2. Open the immediately earlier successful deploy, but do not assume it is healthy. Confirm its full commit SHA, prior smoke evidence, incident history, Sentry error baseline, schema expectations, security status, and whether its build artifact still exposes a **Rollback** action.
3. Select the most recent deployment with positive known-good evidence. Record both its API deploy ID and commit SHA.
4. If a notification worker exists, repeat the inventory on its independent **Deploys** page. Select the worker deploy built from the same known-good SHA, or document why its code was unaffected and can remain running.
5. On the API and worker **Settings** pages, record Auto-Deploy mode, linked branch, root directory, current build/start commands, attached environment groups, and health-check path. Do not copy environment values into the incident record.

Repository target audit for this release line:

- `b6c3894` is an acceptable backend rollback candidate if its Render deploy is verified successful: its `backend` tree is identical to current repository commit `c2b242b`.
- Do **not** select `c278ac4` or an earlier backend merely because it ran before migration 0039. That code defaults `ENABLE_DEV_TEST_CHECKOUT` to true, hard-codes localhost in production CORS, uses process-local rate limiting, lacks the current startup/observability guards, and can treat an unauthenticated MMG callback payload as payment proof. It is schema-compatible but not production-security-compatible.
- A dashboard deploy must still be matched to its full SHA. Do not infer the target from list order or commit message alone.

## Choose the Render mechanism

Render Dashboard rollback automatically disables Auto-Deploy for that service and reuses the selected deploy's build artifact, start command, health-check path, instance count, and service-local environment-variable snapshot. Environment-group values are not reverted; their current values remain. Current service configuration remains saved and is used again by a later standard deploy.

Before native rollback, compare the target deploy metadata with the current requirements. Confirm, without recording values, that the rollback process will receive a valid production database connection, shared Redis, strong JWT secret, production CORS origins, disabled development checkout, disabled MMG, and any intended Sentry/email/push configuration. This matters when production variables were added after the target deploy.

Choose one:

- **Native Rollback — preferred when the target artifact and configuration snapshot are safe.** Use the target deploy's **Rollback** action. This is fastest because it skips rebuilding.
- **Deploy a specific commit — preferred when target service-local environment metadata is stale or the build artifact is unavailable.** Use **Manual Deploy → Deploy a specific commit**, paste/select the recorded full known-good SHA, and click **Deploy Commit**. This rebuilds that code using current service configuration. Dashboard-specific-commit deploys also disable Auto-Deploy. Account for slower recovery and dependency/build reproducibility.

Do not use Restart Service: it redeploys the currently running commit and does not revert code. Do not use Deploy Latest Commit: it can redeploy the failing release.

## Exact dashboard rollback procedure

1. Declare the incident, assign the incident commander and rollback operator, start UTC timing, and preserve representative request IDs/Sentry links/log queries.
2. Check for in-progress or queued deploys on every affected Render service. Cancel only an explicitly identified superseded deploy under incident-commander approval. A queued deploy can otherwise replace the rollback.
3. Set Auto-Deploy to **Off** on the API and any coordinated worker before acting. Dashboard Rollback/specific-commit deploy also disables it, but explicitly verify **Off** because each service is independent.
4. Verify production Alembic revision with the approved SELECT-only Neon procedure. For this release line, expect `20260811_0039`; do not run a downgrade.
5. Apply the mechanism decision above. For native rollback: **API → Deploys → known-good successful deploy → Rollback → Rollback to this deploy**. For rebuild: **API → Deploys → Manual Deploy → Deploy a specific commit → known-good SHA → Deploy Commit**.
6. Watch build/start/live logs. Stop and apply the abort criteria below if startup guards fail, the health check never passes, required configuration is missing, or the candidate produces worse symptoms. Render normally leaves the prior live instance serving if a new web-service deploy cannot become healthy.
7. After the API becomes Live, run the post-rollback checklist below before declaring recovery.
8. If a notification worker is deployed and requires coordination, roll it to its recorded deploy for the same SHA using its own Deploys page. The worker has no HTTP health endpoint; require `notification_worker_starting`, `notification_worker_startup_validated`, and `notification_worker_polling_started` without repeated fatal/database errors. Do not send a test notification.
9. Inventory any manually configured cron/background service sharing the repository. Roll it back only if it runs the affected commit or shares changed schema/message contracts; otherwise document why it stayed unchanged.
10. Keep Auto-Deploy **Off** through the observation period. Re-enable the approved prior mode only after the root cause is fixed, the intended head commit is reviewed, and the incident commander approves. Re-enabling against a branch whose head is still bad can immediately redeploy the defect.

No environment-variable value change is part of a normal rollback. If the candidate requires a value change, stop and treat it as a separately reviewed configuration incident; do not improvise during rollback.

Although notification delivery code does not consume Redis or JWT directly, the worker imports the shared `Settings` object. With `ENV=production`, current startup validation therefore still requires a valid shared `REDIS_URL` and strong `JWT_SECRET`. Confirm the worker's environment group supplies them before selecting a hardened worker deploy; do not add values during the rollback drill.

## Schema compatibility at 20260811_0039

The specifically recorded prior backend is compatible with schema `20260811_0039`. Migration 0039 is additive, retained server defaults support old inserts into `payment_attempts` and `refunds`, and uniqueness constraints safely reject duplicate provider references. Keep the database at 0039; routine application rollback does not require or authorize Alembic downgrade.

After the event-creator verification release migrates production to `20260811_0040`, old hardened backends remain database-compatible because 0040 is additive and retains a `pending` server default. They are not business-policy-compatible: they do not require age/identity verification for publication or discovery. A rollback at schema 0040 therefore requires an operational hold on event approval/publication and prompt restoration of a compliant backend. Keep schema 0040; do not downgrade merely to roll back application code, because downgrade removes verification metadata from events.

For the current history, `b6c3894` plus schema 0039 is both schema-compatible and retains the hardened backend. `c278ac4` plus schema 0039 is schema-compatible at the ORM/database level but fails production security requirements and is therefore an abort target. Compatibility statements must always identify an exact SHA.

Rollback is unsafe without further review if the target:

- predates another non-backward-compatible migration or queries columns/tables no longer present;
- depends on removed enum values, constraints, environment variables, secrets, or external services;
- writes data in a form the current schema rejects without safe error handling;
- can trust unauthenticated payment callbacks, enable mock/test checkout, duplicate fulfillment/refunds, or otherwise weaken financial integrity in the current configuration;
- contains a known exploitable security/privacy defect;
- expects a different JWT secret, which would invalidate active sessions, or cannot use current Redis/CORS/database settings;
- requires downgrading 0039 or deleting/backfilling production data.

The new admin expects the hardened payment/authenticity API. After API rollback, keep the admin deployed only if its read-only/support paths remain compatible; otherwise restrict affected admin operations and make a separate Vercel rollback decision.

## Tabletop: checkout 500s immediately after deployment

1. **Detect:** Alert on checkout 5xx rate in Sentry/Render, support reports, or API metrics. Record the first/last known healthy UTC times, failing release, representative request IDs, affected endpoints, and whether any orders/payments reached ambiguous states.
2. **Classify:** Start at SEV2 for a substantial checkout failure. Escalate to SEV1 for broad platform outage, duplicate fulfillment, accepted payment without ticketing, refund/payout risk, data corruption, or a security incident.
3. **Own:** On-call engineer becomes incident commander until explicitly transferred. Assign separate rollback operator and scribe; add finance/payment owner if any payment state may be ambiguous.
4. **Preserve evidence:** Save deploy IDs/SHAs, Sentry release/issues, Render log query links, request IDs, error counts, current schema revision, Redis status, and sanitized affected internal order IDs. Do not copy secrets or provider payloads.
5. **Correlate:** Search structured Render logs by request ID and endpoint; open the matching Sentry issue and confirm environment/release; compare error onset with Render's Live timestamp. Determine whether failures originate in validation, Redis, database/schema, provider-disabled paths, or application exceptions.
6. **Check dependencies:** `/health` can pass while database/Redis checkout dependencies fail. Run `/health`, public event discovery, one invalid login, read-only Alembic query, Redis-backed limiter check, startup logs, and database/Redis metrics.
7. **Decide:** If the onset aligns with the new deploy, the prior recorded release is compatible/safe, and impact is material, prefer rollback within the incident's decision window. Do not wait for a speculative fix while checkout remains broadly unavailable.
8. **Roll back:** Freeze Auto-Deploy, select native artifact rollback only if its configuration snapshot is safe; otherwise deploy the known-good SHA with current configuration. Coordinate the notification worker as above. Keep schema 0039.
9. **Verify:** Complete every post-rollback check. Do not perform a real checkout, callback, refund, payout, email, or push test during this smoke phase.
10. **Observe:** Monitor for at least 30 continuous minutes and through a representative traffic interval. Track checkout 5xx, general 5xx, latency, Redis failures, database errors, Sentry release/error rate, ambiguous orders, notification-worker failures/backlog, and financial reconciliation exceptions.
11. **Resolve:** Declare recovery only when the incident commander and finance owner (when applicable) confirm stable metrics, no growing ambiguous financial state, verification evidence is complete, and follow-up ownership exists. Leave Auto-Deploy off until the bad head commit cannot automatically return.

**Tabletop result:** Procedure is executable, schema rollback is unnecessary, and `b6c3894` is the repository-verified candidate while `c278ac4` is explicitly disallowed. The safest Render mechanism still depends on the target deploy's environment snapshot. A live dashboard drill is required to record actual service IDs, deploy IDs, worker existence, Auto-Deploy settings, and artifact retention.

## Post-rollback verification checklist

Use `https://admitly.onrender.com`. Record statuses and headers without storing tokens or response bodies containing customer data.

- [ ] **Health:** `GET /health` returns `200` with `{"status":"ok"}`.
- [ ] **Request ID:** Send a safe `X-Request-ID: rollback-<incident>-health`; response echoes the same valid ID in `X-Request-ID`.
- [ ] **Allowed CORS:** Preflight `/health` with origins `https://www.admitlyevents.com` and `https://admitlyevents.com`; each returns the exact corresponding `Access-Control-Allow-Origin` and no wildcard.
- [ ] **Denied CORS:** Preflight with `http://localhost:5173` and an unrelated HTTPS origin; neither response contains `Access-Control-Allow-Origin`.
- [ ] **Non-browser request:** `GET /health` without `Origin` still returns `200`.
- [ ] **Read-only API/database path:** `GET /events/discover?q=rollback-smoke-<incident-id>-no-match` returns `200` and valid JSON without modifying data or exposing customer records in the evidence.
- [ ] **Invalid login and Redis:** Send one login request using a unique reserved-domain address and invalid password. Expect the normal authentication failure (`401`), not `500` or rate-limiter-unavailable `503`; capture `X-Request-ID`. This exercises database lookup and Redis-backed rate limiting without touching a real account or sending email.
- [ ] **Limiter threshold, only if approved:** Reuse only that synthetic identity up to the documented limit and confirm `429` plus `Retry-After`. Skip if incident traffic or operator-IP rate limiting makes this unsafe.
- [ ] **Alembic:** Through the SELECT-only Neon procedure, `SELECT version_num FROM alembic_version;` returns exactly `20260811_0039`.
- [ ] **Schema/runtime:** Render logs contain no undefined-column/table, enum, constraint, migration-head, connection-pool, or unhandled database errors.
- [ ] **Redis:** No shared-limiter connection failures/fallback warnings; invalid login did not return `503`. Confirm the rollback candidate cannot silently use process-local limiting in production.
- [ ] **Structured logs:** Each smoke request produces valid JSON with timestamp, level, logger, message, method, path, status, duration, and request ID. No secrets/tokens are visible.
- [ ] **Sentry:** Backend project shows environment `production` and rollback release SHA; no initialization errors. Error rate returns to baseline. Do not emit an artificial exception unless an existing approved operator mechanism exists.
- [ ] **Production guards:** Startup succeeds with shared Redis, strong JWT secret, production CORS, `ENABLE_DEV_TEST_CHECKOUT=false`, and `MMG_ENABLED=false`. Mock MMG/test checkout cannot execute.
- [ ] **Worker, if deployed:** Correct commit/deploy is Live and startup/polling logs are healthy; no test notification is sent.
- [ ] **Admin compatibility:** Public/legal/admin pages render, and unsupported financial support actions are restricted if the prior API lacks required fields.
- [ ] **Observation:** At least 30 continuous minutes of stable 5xx, latency, Redis/database, Sentry, checkout, worker, and reconciliation signals are recorded.

## Rollback versus forward fix

Choose **rollback** when impact is broad/material, onset clearly follows the deploy, the known-good release and configuration are verified safe against schema 0039, the rollback artifact is available (or the SHA can be rebuilt), and rollback is faster/lower risk than diagnosing under outage.

Choose a **forward fix** when the defect is isolated and containable, the reviewed fix is small and already validated, rollback would reintroduce a security/financial defect or break current schema/contracts, the known-good artifact/configuration cannot be reproduced safely, or the failure is external/configuration/data-related and old code would fail identically.

## Rollback abort criteria

Abort or stop the candidate rollout if:

- the selected deploy/SHA cannot be independently matched to the approved known-good release;
- its artifact is unavailable and the specific-commit rebuild is not reproducible;
- target environment/configuration metadata is missing, stale, or incompatible;
- it is not compatible with schema 0039 or requires database downgrade/data mutation;
- startup guards fail, health never becomes ready, or logs show schema/Redis/JWT/configuration failures;
- it enables development checkout, mock/live MMG unexpectedly, unauthenticated callbacks, duplicate fulfillment/refund risk, or a known security defect;
- it would invalidate active JWT sessions due to a different secret;
- it worsens 5xx, data integrity, financial ambiguity, or notification duplication;
- another queued/automatic deploy will immediately replace it;
- a reviewed forward fix or dependency recovery is demonstrably safer and faster.

If aborted, keep the last safe live instance where Render permits, preserve evidence, and return to incident-command decision making. Do not improvise schema or secret changes.
