# Payment reconciliation and refund SOP

## Daily reconciliation

1. Obtain the MMG settlement/export through the approved authenticated channel. Store it only in the restricted finance location.
2. Match provider reference, order reference, currency, gross amount, fees, net amount, status, and settlement date against payment attempts, orders, refunds, disputes, and financial entries.
3. Classify exceptions: provider-paid/order-pending, order-complete/provider-missing, amount mismatch, duplicate callback/reference, stale pending verification, refund mismatch, or chargeback.
4. Never mark a payment verified from buyer-supplied evidence alone. Verify in the provider portal/API and require a second approver for manual completion.
5. Record each exception, evidence, owner, next action, and resolution. Aggregate totals must reconcile before payout approval.

## Refund processing

1. Confirm requester authority, event policy/status, current ticket ownership, check-in/transfer state, prior refunds or disputes, refundable amount, currency, and original settled provider reference.
2. Obtain required approval and create the refund through admin tooling. Do not edit order, ticket, or ledger rows directly.
3. Submit to MMG, store the provider refund reference, and leave the refund pending until provider confirmation. A queued response is not completion.
4. On verified completion, reconcile financial entries and ticket/order state, then notify the buyer. On failure, preserve the original state and route the exception for review.
5. Reconcile pending refunds daily until terminal. Investigate callbacks that are invalid, unsigned, duplicated, out of order, or do not match amount/currency/reference.

## Release blocker

The repository’s live MMG checkout creation, callback authenticity verification, live reference lookup, and refund calls are not implemented. Do not enable `MMG_PROVIDER_MODE=live` until MMG’s official API contract, signature/key-rotation rules, idempotency behavior, sandbox certification, credentials, and settlement exports have been implemented and tested.
