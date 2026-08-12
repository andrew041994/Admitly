# Neon recovery drill evidence template

Store the completed record in the private operations evidence repository. Do not commit production connection strings, role passwords, customer data, payment references, request/response payloads, or screenshots containing credentials.

## Authorization and source

- Operator:
- Approver, if applicable:
- Drill/incident ticket:
- Neon project identifier:
- Region:
- Production branch name and identifier:
- Production branch protected: yes / no / not verifiable
- Configured instant-restore window:
- Snapshot schedule and retention, if configured:
- Read-only validation role:

## Recovery point and timing

- Recovery source: historical timestamp / snapshot / other
- Recovery timestamp or snapshot identifier (UTC):
- Production/reference time used to calculate age (UTC):
- Actual recovery-point age:
- Recovery branch name and identifier:
- Drill start time (UTC):
- Branch ready time (UTC):
- Validation complete time (UTC):
- Drill end time (UTC):
- Proposed/approved RPO target:
- Actual RPO achieved:
- RPO result: pass / fail / not measured
- Proposed/approved RTO target:
- Actual RTO achieved:
- RTO result: pass / fail / not measured

## Read-only and schema evidence

- `transaction_read_only` reported `on`: yes / no
- Validation role had write privileges: yes / no
- If yes, compensating transaction-only control and approver acknowledgment:
- Alembic revision:
- Expected revision for selected recovery time:
- Critical relations all present: yes / no

## Sanitized row counts

| Table | Recovered count | Approved comparison count/time | Difference explained |
|---|---:|---:|---|
| users | | | |
| events | | | |
| orders | | | |
| payment_attempts | | | |
| tickets | | | |
| refunds | | | |
| financial_entries | | | |

## Relationship checks

- Ticket/order/event anomaly counts:
- Completed-order ticket quantity mismatches:
- Payment attempts missing orders:
- Provider mismatches and explanation:
- Provider-reference mismatches and explanation:
- Refunds missing orders:
- Orders over-refunded:
- Sanitized sample order/ticket review result:
- Sanitized sample payment/order review result:

## Result and evidence

- Overall result: pass / conditional pass / fail
- Findings and remediation owner/due date:
- Evidence location:
- Evidence reviewed by/date:

## Temporary branch cleanup

- Recovery branch retained for approver review: yes / no
- Cleanup authorized by:
- Exact recovery branch name and identifier re-verified before deletion: yes / no
- Cleanup/deletion status: pending / deleted / intentionally retained
- Cleanup operator and time (UTC):
- Production branch confirmed untouched after cleanup: yes / no
