"""Phase 7 order refunds/cancellations and event cancellation audit fields

Revision ID: 20260406_0008
Revises: 20260406_0007
Create Date: 2026-04-06 08:00:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260406_0008"
down_revision: Union[str, None] = "20260406_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


REFUND_STATUS_VALUES = ("not_refunded", "pending", "refunded", "failed")


def upgrade() -> None:
    op.add_column("orders", sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("orders", sa.Column("cancelled_by_user_id", sa.Integer(), nullable=True))
    op.add_column("orders", sa.Column("cancel_reason", sa.Text(), nullable=True))
    op.add_column("orders", sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("orders", sa.Column("refunded_by_user_id", sa.Integer(), nullable=True))
    op.add_column("orders", sa.Column("refund_reason", sa.Text(), nullable=True))
    op.add_column(
        "orders",
        sa.Column(
            "refund_status",
            sa.String(length=32),
            nullable=False,
            server_default=REFUND_STATUS_VALUES[0],
        ),
    )

    op.create_foreign_key(
        op.f("fk_orders_cancelled_by_user_id_users"),
        "orders",
        "users",
        ["cancelled_by_user_id"],
        ["id"],
    )
    op.create_foreign_key(
        op.f("fk_orders_refunded_by_user_id_users"),
        "orders",
        "users",
        ["refunded_by_user_id"],
        ["id"],
    )
    op.create_index(op.f("ix_orders_cancelled_by_user_id"), "orders", ["cancelled_by_user_id"], unique=False)
    op.create_index(op.f("ix_orders_refunded_by_user_id"), "orders", ["refunded_by_user_id"], unique=False)

    op.create_check_constraint(
        "ck_orders_refund_status_values",
        "orders",
        "refund_status IN ('not_refunded', 'pending', 'refunded', 'failed')",
    )

    op.add_column("events", sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("events", sa.Column("cancelled_by_user_id", sa.Integer(), nullable=True))
    op.add_column("events", sa.Column("cancellation_reason", sa.Text(), nullable=True))
    op.create_foreign_key(
        op.f("fk_events_cancelled_by_user_id_users"),
        "events",
        "users",
        ["cancelled_by_user_id"],
        ["id"],
    )
    op.create_index(op.f("ix_events_cancelled_by_user_id"), "events", ["cancelled_by_user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_events_cancelled_by_user_id"), table_name="events")
    op.drop_constraint(op.f("fk_events_cancelled_by_user_id_users"), "events", type_="foreignkey")
    op.drop_column("events", "cancellation_reason")
    op.drop_column("events", "cancelled_by_user_id")
    op.drop_column("events", "cancelled_at")

    op.drop_constraint("ck_orders_refund_status_values", "orders", type_="check")
    op.drop_index(op.f("ix_orders_refunded_by_user_id"), table_name="orders")
    op.drop_index(op.f("ix_orders_cancelled_by_user_id"), table_name="orders")
    op.drop_constraint(op.f("fk_orders_refunded_by_user_id_users"), "orders", type_="foreignkey")
    op.drop_constraint(op.f("fk_orders_cancelled_by_user_id_users"), "orders", type_="foreignkey")
    op.drop_column("orders", "refund_status")
    op.drop_column("orders", "refund_reason")
    op.drop_column("orders", "refunded_by_user_id")
    op.drop_column("orders", "refunded_at")
    op.drop_column("orders", "cancel_reason")
    op.drop_column("orders", "cancelled_by_user_id")
    op.drop_column("orders", "cancelled_at")
