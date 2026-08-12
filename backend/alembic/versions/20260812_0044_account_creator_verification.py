"""Move creator age/identity eligibility to the user account.

Revision ID: 20260812_0044
Revises: 20260812_0043
"""

from alembic import op
import sqlalchemy as sa


revision = "20260812_0044"
down_revision = "20260812_0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "events",
        sa.Column("creator_age_identity_verification_snapshot_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "creator_age_identity_verification_status",
            sa.String(length=32),
            server_default="pending",
            nullable=False,
        ),
    )
    op.add_column("users", sa.Column("creator_age_identity_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("creator_age_identity_verified_by_user_id", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("creator_age_identity_verification_note", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("creator_age_identity_revoked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("creator_age_identity_revoked_by_user_id", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("creator_age_identity_revocation_reason", sa.Text(), nullable=True))
    op.create_check_constraint(
        "ck_users_creator_age_identity_verification_status",
        "users",
        "creator_age_identity_verification_status IN ('pending', 'verified', 'revoked')",
    )
    op.create_foreign_key(
        "fk_users_creator_age_identity_verified_by_user_id_users",
        "users", "users", ["creator_age_identity_verified_by_user_id"], ["id"],
    )
    op.create_foreign_key(
        "fk_users_creator_age_identity_revoked_by_user_id_users",
        "users", "users", ["creator_age_identity_revoked_by_user_id"], ["id"],
    )
    op.create_index(
        op.f("ix_users_creator_age_identity_verified_by_user_id"),
        "users", ["creator_age_identity_verified_by_user_id"], unique=False,
    )
    op.create_index(
        op.f("ix_users_creator_age_identity_revoked_by_user_id"),
        "users", ["creator_age_identity_revoked_by_user_id"], unique=False,
    )

    op.create_table(
        "creator_age_identity_verification_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=False),
        sa.Column("previous_status", sa.String(length=32), nullable=False),
        sa.Column("new_status", sa.String(length=32), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_creator_age_identity_verification_history_action"),
        "creator_age_identity_verification_history", ["action"], unique=False,
    )
    op.create_index(
        op.f("ix_creator_age_identity_verification_history_actor_user_id"),
        "creator_age_identity_verification_history", ["actor_user_id"], unique=False,
    )
    op.create_index(
        op.f("ix_creator_age_identity_verification_history_user_id"),
        "creator_age_identity_verification_history", ["user_id"], unique=False,
    )

    # Trust only creators whose every legacy "verified" event record is complete
    # and points back to that event's actual creator. Pick their earliest complete
    # verification deterministically; ambiguous creators remain pending.
    op.execute(
        """
        WITH consistent_creators AS (
            SELECT op.user_id
            FROM organizer_profiles op
            JOIN events e ON e.organizer_id = op.id
            GROUP BY op.user_id
            HAVING COUNT(*) FILTER (WHERE e.creator_age_identity_verification_status = 'verified') > 0
               AND COUNT(*) FILTER (
                    WHERE e.creator_age_identity_verification_status = 'verified'
                      AND (
                        e.creator_age_identity_verified_user_id IS DISTINCT FROM op.user_id
                        OR e.creator_age_identity_verified_by_user_id IS NULL
                        OR e.creator_age_identity_verified_at IS NULL
                      )
               ) = 0
        ), ranked AS (
            SELECT
                op.user_id,
                e.creator_age_identity_verified_at AS verified_at,
                e.creator_age_identity_verified_by_user_id AS verifier_id,
                e.creator_age_identity_verification_note AS note,
                ROW_NUMBER() OVER (
                    PARTITION BY op.user_id
                    ORDER BY e.creator_age_identity_verified_at ASC, e.id ASC
                ) AS row_number
            FROM events e
            JOIN organizer_profiles op ON op.id = e.organizer_id
            JOIN consistent_creators cc ON cc.user_id = op.user_id
            WHERE e.creator_age_identity_verification_status = 'verified'
        )
        UPDATE users u
        SET creator_age_identity_verification_status = 'verified',
            creator_age_identity_verified_at = r.verified_at,
            creator_age_identity_verified_by_user_id = r.verifier_id,
            creator_age_identity_verification_note = r.note
        FROM ranked r
        WHERE r.row_number = 1 AND u.id = r.user_id
        """
    )
    op.execute(
        """
        INSERT INTO creator_age_identity_verification_history
            (user_id, action, actor_user_id, previous_status, new_status, note, created_at, updated_at)
        SELECT
            u.id, 'verified', u.creator_age_identity_verified_by_user_id,
            'pending', 'verified', u.creator_age_identity_verification_note,
            u.creator_age_identity_verified_at, u.creator_age_identity_verified_at
        FROM users u
        WHERE u.creator_age_identity_verification_status = 'verified'
          AND u.creator_age_identity_verified_by_user_id IS NOT NULL
          AND u.creator_age_identity_verified_at IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_creator_age_identity_verification_history_user_id"), table_name="creator_age_identity_verification_history")
    op.drop_index(op.f("ix_creator_age_identity_verification_history_actor_user_id"), table_name="creator_age_identity_verification_history")
    op.drop_index(op.f("ix_creator_age_identity_verification_history_action"), table_name="creator_age_identity_verification_history")
    op.drop_table("creator_age_identity_verification_history")
    op.drop_index(op.f("ix_users_creator_age_identity_revoked_by_user_id"), table_name="users")
    op.drop_index(op.f("ix_users_creator_age_identity_verified_by_user_id"), table_name="users")
    op.drop_constraint("fk_users_creator_age_identity_revoked_by_user_id_users", "users", type_="foreignkey")
    op.drop_constraint("fk_users_creator_age_identity_verified_by_user_id_users", "users", type_="foreignkey")
    op.drop_constraint("ck_users_creator_age_identity_verification_status", "users", type_="check")
    op.drop_column("users", "creator_age_identity_revocation_reason")
    op.drop_column("users", "creator_age_identity_revoked_by_user_id")
    op.drop_column("users", "creator_age_identity_revoked_at")
    op.drop_column("users", "creator_age_identity_verification_note")
    op.drop_column("users", "creator_age_identity_verified_by_user_id")
    op.drop_column("users", "creator_age_identity_verified_at")
    op.drop_column("users", "creator_age_identity_verification_status")
    op.drop_column("events", "creator_age_identity_verification_snapshot_at")
