"""Phase 8 push token storage

Revision ID: 20260406_0009
Revises: 20260406_0008
Create Date: 2026-04-06 12:00:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260406_0009"
down_revision: Union[str, None] = "20260406_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "push_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token", sa.String(length=512), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_push_tokens")),
        sa.UniqueConstraint("token", name="uq_push_tokens_token"),
    )
    op.create_index(op.f("ix_push_tokens_user_id"), "push_tokens", ["user_id"], unique=False)
    op.create_index(op.f("ix_push_tokens_is_active"), "push_tokens", ["is_active"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_push_tokens_is_active"), table_name="push_tokens")
    op.drop_index(op.f("ix_push_tokens_user_id"), table_name="push_tokens")
    op.drop_table("push_tokens")
