# Migration 0039 production-data preflight

Migration `20260811_0039_payment_callback_hardening.py` adds unique order and refund provider-reference constraints. Run this preflight before scheduling the migration.

## Safety requirements

- Use a Neon role that is explicitly restricted to `SELECT`, or otherwise independently verified as read-only.
- Start the session with `BEGIN TRANSACTION READ ONLY` and verify `transaction_read_only` is `on`.
- Do not normalize, update, delete, merge, or otherwise repair records during this procedure.
- Return only record IDs, counts, provider names, lengths, and hashed reference fingerprints to tickets or chat. Treat raw payment references as restricted financial identifiers.
- Any exact duplicate order provider/reference group blocks migration 0039.
- Whitespace, case, identity, or state inconsistencies require financial review even when PostgreSQL would permit them.

`authenticity_status` belongs to `payment_attempts`, not `refunds`. The provider refund fields belong to `refunds`.

## Pre-migration queries

```sql
BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '60s';

SELECT
    current_setting('transaction_read_only') AS transaction_read_only,
    version_num AS alembic_version
FROM alembic_version;

-- Must return transaction_read_only=on. Record the current migration revision.

-- Exact duplicates that block the new order constraint.
WITH duplicate_groups AS (
    SELECT
        payment_provider,
        payment_reference,
        COUNT(*) AS row_count,
        ARRAY_AGG(id ORDER BY id) AS order_ids
    FROM orders
    WHERE payment_provider IS NOT NULL
      AND payment_reference IS NOT NULL
    GROUP BY payment_provider, payment_reference
    HAVING COUNT(*) > 1
)
SELECT
    payment_provider,
    MD5(payment_reference) AS reference_fingerprint,
    LENGTH(payment_reference) AS reference_length,
    row_count,
    order_ids
FROM duplicate_groups
ORDER BY row_count DESC, payment_provider;

-- Clean result: conflicting_group_count=0 and affected_order_count=0.
WITH duplicate_groups AS (
    SELECT COUNT(*) AS row_count
    FROM orders
    WHERE payment_provider IS NOT NULL
      AND payment_reference IS NOT NULL
    GROUP BY payment_provider, payment_reference
    HAVING COUNT(*) > 1
)
SELECT
    COUNT(*) AS conflicting_group_count,
    COALESCE(SUM(row_count), 0) AS affected_order_count
FROM duplicate_groups;

-- Clean result: no rows.
SELECT issue, COUNT(*) AS row_count, ARRAY_AGG(id ORDER BY id) AS order_ids
FROM (
    SELECT id, 'blank_payment_provider' AS issue
    FROM orders WHERE payment_provider = ''
    UNION ALL
    SELECT id, 'blank_payment_reference'
    FROM orders WHERE payment_reference = ''
    UNION ALL
    SELECT id, 'payment_provider_whitespace'
    FROM orders
    WHERE payment_provider IS NOT NULL AND payment_provider <> BTRIM(payment_provider)
    UNION ALL
    SELECT id, 'payment_reference_whitespace'
    FROM orders
    WHERE payment_reference IS NOT NULL AND payment_reference <> BTRIM(payment_reference)
) issues
GROUP BY issue
ORDER BY issue;

-- Trim-normalized variants. Clean result: no rows.
WITH normalized AS (
    SELECT
        id,
        BTRIM(payment_provider) AS normalized_provider,
        BTRIM(payment_reference) AS normalized_reference,
        payment_provider,
        payment_reference
    FROM orders
    WHERE payment_provider IS NOT NULL AND payment_reference IS NOT NULL
), conflicts AS (
    SELECT
        normalized_provider,
        normalized_reference,
        COUNT(*) AS row_count,
        COUNT(DISTINCT (payment_provider, payment_reference)) AS exact_variant_count,
        ARRAY_AGG(id ORDER BY id) AS order_ids
    FROM normalized
    GROUP BY normalized_provider, normalized_reference
    HAVING COUNT(DISTINCT (payment_provider, payment_reference)) > 1
)
SELECT
    normalized_provider,
    MD5(normalized_reference) AS reference_fingerprint,
    LENGTH(normalized_reference) AS reference_length,
    row_count,
    exact_variant_count,
    order_ids
FROM conflicts
ORDER BY row_count DESC;

-- Case-and-trim-normalized variants. Clean result: no rows.
WITH normalized AS (
    SELECT
        id,
        LOWER(BTRIM(payment_provider)) AS normalized_provider,
        LOWER(BTRIM(payment_reference)) AS normalized_reference,
        payment_provider,
        payment_reference
    FROM orders
    WHERE payment_provider IS NOT NULL AND payment_reference IS NOT NULL
), conflicts AS (
    SELECT
        normalized_provider,
        normalized_reference,
        COUNT(*) AS row_count,
        COUNT(DISTINCT (payment_provider, payment_reference)) AS exact_variant_count,
        ARRAY_AGG(id ORDER BY id) AS order_ids
    FROM normalized
    GROUP BY normalized_provider, normalized_reference
    HAVING COUNT(DISTINCT (payment_provider, payment_reference)) > 1
)
SELECT
    normalized_provider,
    MD5(normalized_reference) AS reference_fingerprint,
    LENGTH(normalized_reference) AS reference_length,
    row_count,
    exact_variant_count,
    order_ids
FROM conflicts
ORDER BY row_count DESC;

-- Order state/provider consistency. Clean result: no rows.
SELECT issue, COUNT(*) AS row_count, ARRAY_AGG(id ORDER BY id) AS order_ids
FROM (
    SELECT id, 'provider_without_reference' AS issue
    FROM orders WHERE payment_provider IS NOT NULL AND payment_reference IS NULL
    UNION ALL
    SELECT id, 'reference_without_provider'
    FROM orders WHERE payment_reference IS NOT NULL AND payment_provider IS NULL
    UNION ALL
    SELECT id, 'mmg_method_with_non_mmg_provider'
    FROM orders
    WHERE payment_method IN ('mmg_checkout', 'mmg_agent')
      AND payment_provider IS DISTINCT FROM 'mmg'
    UNION ALL
    SELECT id, 'verified_payment_missing_identity'
    FROM orders
    WHERE payment_verification_status = 'verified'
      AND (
          payment_provider IS NULL OR payment_reference IS NULL
          OR payment_provider = '' OR payment_reference = ''
      )
    UNION ALL
    SELECT id, 'completed_order_not_verified'
    FROM orders
    WHERE status = 'completed'
      AND payment_verification_status IS DISTINCT FROM 'verified'
) issues
GROUP BY issue
ORDER BY issue;

-- Payment-attempt/provider consistency. Clean result: zero mismatches.
SELECT
    COUNT(*) AS mismatch_count,
    ARRAY_AGG(pa.id ORDER BY pa.id) AS payment_attempt_ids,
    ARRAY_AGG(DISTINCT pa.order_id ORDER BY pa.order_id) AS order_ids
FROM payment_attempts pa
JOIN orders o ON o.id = pa.order_id
WHERE pa.provider_reference IS NOT NULL
  AND (
      pa.provider IS DISTINCT FROM o.payment_provider
      OR pa.provider_reference IS DISTINCT FROM o.payment_reference
  );

-- Informational counts of rows that receive migration defaults.
SELECT
    (SELECT COUNT(*) FROM payment_attempts) AS payment_attempts_to_backfill,
    (SELECT COUNT(*) FROM refunds) AS refunds_to_backfill;

-- Correct table ownership for all migration-0039 fields.
SELECT
    EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'payment_attempts'
          AND column_name = 'authenticity_status'
    ) AS payment_attempt_authenticity_present,
    (
        SELECT COUNT(*) = 5
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'refunds'
          AND column_name IN (
              'payment_provider',
              'provider_refund_reference',
              'provider_status',
              'provider_submitted_at',
              'provider_verified_at'
          )
    ) AS refund_provider_columns_present;

ROLLBACK;
```

