# Render rollback drill evidence template

Store completed evidence in the private operations repository. Do not record secrets, environment values, connection strings, tokens, customer PII, or provider payloads.

## Incident and ownership

- Incident ID:
- UTC start time:
- Detection source:
- Severity and reason:
- Operator/rollback executor:
- Incident commander:
- Scribe:
- Finance/payment owner, if applicable:

## Current production state

- API service name/ID:
- Current API deploy ID:
- Current full commit SHA:
- Current Sentry release:
- Current deploy Live time:
- Notification worker exists: yes / no / not verified
- Worker service name/ID:
- Current worker deploy ID and SHA:
- Other repository-linked background/cron services:
- Current Alembic revision:
- API Auto-Deploy mode before incident:
- Worker Auto-Deploy mode before incident:

## Selected known-good release

- Previous known-good API deploy ID:
- Previous full commit SHA:
- Repository target classification: allowed (`b6c3894` or later verified hardened SHA) / prohibited / needs review
- Evidence that it was healthy:
- Rollback artifact available: yes / no
- Target environment metadata reviewed without recording values: yes / no
- Schema `20260811_0039` compatibility confirmed: yes / no
- Security/payment safety confirmed: yes / no
- Known-good worker deploy ID/SHA, if applicable:

## Decision and execution

- Rollback decision reason:
- Rollback versus forward-fix assessment:
- Chosen mechanism: native rollback / deploy specific commit / abort
- Auto-Deploy confirmed Off for coordinated services:
- Rollback start time (UTC):
- API Live/rollback end time (UTC):
- Worker rollback start/end time, if applicable:
- Rollback duration:
- Abort criteria checked/result:

## Verification

- `GET /health` result:
- Request-ID result:
- Allowed production CORS result:
- Denied localhost/unrelated CORS result:
- No-Origin result:
- Invalid-login/auth result:
- Read-only event endpoint result:
- Redis/rate-limiter result:
- Alembic revision result:
- Structured-log result:
- Sentry environment/release/error result:
- Schema/runtime error review:
- Development checkout disabled:
- MMG disabled/no mock behavior:
- Notification-worker result, if applicable:
- Admin compatibility result:

## Observation and disposition

- Observation start/end time:
- Observation period duration:
- Checkout/general 5xx result:
- Database/Redis result:
- Sentry/log result:
- Ambiguous order/payment review result:
- Worker/backlog result:
- Final disposition: recovered / forward fix required / rollback aborted / unresolved
- Incident resolution time (UTC):
- Auto-Deploy final state and approver:
- Follow-up owner and due date:
- Evidence location:
