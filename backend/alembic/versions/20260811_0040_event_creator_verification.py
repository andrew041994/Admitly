"""Add event creator age and identity verification metadata.

Revision ID: 20260811_0040
Revises: 20260811_0039
"""

from alembic import op
import sqlalchemy as sa


revision = "20260811_0040"
down_revision = "20260811_0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "events",
        sa.Column(
            "creator_age_identity_verification_status",
            sa.String(length=32),
            nullable=False,
            server_default="pending",
        ),
    )
    op.add_column(
        "events",
        sa.Column("creator_age_identity_verified_user_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "events",
        sa.Column("creator_age_identity_verified_by_user_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "events",
        sa.Column("creator_age_identity_verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "events",
        sa.Column("creator_age_identity_verification_note", sa.Text(), nullable=True),
    )
    op.create_foreign_key(
        "fk_events_creator_age_identity_verified_user_id_users",
        "events",
        "users",
        ["creator_age_identity_verified_user_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_events_creator_age_identity_verified_by_user_id_users",
        "events",
        "users",
        ["creator_age_identity_verified_by_user_id"],
        ["id"],
    )
    op.create_index(
        op.f("ix_events_creator_age_identity_verified_user_id"),
        "events",
        ["creator_age_identity_verified_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_events_creator_age_identity_verified_by_user_id"),
        "events",
        ["creator_age_identity_verified_by_user_id"],
        unique=False,
    )
    op.create_check_constraint(
        "ck_events_creator_age_identity_verification_status",
        "events",
        "creator_age_identity_verification_status IN ('pending', 'verified')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_events_creator_age_identity_verification_status",
        "events",
        type_="check",
    )
    op.drop_index(
        op.f("ix_events_creator_age_identity_verified_by_user_id"),
        table_name="events",
    )
    op.drop_index(
        op.f("ix_events_creator_age_identity_verified_user_id"),
        table_name="events",
    )
    op.drop_constraint(
        "fk_events_creator_age_identity_verified_by_user_id_users",
        "events",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_events_creator_age_identity_verified_user_id_users",
        "events",
        type_="foreignkey",
    )
    op.drop_column("events", "creator_age_identity_verification_note")
    op.drop_column("events", "creator_age_identity_verified_at")
    op.drop_column("events", "creator_age_identity_verified_by_user_id")
    op.drop_column("events", "creator_age_identity_verified_user_id")
    op.drop_column("events", "creator_age_identity_verification_status")