Before migration 0039, the new refund provider columns do not exist, so historical refund references cannot conflict. Existing refunds will receive `provider_status='not_submitted'` and `NULL` provider/reference values.

If the final schema-presence query reports that the refund fields already exist, use a read-only session to check exact duplicate `(payment_provider, provider_refund_reference)` groups, blank references, whitespace/case variants, references without providers, and `verified` rows without references. Do not attempt that query against schema 0038 because the columns do not exist.

```sql
BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '60s';

-- Clean result: no rows. Any row blocks reapplying/validating the constraint.
WITH duplicate_groups AS (
    SELECT
        payment_provider,
        provider_refund_reference,
        COUNT(*) AS row_count,
        ARRAY_AGG(id ORDER BY id) AS refund_ids
    FROM refunds
    WHERE payment_provider IS NOT NULL
      AND provider_refund_reference IS NOT NULL
    GROUP BY payment_provider, provider_refund_reference
    HAVING COUNT(*) > 1
)
SELECT
    payment_provider,
    MD5(provider_refund_reference) AS reference_fingerprint,
    LENGTH(provider_refund_reference) AS reference_length,
    row_count,
    refund_ids
FROM duplicate_groups
ORDER BY row_count DESC, payment_provider;

-- Clean result: no rows.
SELECT issue, COUNT(*) AS row_count, ARRAY_AGG(id ORDER BY id) AS refund_ids
FROM (
    SELECT id, 'provider_reference_without_provider' AS issue
    FROM refunds
    WHERE provider_refund_reference IS NOT NULL
      AND (payment_provider IS NULL OR payment_provider = '')
    UNION ALL
    SELECT id, 'blank_provider_reference'
    FROM refunds WHERE provider_refund_reference = ''
    UNION ALL
    SELECT id, 'provider_whitespace'
    FROM refunds
    WHERE payment_provider IS NOT NULL
      AND payment_provider <> BTRIM(payment_provider)
    UNION ALL
    SELECT id, 'reference_whitespace'
    FROM refunds
    WHERE provider_refund_reference IS NOT NULL
      AND provider_refund_reference <> BTRIM(provider_refund_reference)
    UNION ALL
    SELECT id, 'verified_without_reference'
    FROM refunds
    WHERE provider_status = 'verified'
      AND (
          payment_provider IS NULL OR provider_refund_reference IS NULL
          OR payment_provider = '' OR provider_refund_reference = ''
      )
    UNION ALL
    SELECT id, 'verified_timestamp_without_verified_status'
    FROM refunds
    WHERE provider_verified_at IS NOT NULL
      AND provider_status <> 'verified'
) issues
GROUP BY issue
ORDER BY issue;

-- Case-and-trim variants. Clean result: no rows.
WITH normalized AS (
    SELECT
        id,
        LOWER(BTRIM(payment_provider)) AS normalized_provider,
        LOWER(BTRIM(provider_refund_reference)) AS normalized_reference,
        payment_provider,
        provider_refund_reference
    FROM refunds
    WHERE payment_provider IS NOT NULL
      AND provider_refund_reference IS NOT NULL
), conflicts AS (
    SELECT
        normalized_provider,
        normalized_reference,
        COUNT(*) AS row_count,
        COUNT(DISTINCT (payment_provider, provider_refund_reference)) AS exact_variant_count,
        ARRAY_AGG(id ORDER BY id) AS refund_ids
    FROM normalized
    GROUP BY normalized_provider, normalized_reference
    HAVING COUNT(DISTINCT (payment_provider, provider_refund_reference)) > 1
)
SELECT
    normalized_provider,
    MD5(normalized_reference) AS reference_fingerprint,
    LENGTH(normalized_reference) AS reference_length,
    row_count,
    exact_variant_count,
    refund_ids
FROM conflicts
ORDER BY row_count DESC;

ROLLBACK;
```

## Blocking results

Do not run migration 0039 when:

- any exact duplicate non-null order provider/reference group exists;
- the preflight was not executed through a verified read-only session;
- unexplained completed/unverified or verified/missing-identity orders exist;
- payment attempts disagree with their order identity without an approved financial explanation;
- normalized variants remain unreviewed;
- the deployment owner has not accounted for the migration's non-concurrent index/constraint locks.

Create a remediation proposal for finance/support review. Do not automate remediation and do not expose raw provider references in ordinary tickets.
