"""Phase 12 MMG reconciliation and payout bookkeeping

Revision ID: 20260407_0012
Revises: 20260406_0011
Create Date: 2026-04-07 10:00:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260407_0012"
down_revision: Union[str, None] = "20260406_0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


reconciliation_status_enum = postgresql.ENUM(
    "unreconciled",
    "reconciled",
    "disputed",
    "excluded",
    name="reconciliation_status",
    create_type=False,
)
payout_status_enum = postgresql.ENUM(
    "not_ready",
    "eligible",
    "included",
    "paid",
    "held",
    name="payout_status",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    reconciliation_status_enum.create(bind, checkfirst=True)
    payout_status_enum.create(bind, checkfirst=True)

    op.add_column(
        "orders",
        sa.Column(
            "reconciliation_status",
            reconciliation_status_enum,
            nullable=False,
            server_default="unreconciled",
        ),
    )
    op.add_column("orders", sa.Column("reconciled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("orders", sa.Column("reconciled_by_user_id", sa.Integer(), nullable=True))
    op.add_column("orders", sa.Column("reconciliation_note", sa.Text(), nullable=True))

    op.add_column(
        "orders",
        sa.Column(
            "payout_status",
            payout_status_enum,
            nullable=False,
            server_default="not_ready",
        ),
    )
    op.add_column("orders", sa.Column("payout_batch_id", sa.String(length=64), nullable=True))
    op.add_column("orders", sa.Column("payout_included_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("orders", sa.Column("payout_paid_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("orders", sa.Column("payout_note", sa.Text(), nullable=True))

    op.create_index(op.f("ix_orders_reconciled_by_user_id"), "orders", ["reconciled_by_user_id"], unique=False)
    op.create_foreign_key(
        "fk_orders_reconciled_by_user_id_users",
        "orders",
        "users",
        ["reconciled_by_user_id"],
        ["id"],
    )
    op.create_index(op.f("ix_orders_payout_batch_id"), "orders", ["payout_batch_id"], unique=False)

    op.alter_column("orders", "reconciliation_status", server_default=None)
    op.alter_column("orders", "payout_status", server_default=None)


def downgrade() -> None:
    op.drop_index(op.f("ix_orders_payout_batch_id"), table_name="orders")
    op.drop_constraint("fk_orders_reconciled_by_user_id_users", "orders", type_="foreignkey")
    op.drop_index(op.f("ix_orders_reconciled_by_user_id"), table_name="orders")

    op.drop_column("orders", "payout_note")
    op.drop_column("orders", "payout_paid_at")
    op.drop_column("orders", "payout_included_at")
    op.drop_column("orders", "payout_batch_id")
    op.drop_column("orders", "payout_status")

    op.drop_column("orders", "reconciliation_note")
    op.drop_column("orders", "reconciled_by_user_id")
    op.drop_column("orders", "reconciled_at")
    op.drop_column("orders", "reconciliation_status")

    payout_status_enum.drop(op.get_bind(), checkfirst=True)
    reconciliation_status_enum.drop(op.get_bind(), checkfirst=True)
