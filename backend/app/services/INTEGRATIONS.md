# Integrations (Phase 26 — Hardening)

## API key auth
Use `X-API-Key: <prefix>.<secret>` for `/public/integrations/*` routes.

- Secret material is returned **only** at key creation time.
- List views expose key metadata (`name`, `key_prefix`, `scopes`, `last_used_at`, `revoked_at`).
- Revoked keys are rejected at authentication time.

## Supported scopes
- `integrations:read` — read integration catalog.
- `integrations:write` — reserved for write-capable public integration APIs.

Unknown scopes are ignored; an empty scope set falls back to `integrations:read`.

## Webhook events
Current supported event types:
- `order.paid`
- `order.refunded`
- `refund.processed`
- `transfer.accepted`
- `checkin.completed`

## Envelope contract (stable)
All outbound webhook payloads use the same envelope shape:

```json
{
  "id": "evt_...",
  "type": "order.paid",
  "version": "v1",
  "created_at": "2026-04-07T10:00:00+00:00",
  "data": { "order_id": 123 }
}
```

Required keys are always: `id`, `type`, `version`, `created_at`, `data`.
Consumers should dedupe by `id`.

## Signature verification
Outgoing webhook request headers:
- `X-Admitly-Timestamp`
- `X-Admitly-Signature` (`v1=<hex>`)

Digest contract:
`hex(HMAC_SHA256(secret, "${timestamp}.${raw_body}"))`

Verify against the **raw** request body.

## Retry and redelivery behavior
- Automatic retries are scheduled with bounded backoff after non-2xx responses or transport failures.
- Manual redelivery is an explicit admin/internal action and creates a **new delivery attempt row**.
- Manual redelivery reuses the original webhook event envelope (`event_id`/payload unchanged).
- Delivery diagnostics expose attempt status, response code, failure reason, next retry time, and delivery kind:
  - `automatic_initial`
  - `automatic_retry`
  - `manual_redelivery`

## Debug notes
Common failure classes:
- `http_<status>` for provider HTTP errors.
- short transport/network exception text (truncated).

Delivery diagnostics intentionally omit secrets.
