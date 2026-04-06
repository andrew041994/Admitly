"""Phase 5 ticket ownership transfer columns

Revision ID: 20260406_0006
Revises: 20260406_0005
Create Date: 2026-04-06 06:00:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260406_0006"
down_revision: Union[str, None] = "20260406_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tickets", sa.Column("purchaser_user_id", sa.Integer(), nullable=True))
    op.add_column("tickets", sa.Column("owner_user_id", sa.Integer(), nullable=True))
    op.add_column("tickets", sa.Column("transferred_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tickets", sa.Column("transfer_count", sa.Integer(), nullable=False, server_default="0"))

    op.execute("UPDATE tickets SET purchaser_user_id = user_id, owner_user_id = user_id")

    op.alter_column("tickets", "purchaser_user_id", nullable=False)
    op.alter_column("tickets", "owner_user_id", nullable=False)

    op.create_foreign_key(
        op.f("fk_tickets_purchaser_user_id_users"),
        "tickets",
        "users",
        ["purchaser_user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        op.f("fk_tickets_owner_user_id_users"),
        "tickets",
        "users",
        ["owner_user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(op.f("ix_tickets_purchaser_user_id"), "tickets", ["purchaser_user_id"], unique=False)
    op.create_index(op.f("ix_tickets_owner_user_id"), "tickets", ["owner_user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_tickets_owner_user_id"), table_name="tickets")
    op.drop_index(op.f("ix_tickets_purchaser_user_id"), table_name="tickets")
    op.drop_constraint(op.f("fk_tickets_owner_user_id_users"), "tickets", type_="foreignkey")
    op.drop_constraint(op.f("fk_tickets_purchaser_user_id_users"), "tickets", type_="foreignkey")
    op.drop_column("tickets", "transfer_count")
    op.drop_column("tickets", "transferred_at")
    op.drop_column("tickets", "owner_user_id")
    op.drop_column("tickets", "purchaser_user_id")
