# MMG Integration Gap Report

Status: provider-independent payment hardening is in place, but live MMG is intentionally not implemented or enabled.

## Repository architecture

| Stage | Current implementation |
| --- | --- |
| Buyer checkout UI | `mobile/src/navigation/screens/CheckoutMethodScreen.tsx` starts MMG checkout or the MMG agent flow. `mobile/src/api/orders.ts` calls the backend. |
| Order/payment creation API | `backend/app/api/orders.py` exposes checkout initiation, agent initiation, and agent submission. |
| Payment orchestration | `backend/app/services/payments/__init__.py` owns order authorization, state changes, payment-attempt records, manual review, callback handling, and calls the provider boundary. |
| MMG boundary | `backend/app/services/payments/mmg.py` contains provider configuration validation and mock behavior. Live checkout, live transaction lookup, callback authentication, and live refunds are explicit errors/TODOs. |
| Browser/app redirect | A provider checkout URL is persisted on the order and opened by the mobile app. The backend return route is informational only. Official redirect/deep-link semantics are unknown. |
| Callback | `backend/app/api/payments.py` accepts callback receipt. `handle_mmg_callback` locks the order and records normalized callback facts. In live mode authenticity is `unverified`, so no callback can mark an order paid. |
| Finalization | `backend/app/services/orders.py::complete_paid_order` validates payable state, changes the order once, and invokes ticket issuance in the same database transaction. |
| Tickets | `backend/app/services/tickets.py::issue_tickets_for_completed_order` locks the order, returns an already complete ticket set, and rejects partial prior issuance. |
| Reconciliation/payout | `backend/app/services/finance_reporting.py`, finance APIs, and the admin finance page expose paid-order reconciliation and payout state. Admin mutations create action-audit records. |
| Refunds | `backend/app/services/refunds.py` tracks review and provider state. MMG approval does not void tickets or post accounting until a separately audited provider confirmation is recorded. No live provider call exists. |
| Admin/support | Admin finance exposes settlement/order reporting. Admin support shows order payment data, payment attempts, callback authenticity, refunds/disputes, timeline entries, and action audits. |

## Known from this repository

- The product calls the provider `mmg`, supports `mmg_checkout` and `mmg_agent` payment methods, and currently uses GYD order amounts with two decimal database precision.
- Current configuration names are `MMG_ENABLED`, `MMG_PROVIDER_MODE`, `MMG_BASE_URL`, `MMG_MERCHANT_ID`, `MMG_API_KEY`, `MMG_API_SECRET`, `MMG_CALLBACK_URL`, `MMG_RETURN_URL_SUCCESS`, `MMG_RETURN_URL_CANCEL`, `MMG_REQUEST_TIMEOUT_SECONDS`, `MMG_AGENT_AUTO_VERIFY_ENABLED`, and `MMG_AGENT_MANUAL_FALLBACK_ENABLED`.
- Those names are placeholders for integration wiring, not evidence of MMG's official authentication or API contract.
- Production startup rejects MMG enabled with mock mode. Provider mock functions also reject production execution.
- Live callbacks are not authenticated and therefore are only recorded as unverified observations. They cannot finalize an order.
- Orders use a unique `(payment_provider, payment_reference)` pair. Refunds use a unique `(payment_provider, provider_refund_reference)` pair.

## Required from MMG, currently unknown

Official MMG material must establish each applicable item before implementation:

- production and sandbox API base URLs;
- merchant/account identifier format and issuance process;
- authentication mechanism, credential types, scopes, rotation, and storage requirements;
- checkout/create-payment endpoint, HTTP method, request schema, response schema, and error model;
- provider transaction identifier and merchant/order reference rules, uniqueness, allowed characters, and maximum lengths;
- amount representation, rounding rules, supported currencies, and whether GYD is represented as major or minor units;
- redirect, app-link/deep-link, success, cancellation, and browser return behavior;
- callback registration requirements, delivery method, content type, payload schema, event/status vocabulary, retry policy, and ordering guarantees;
- callback authenticity mechanism, signature header names, algorithm, canonical signing input, encoding, key rotation, timestamp tolerance, and replay protections;
- authoritative transaction lookup/status endpoint and the fields used to match merchant, order, amount, currency, and provider transaction identity;
- agent-payment lookup/verification mechanism and its authoritative status lifecycle;
- provider idempotency-key support and retry semantics for payment creation, lookup, and refunds;
- refund endpoint, request/response schemas, full/partial refund rules, limits, timing, statuses, idempotency, and authoritative completion lookup;
- settlement/reconciliation reports or APIs, settlement identifiers, fee fields, payout timing, and discrepancy workflow;
- sandbox credentials/test cases, production credentials, IP allowlisting or certificate requirements, webhook certification, and launch approval process;
- official support/escalation contacts and operational status source.

## Deliberately unimplemented assumptions

Do not infer endpoint paths, JSON field names, headers, API keys, signature algorithms, callback status meanings, redirect rules, amount units, lookup behavior, retry behavior, or refund completion semantics from the current placeholder configuration or mock code. Live enablement must remain off until the official contract is implemented and verified in MMG's sandbox.

## Integration acceptance criteria

Once the official contract is available, the provider boundary must authenticate callbacks before any paid transition; perform authoritative lookup when required; match provider transaction, merchant/order identity, amount, and currency; use provider-supported idempotency; preserve the existing row-lock/transaction/ticket guarantees; implement observable retries without logging secrets; reconcile sandbox settlement data; and pass duplicate, replay, out-of-order, mismatch, expiry, refund, and failure tests before production enablement.
