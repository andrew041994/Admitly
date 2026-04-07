"""Phase 15 event cancellation refund batches

Revision ID: 20260407_0015
Revises: 20260407_0014
Create Date: 2026-04-07 18:20:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260407_0015"
down_revision: Union[str, None] = "20260407_0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


event_refund_batch_status_enum = postgresql.ENUM(
    "pending", "processing", "completed", "failed", name="event_refund_batch_status", create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()
    event_refund_batch_status_enum.create(bind, checkfirst=True)

    op.create_table(
        "event_refund_batches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("initiated_by_user_id", sa.Integer(), nullable=True),
        sa.Column("status", event_refund_batch_status_enum, nullable=False),
        sa.Column("total_orders", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processed_orders", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("successful_refunds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_orders", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_orders", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"]),
        sa.ForeignKeyConstraint(["initiated_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_event_refund_batches_event_id"), "event_refund_batches", ["event_id"], unique=False)
    op.create_index(op.f("ix_event_refund_batches_initiated_by_user_id"), "event_refund_batches", ["initiated_by_user_id"], unique=False)
    op.create_index(op.f("ix_event_refund_batches_status"), "event_refund_batches", ["status"], unique=False)
    op.create_index(op.f("ix_event_refund_batches_created_at"), "event_refund_batches", ["created_at"], unique=False)
    op.create_index(
        "uq_event_refund_batches_active_event",
        "event_refund_batches",
        ["event_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending', 'processing')"),
    )


def downgrade() -> None:
    op.drop_index("uq_event_refund_batches_active_event", table_name="event_refund_batches")
    op.drop_index(op.f("ix_event_refund_batches_created_at"), table_name="event_refund_batches")
    op.drop_index(op.f("ix_event_refund_batches_status"), table_name="event_refund_batches")
    op.drop_index(op.f("ix_event_refund_batches_initiated_by_user_id"), table_name="event_refund_batches")
    op.drop_index(op.f("ix_event_refund_batches_event_id"), table_name="event_refund_batches")
    op.drop_table("event_refund_batches")

    event_refund_batch_status_enum.drop(op.get_bind(), checkfirst=True)
