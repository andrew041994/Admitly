# Production release checklist

Release owner records evidence and signs each item. Automated CI is necessary but does not replace these checks.

- [ ] Production config validation passes with Redis, a non-default JWT secret, `ENABLE_DEV_TEST_CHECKOUT=false`, and no client test-checkout UI.
- [ ] Backend tests, mobile typecheck/tests, admin build, migration-head validation, migrations on a production-like database, and `git diff --check` pass.
- [ ] Sentry DSNs and release/environment tags are configured for backend, Android, iOS, and admin; a controlled test event appears with its request/release ID.
- [ ] Physical Android and iOS devices pass signup, verification, login, reset, organizer, buyer, and staff journeys on signed native builds.
- [ ] Real push delivery passes foreground, background, and terminated states on both platforms, including token rotation/logout behavior.
- [ ] A low-value real MMG checkout passes initiation, verified callback, idempotent callback replay, ticket issuance, reconciliation, and approved refund.
- [ ] Full checkout → ticket → transfer → recipient acceptance → scan runs end to end, including rejected duplicate/old ticket scans.
- [ ] Full organizer workflow passes event creation, approval, publication, tier inventory, staff assignment, check-in, reporting, cancellation, and refund batch behavior.
- [ ] Event approval rejects unverified creators; the admin records only verification metadata after confirming the creator is 18+, the emailed government-ID image is deleted, no ID image/number appears in application storage or logs, and the event becomes publishable/discoverable only after verification and approval.
- [ ] Final security/regression pass covers authorization boundaries, rate limits across multiple API instances, Redis outage behavior, callback forgery/replay, secrets, CORS, S3 access, logs/PII, dependency findings, and admin audit records.
- [ ] Neon restore drill, Render rollback drill, incident contacts, support coverage, payment reconciliation ownership, and legal page review are current.
