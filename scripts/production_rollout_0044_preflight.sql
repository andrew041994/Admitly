\set ON_ERROR_STOP on
\pset pager off

-- Admitly 20260812_0044 production preflight. Run only with a read-only role:
-- psql "$READ_ONLY_DATABASE_URL" -X -f scripts/production_rollout_0044_preflight.sql
-- Prints counts and schema facts only; never selects user PII.

BEGIN TRANSACTION READ ONLY;

SELECT current_setting('transaction_read_only') AS transaction_read_only;

SELECT to_regclass('public.alembic_version') IS NOT NULL AS has_alembic_version \gset
\if :has_alembic_version
SELECT version_num AS current_alembic_revision FROM alembic_version ORDER BY version_num;
SELECT count(*) AS alembic_revision_row_count FROM alembic_version;
\else
SELECT 'MISSING' AS current_alembic_revision;
\endif

WITH required(table_name) AS (
  VALUES ('users'), ('organizer_profiles'), ('events'), ('alembic_version')
)
SELECT r.table_name, to_regclass('public.' || r.table_name) IS NOT NULL AS present
FROM required r ORDER BY r.table_name;

SELECT to_regclass('public.users') IS NOT NULL
   AND to_regclass('public.organizer_profiles') IS NOT NULL
   AND to_regclass('public.events') IS NOT NULL AS has_required_base_tables \gset

\if :has_required_base_tables
SELECT count(*) AS user_count FROM users;
SELECT count(*) AS creator_account_count FROM organizer_profiles;
SELECT count(*) AS event_count FROM events;
SELECT count(*) AS approved_event_count FROM events WHERE approval_status = 'approved';

SELECT EXISTS (
  SELECT 1 FROM information_schema.columns
  WHERE table_schema = 'public' AND table_name = 'events'
    AND column_name = 'creator_age_identity_verification_status'
) AS has_legacy_event_verification \gset

\if :has_legacy_event_verification
SELECT count(*) AS legacy_verified_event_count
FROM events WHERE creator_age_identity_verification_status = 'verified';

SELECT count(*) AS legacy_verified_event_complete_and_creator_consistent_count
FROM events e JOIN organizer_profiles op ON op.id = e.organizer_id
WHERE e.creator_age_identity_verification_status = 'verified'
  AND e.creator_age_identity_verified_user_id = op.user_id
  AND e.creator_age_identity_verified_by_user_id IS NOT NULL
  AND e.creator_age_identity_verified_at IS NOT NULL;

SELECT count(*) AS legacy_verified_event_inconsistent_or_incomplete_count
FROM events e LEFT JOIN organizer_profiles op ON op.id = e.organizer_id
WHERE e.creator_age_identity_verification_status = 'verified'
  AND (op.id IS NULL
    OR e.creator_age_identity_verified_user_id IS DISTINCT FROM op.user_id
    OR e.creator_age_identity_verified_by_user_id IS NULL
    OR e.creator_age_identity_verified_at IS NULL);

SELECT count(*) AS legacy_pending_event_with_verification_metadata_count
FROM events
WHERE creator_age_identity_verification_status = 'pending'
  AND (creator_age_identity_verified_user_id IS NOT NULL
    OR creator_age_identity_verified_by_user_id IS NOT NULL
    OR creator_age_identity_verified_at IS NOT NULL
    OR creator_age_identity_verification_note IS NOT NULL);

SELECT count(*) AS creator_accounts_with_conflicting_verified_user_metadata_count
FROM (
  SELECT op.user_id
  FROM organizer_profiles op JOIN events e ON e.organizer_id = op.id
  WHERE e.creator_age_identity_verification_status = 'verified'
  GROUP BY op.user_id
  HAVING count(DISTINCT e.creator_age_identity_verified_user_id)
           FILTER (WHERE e.creator_age_identity_verified_user_id IS NOT NULL) > 1
      OR bool_or(e.creator_age_identity_verified_user_id IS DISTINCT FROM op.user_id)
) conflicts;

SELECT count(*) AS creator_accounts_with_incomplete_or_mismatched_verified_evidence_count
FROM (
  SELECT op.user_id
  FROM organizer_profiles op JOIN events e ON e.organizer_id = op.id
  WHERE e.creator_age_identity_verification_status = 'verified'
  GROUP BY op.user_id
  HAVING bool_or(e.creator_age_identity_verified_user_id IS DISTINCT FROM op.user_id
    OR e.creator_age_identity_verified_by_user_id IS NULL
    OR e.creator_age_identity_verified_at IS NULL)
) ambiguous;

