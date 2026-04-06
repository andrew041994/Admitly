"""Phase 3 MMG payment fields on orders

Revision ID: 20260406_0004
Revises: 20260406_0003
Create Date: 2026-04-06 03:30:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260406_0004"
down_revision: Union[str, None] = "20260406_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("payment_method", sa.String(length=64), nullable=True))
    op.add_column("orders", sa.Column("payment_reference", sa.String(length=255), nullable=True))
    op.add_column("orders", sa.Column("payment_checkout_url", sa.String(length=1024), nullable=True))
    op.add_column(
        "orders",
        sa.Column(
            "payment_verification_status",
            sa.String(length=64),
            nullable=False,
            server_default="not_started",
        ),
    )
    op.add_column("orders", sa.Column("payment_submitted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("orders", sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f("ix_orders_payment_reference"), "orders", ["payment_reference"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_orders_payment_reference"), table_name="orders")
    op.drop_column("orders", "paid_at")
    op.drop_column("orders", "payment_submitted_at")
    op.drop_column("orders", "payment_verification_status")
    op.drop_column("orders", "payment_checkout_url")
    op.drop_column("orders", "payment_reference")
    op.drop_column("orders", "payment_method")
