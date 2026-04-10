"""Fix missing timestamp defaults for remaining tables

Revision ID: 20260410_0032
Revises: 20260410_0031
Create Date: 2026-04-10 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260410_0032"
down_revision: Union[str, None] = "20260410_0031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table_name in (
        "webhook_deliveries",
        "organizer_balance_adjustments",
        "promo_code_ticket_tiers",
    ):
        op.alter_column(
            table_name,
            "created_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        )
        op.alter_column(
            table_name,
            "updated_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        )


def downgrade() -> None:
    for table_name in (
        "promo_code_ticket_tiers",
        "organizer_balance_adjustments",
        "webhook_deliveries",
    ):
        op.alter_column(
            table_name,
            "updated_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
            server_default=None,
        )
        op.alter_column(
            table_name,
            "created_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
            server_default=None,
        )