-- These prospective 0044 dispositions are mutually exclusive over creators.
WITH evidence AS (
  SELECT op.user_id,
    count(*) FILTER (WHERE e.creator_age_identity_verification_status = 'verified') AS verified_event_count,
    count(*) FILTER (
      WHERE e.creator_age_identity_verification_status = 'verified'
        AND (e.creator_age_identity_verified_user_id IS DISTINCT FROM op.user_id
          OR e.creator_age_identity_verified_by_user_id IS NULL
          OR e.creator_age_identity_verified_at IS NULL)
    ) AS ambiguous_event_count
  FROM organizer_profiles op LEFT JOIN events e ON e.organizer_id = op.id
  GROUP BY op.user_id
)
SELECT
  count(*) FILTER (WHERE verified_event_count > 0 AND ambiguous_event_count = 0)
    AS creator_accounts_that_0044_will_verify,
  count(*) FILTER (WHERE verified_event_count = 0)
    AS creator_accounts_remaining_pending_without_prior_verification,
  count(*) FILTER (WHERE verified_event_count > 0 AND ambiguous_event_count > 0)
    AS creator_accounts_requiring_manual_review
FROM evidence;

SELECT count(*) AS events_with_missing_organizer_reference_count
FROM events e LEFT JOIN organizer_profiles op ON op.id = e.organizer_id WHERE op.id IS NULL;
SELECT count(*) AS legacy_verified_subject_missing_user_reference_count
FROM events e LEFT JOIN users u ON u.id = e.creator_age_identity_verified_user_id
WHERE e.creator_age_identity_verified_user_id IS NOT NULL AND u.id IS NULL;
SELECT count(*) AS legacy_verifier_missing_user_reference_count
FROM events e LEFT JOIN users u ON u.id = e.creator_age_identity_verified_by_user_id
WHERE e.creator_age_identity_verified_by_user_id IS NOT NULL AND u.id IS NULL;
\else
SELECT 'MISSING: migration 20260811_0040 event verification columns' AS blocking_condition;
\endif
\else
SELECT 'MISSING: one or more required base tables' AS blocking_condition;
\endif

SELECT to_regclass('public.auth_sessions') IS NOT NULL AS has_auth_sessions \gset
SELECT :has_auth_sessions::boolean AS auth_sessions_table_present;
\if :has_auth_sessions
SELECT count(*) AS auth_session_count FROM auth_sessions;
SELECT
  count(*) FILTER (WHERE c.contype = 'p') AS primary_key_constraint_count,
  count(*) FILTER (WHERE c.contype = 'u') AS unique_constraint_count,
  count(*) FILTER (WHERE c.contype = 'f' AND c.confrelid = 'public.users'::regclass)
    AS users_foreign_key_constraint_count
FROM pg_constraint c
WHERE c.conrelid = 'public.auth_sessions'::regclass;
SELECT
  to_regclass('public.ix_auth_sessions_expires_at') IS NOT NULL AS has_expires_index,
  to_regclass('public.ix_auth_sessions_user_active') IS NOT NULL AS has_user_active_index,
  to_regclass('public.ix_auth_sessions_user_id') IS NOT NULL AS has_user_id_index;
SELECT count(*) AS auth_session_orphan_user_count
FROM auth_sessions s LEFT JOIN users u ON u.id = s.user_id WHERE u.id IS NULL;
SELECT count(*) AS auth_session_duplicate_refresh_hash_group_count
FROM (SELECT refresh_token_hash FROM auth_sessions GROUP BY refresh_token_hash HAVING count(*) > 1) d;
SELECT count(*) AS auth_session_invalid_shape_count
FROM auth_sessions
WHERE id = '' OR length(id) > 64 OR refresh_token_hash !~ '^[0-9a-f]{64}$'
   OR expires_at IS NULL OR created_at IS NULL OR updated_at IS NULL;
SELECT count(*) AS auth_session_invalid_lifecycle_count
FROM auth_sessions
WHERE expires_at <= created_at
   OR (revoked_at IS NULL AND revocation_reason IS NOT NULL)
   OR (revoked_at IS NOT NULL AND revocation_reason IS NULL);
SELECT count(*) AS auth_session_active_but_expired_count
FROM auth_sessions WHERE revoked_at IS NULL AND expires_at <= now();
\endif

