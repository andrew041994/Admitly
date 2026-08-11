# Incident-response procedure

Severity: SEV-1 for active safety, broad security/payment compromise, destructive data loss, or platform-wide outage; SEV-2 for major degraded workflows; SEV-3 for limited impact with a workaround.

1. Declare the incident, assign an incident commander, operations lead, communications lead, and scribe. Use UTC timestamps.
2. Record detection source, scope, affected users/events/payments, latest healthy time, deploy and migration IDs, and representative request IDs. Do not place secrets or unnecessary personal data in the incident log.
3. Contain first: disable the affected feature, revoke exposed credentials, pause payouts/callback processing, stop a worker, or roll back when appropriate. Preserve logs and database branches before changing evidence.
4. Communicate on a fixed cadence: 15 minutes for SEV-1, 30 minutes for SEV-2. State confirmed facts, impact, mitigation, and next update time.
5. Recover using the relevant rollback, restore, payment, or storage runbook. Require explicit verification of authentication, checkout, tickets, transfers, scan, notifications, and financial integrity as applicable.
6. Monitor after recovery and declare resolution only when metrics and user journeys remain healthy through the agreed observation window.
7. Within five business days, publish an internal review covering timeline, root cause, contributing controls, customer/data/payment impact, detection gaps, and owned corrective actions.

Security or privacy incidents also require a documented legal assessment of notification obligations and evidence retention.
