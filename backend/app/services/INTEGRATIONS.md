# Integrations (Phase 26)

## Event envelope
All webhook/public integration payloads use:
- `id` (event id for dedupe)
- `type` (stable event name)
- `version` (`v1`)
- `created_at` (UTC ISO timestamp)
- `data` (event-specific object)

## Supported webhook events
- `order.paid`
- `order.refunded`
- `refund.processed`
- `transfer.accepted`
- `checkin.completed`

## Signing
Outgoing webhook request headers:
- `X-Admitly-Timestamp`
- `X-Admitly-Signature` (`v1=<hex>`)

Digest contract:
`hex(HMAC_SHA256(secret, "${timestamp}.${raw_body}"))`

## Retry semantics
- Failed deliveries are retried with bounded backoff.
- Attempt records are immutable per attempt number and auditable.
- Consumers should dedupe by event `id`.

## API keys
Use `X-API-Key: <prefix>.<secret>`.
Secrets are returned only at key creation time.
