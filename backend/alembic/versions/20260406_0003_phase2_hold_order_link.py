"""Phase 2 hold to order linkage

Revision ID: 20260406_0003
Revises: 20260406_0002
Create Date: 2026-04-06 01:15:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260406_0003"
down_revision: Union[str, None] = "20260406_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("ticket_holds", sa.Column("order_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        op.f("fk_ticket_holds_order_id_orders"),
        "ticket_holds",
        "orders",
        ["order_id"],
        ["id"],
    )
    op.create_index(op.f("ix_ticket_holds_order_id"), "ticket_holds", ["order_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_ticket_holds_order_id"), table_name="ticket_holds")
    op.drop_constraint(op.f("fk_ticket_holds_order_id_orders"), "ticket_holds", type_="foreignkey")
    op.drop_column("ticket_holds", "order_id")
