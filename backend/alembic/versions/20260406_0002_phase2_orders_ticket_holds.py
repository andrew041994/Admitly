"""Phase 2 orders and ticket holds

Revision ID: 20260406_0002
Revises: 20260406_0001
Create Date: 2026-04-06 00:30:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260406_0002"
down_revision: Union[str, None] = "20260406_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

order_status = sa.Enum("pending", "completed", "cancelled", "expired", name="order_status")


def upgrade() -> None:
    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("status", order_status, nullable=False, server_default="pending"),
        sa.Column("total_amount", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="GYD"),
        sa.Column("payment_provider", sa.String(length=64), nullable=True),
        sa.Column("payment_intent_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], name=op.f("fk_orders_event_id_events")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_orders_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_orders")),
    )
    op.create_index(op.f("ix_orders_user_id"), "orders", ["user_id"], unique=False)
    op.create_index(op.f("ix_orders_event_id"), "orders", ["event_id"], unique=False)

    op.create_table(
        "order_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("ticket_tier_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("quantity > 0", name=op.f("ck_order_items_order_items_quantity_positive")),
        sa.ForeignKeyConstraint(
            ["order_id"], ["orders.id"], name=op.f("fk_order_items_order_id_orders"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["ticket_tier_id"], ["ticket_tiers.id"], name=op.f("fk_order_items_ticket_tier_id_ticket_tiers")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_order_items")),
    )
    op.create_index(op.f("ix_order_items_order_id"), "order_items", ["order_id"], unique=False)
    op.create_index(op.f("ix_order_items_ticket_tier_id"), "order_items", ["ticket_tier_id"], unique=False)

    op.create_table(
        "ticket_holds",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("ticket_tier_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("session_id", sa.String(length=255), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("quantity > 0", name=op.f("ck_ticket_holds_ticket_holds_quantity_positive")),
        sa.ForeignKeyConstraint(
            ["event_id"], ["events.id"], name=op.f("fk_ticket_holds_event_id_events"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["ticket_tier_id"], ["ticket_tiers.id"], name=op.f("fk_ticket_holds_ticket_tier_id_ticket_tiers")
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_ticket_holds_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ticket_holds")),
    )
    op.create_index(
        "ix_ticket_holds_event_id_ticket_tier_id",
        "ticket_holds",
        ["event_id", "ticket_tier_id"],
        unique=False,
    )
    op.create_index(op.f("ix_ticket_holds_expires_at"), "ticket_holds", ["expires_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_ticket_holds_expires_at"), table_name="ticket_holds")
    op.drop_index("ix_ticket_holds_event_id_ticket_tier_id", table_name="ticket_holds")
    op.drop_table("ticket_holds")

    op.drop_index(op.f("ix_order_items_ticket_tier_id"), table_name="order_items")
    op.drop_index(op.f("ix_order_items_order_id"), table_name="order_items")
    op.drop_table("order_items")

    op.drop_index(op.f("ix_orders_event_id"), table_name="orders")
    op.drop_index(op.f("ix_orders_user_id"), table_name="orders")
    op.drop_table("orders")

    bind = op.get_bind()
    order_status.drop(bind, checkfirst=True)
