# Render rollback runbook

Owner: on-call engineer. Use for a bad API or worker deployment; database rollback is a separate decision.

1. Open an incident record and capture the failing deploy ID, commit SHA, start time, symptoms, and current migration revision.
2. Stop automated deploys if they would overwrite the rollback. If writes risk corruption, disable the affected feature or service first.
3. Identify the last healthy deploy and confirm its expected Alembic revision. A code rollback is safe only when all migrations since that release are backward compatible.
4. Use Render’s rollback/redeploy control for the exact healthy deploy. Roll back the API and notification worker together when they share code or schema assumptions.
5. Do not run Alembic `downgrade` during routine rollback. If schema reversal is essential, treat it as a database incident with a tested migration and backup.
6. Verify `/health`, authentication, a read-only event request, worker startup, and logs. Then run one low-risk authenticated smoke test without initiating a real charge.
7. Watch Sentry, structured logs, request IDs, latency, callbacks, and worker backlog for at least 30 minutes. Re-enable auto-deploy only after stability is confirmed.

Record who rolled back, the selected deploy, verification evidence, customer impact, and follow-up owner.