SELECT EXISTS (
  SELECT 1 FROM information_schema.columns
  WHERE table_schema = 'public' AND table_name = 'users'
    AND column_name = 'creator_age_identity_verification_status'
) AS has_account_verification \gset
SELECT :has_account_verification::boolean AS account_verification_columns_present;
\if :has_account_verification
SELECT count(*) AS account_verification_status_check_constraint_count
FROM pg_constraint
WHERE conrelid = 'public.users'::regclass
  AND contype = 'c'
  AND conname = 'ck_users_creator_age_identity_verification_status';
SELECT count(*) AS account_verification_actor_foreign_key_count
FROM pg_constraint
WHERE conrelid = 'public.users'::regclass
  AND contype = 'f'
  AND conname IN (
    'fk_users_creator_age_identity_verified_by_user_id_users',
    'fk_users_creator_age_identity_revoked_by_user_id_users'
  );
SELECT creator_age_identity_verification_status, count(*) AS user_count
FROM users GROUP BY creator_age_identity_verification_status ORDER BY 1;
SELECT count(*) AS invalid_account_verification_status_count
FROM users WHERE creator_age_identity_verification_status NOT IN ('pending', 'verified', 'revoked')
   OR creator_age_identity_verification_status IS NULL;
SELECT count(*) AS verified_account_incomplete_metadata_count
FROM users WHERE creator_age_identity_verification_status = 'verified'
  AND (creator_age_identity_verified_at IS NULL OR creator_age_identity_verified_by_user_id IS NULL);
SELECT count(*) AS revoked_account_incomplete_metadata_count
FROM users WHERE creator_age_identity_verification_status = 'revoked'
  AND (creator_age_identity_revoked_at IS NULL OR creator_age_identity_revoked_by_user_id IS NULL
    OR nullif(btrim(creator_age_identity_revocation_reason), '') IS NULL);
SELECT count(*) AS account_verified_by_missing_user_reference_count
FROM users subject LEFT JOIN users actor ON actor.id = subject.creator_age_identity_verified_by_user_id
WHERE subject.creator_age_identity_verified_by_user_id IS NOT NULL AND actor.id IS NULL;
SELECT count(*) AS account_revoked_by_missing_user_reference_count
FROM users subject LEFT JOIN users actor ON actor.id = subject.creator_age_identity_revoked_by_user_id
WHERE subject.creator_age_identity_revoked_by_user_id IS NOT NULL AND actor.id IS NULL;
\endif

SELECT to_regclass('public.creator_age_identity_verification_history') IS NOT NULL AS has_verification_history \gset
SELECT :has_verification_history::boolean AS verification_history_table_present;
\if :has_verification_history
SELECT
  count(*) FILTER (WHERE c.contype = 'p') AS history_primary_key_constraint_count,
  count(*) FILTER (WHERE c.contype = 'f' AND c.confrelid = 'public.users'::regclass)
    AS history_users_foreign_key_constraint_count
FROM pg_constraint c
WHERE c.conrelid = 'public.creator_age_identity_verification_history'::regclass;
SELECT count(*) AS verification_history_count FROM creator_age_identity_verification_history;
SELECT count(*) AS verification_history_invalid_reference_count
FROM creator_age_identity_verification_history h
LEFT JOIN users subject ON subject.id = h.user_id
LEFT JOIN users actor ON actor.id = h.actor_user_id
WHERE subject.id IS NULL OR actor.id IS NULL;
SELECT count(*) AS verification_history_invalid_state_count
FROM creator_age_identity_verification_history
WHERE action NOT IN ('verified', 'revoked')
   OR previous_status NOT IN ('pending', 'verified', 'revoked')
   OR new_status NOT IN ('pending', 'verified', 'revoked');
SELECT count(*) AS verified_account_without_verified_history_count
FROM users u WHERE u.creator_age_identity_verification_status = 'verified'
  AND NOT EXISTS (SELECT 1 FROM creator_age_identity_verification_history h
    WHERE h.user_id = u.id AND h.action = 'verified');
\endif

SELECT EXISTS (
  SELECT 1 FROM information_schema.columns
  WHERE table_schema = 'public' AND table_name = 'events'
    AND column_name = 'creator_age_identity_verification_snapshot_at'
) AS has_event_verification_snapshot \gset
SELECT :has_event_verification_snapshot::boolean AS event_verification_snapshot_column_present;
\if :has_event_verification_snapshot
SELECT count(*) AS approved_verified_events_without_snapshot_count
FROM events WHERE approval_status = 'approved'
  AND creator_age_identity_verification_status = 'verified'
  AND creator_age_identity_verification_snapshot_at IS NULL;
\endif

ROLLBACK;
