"""Add durable in-app notifications and push dispatch.

Revision ID: 20260805_0038
Revises: 20260805_0037
Create Date: 2026-08-05 12:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260805_0038"
down_revision = "20260805_0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE reminder_type ADD VALUE IF NOT EXISTS '1_hour_before'")

    op.add_column("push_tokens", sa.Column("installation_id", sa.String(length=128), nullable=True))
    op.add_column("push_tokens", sa.Column("last_registered_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("push_tokens", sa.Column("disabled_reason", sa.String(length=64), nullable=True))
    op.create_unique_constraint("uq_push_tokens_installation_id", "push_tokens", ["installation_id"])

    op.create_table(
        "notification_preferences",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("ticket_activity_push_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("event_reminders_push_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("nearby_events_push_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("location_discovery_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("location_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", name="uq_notification_preferences_user_id"),
    )
    op.create_index("ix_notification_preferences_user_id", "notification_preferences", ["user_id"])

    op.create_table(
        "user_notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("notification_type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("body", sa.String(length=500), nullable=False),
        sa.Column("is_read", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("route_key", sa.String(length=32), nullable=True),
        sa.Column("route_params", sa.JSON(), server_default=sa.text("'{}'::json"), nullable=False),
        sa.Column("related_entity_type", sa.String(length=32), nullable=True),
        sa.Column("related_entity_id", sa.Integer(), nullable=True),
        sa.Column("dedupe_key", sa.String(length=255), nullable=False),
        sa.Column("push_status", sa.String(length=32), server_default="not_queued", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("dedupe_key", name="uq_user_notifications_dedupe_key"),
    )
    op.create_index("ix_user_notifications_user_id", "user_notifications", ["user_id"])
    op.create_index("ix_user_notifications_notification_type", "user_notifications", ["notification_type"])
    op.create_index("ix_user_notifications_related_entity_type", "user_notifications", ["related_entity_type"])
    op.create_index("ix_user_notifications_related_entity_id", "user_notifications", ["related_entity_id"])
    op.create_index("ix_user_notifications_push_status", "user_notifications", ["push_status"])
    op.create_index("ix_user_notifications_user_created", "user_notifications", ["user_id", "created_at"])
    op.create_index("ix_user_notifications_user_unread", "user_notifications", ["user_id", "is_read", "created_at"])

    op.create_table(
        "push_dispatches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("notification_id", sa.Integer(), nullable=False),
        sa.Column("push_token_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_ticket_id", sa.String(length=255), nullable=True),
        sa.Column("provider_status", sa.String(length=64), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["notification_id"], ["user_notifications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["push_token_id"], ["push_tokens.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("notification_id", "push_token_id", name="uq_push_dispatch_notification_token"),
    )
    op.create_index("ix_push_dispatches_notification_id", "push_dispatches", ["notification_id"])
    op.create_index("ix_push_dispatches_push_token_id", "push_dispatches", ["push_token_id"])
    op.create_index("ix_push_dispatches_status", "push_dispatches", ["status"])
    op.create_index("ix_push_dispatches_provider_ticket_id", "push_dispatches", ["provider_ticket_id"])
    op.create_index("ix_push_dispatches_claim", "push_dispatches", ["status", "next_attempt_at", "id"])

    op.create_table(
        "notification_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_type", sa.String(length=32), nullable=False),
        sa.Column("dedupe_key", sa.String(length=255), nullable=False),
        sa.Column("related_entity_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_cursor_id", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("dedupe_key", name="uq_notification_jobs_dedupe_key"),
    )
    op.create_index("ix_notification_jobs_job_type", "notification_jobs", ["job_type"])
    op.create_index("ix_notification_jobs_related_entity_id", "notification_jobs", ["related_entity_id"])
    op.create_index("ix_notification_jobs_status", "notification_jobs", ["status"])
    op.create_index("ix_notification_jobs_run_at", "notification_jobs", ["run_at"])
    op.create_index("ix_notification_jobs_claim", "notification_jobs", ["status", "run_at", "id"])


def downgrade() -> None:
    op.drop_table("notification_jobs")
    op.drop_table("push_dispatches")
    op.drop_table("user_notifications")
    op.drop_table("notification_preferences")
    op.drop_constraint("uq_push_tokens_installation_id", "push_tokens", type_="unique")
    op.drop_column("push_tokens", "disabled_reason")
    op.drop_column("push_tokens", "last_registered_at")
    op.drop_column("push_tokens", "installation_id")
    # PostgreSQL enum values cannot be removed safely during downgrade; the unused value remains.
