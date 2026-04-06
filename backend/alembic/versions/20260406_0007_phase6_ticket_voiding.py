"""Phase 6 ticket voiding audit columns

Revision ID: 20260406_0007
Revises: 20260406_0006
Create Date: 2026-04-06 07:00:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260406_0007"
down_revision: Union[str, None] = "20260406_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tickets", sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tickets", sa.Column("voided_by_user_id", sa.Integer(), nullable=True))
    op.add_column("tickets", sa.Column("void_reason", sa.Text(), nullable=True))
    op.create_foreign_key(
        op.f("fk_tickets_voided_by_user_id_users"),
        "tickets",
        "users",
        ["voided_by_user_id"],
        ["id"],
    )
    op.create_index(op.f("ix_tickets_voided_by_user_id"), "tickets", ["voided_by_user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_tickets_voided_by_user_id"), table_name="tickets")
    op.drop_constraint(op.f("fk_tickets_voided_by_user_id_users"), "tickets", type_="foreignkey")
    op.drop_column("tickets", "void_reason")
    op.drop_column("tickets", "voided_by_user_id")
    op.drop_column("tickets", "voided_at")
