"""Ensure promo_code_redemptions timestamp defaults

Revision ID: 20260410_0033
Revises: 20260410_0032
Create Date: 2026-04-10 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260410_0033"
down_revision: Union[str, None] = "20260410_0032"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "promo_code_redemptions",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )
    op.alter_column(
        "promo_code_redemptions",
        "updated_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )


def downgrade() -> None:
    op.alter_column(
        "promo_code_redemptions",
        "updated_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
        server_default=None,
    )
    op.alter_column(
        "promo_code_redemptions",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
        server_default=None,
    )
