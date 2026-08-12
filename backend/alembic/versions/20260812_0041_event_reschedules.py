"""Add durable event reschedule history.

Revision ID: 20260812_0041
Revises: 20260811_0040
"""

from alembic import op
import sqlalchemy as sa


revision = "20260812_0041"
down_revision = "20260811_0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "event_reschedules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("previous_start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("previous_end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("previous_doors_open_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("previous_sales_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("previous_sales_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("new_start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("new_end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("new_doors_open_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("new_sales_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("new_sales_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rescheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], name=op.f("fk_event_reschedules_actor_user_id_users")),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], name=op.f("fk_event_reschedules_event_id_events"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_event_reschedules")),
        sa.UniqueConstraint("event_id", "idempotency_key", name="uq_event_reschedules_event_idempotency_key"),
    )
    op.create_index(op.f("ix_event_reschedules_event_id"), "event_reschedules", ["event_id"], unique=False)
    op.create_index(op.f("ix_event_reschedules_actor_user_id"), "event_reschedules", ["actor_user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_event_reschedules_actor_user_id"), table_name="event_reschedules")
    op.drop_index(op.f("ix_event_reschedules_event_id"), table_name="event_reschedules")
    op.drop_table("event_reschedules")
