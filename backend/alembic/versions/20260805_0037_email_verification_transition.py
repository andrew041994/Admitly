"""Add email verification audit and transition fields.

Revision ID: 20260805_0037
Revises: 20260804_0036
Create Date: 2026-08-05 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260805_0037"
down_revision: Union[str, None] = "20260804_0036"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "users",
        sa.Column("email_verification_required_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "email_verification_required_at")
    op.drop_column("users", "email_verified_at")
