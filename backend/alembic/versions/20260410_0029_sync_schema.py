"""sync schema

Revision ID: 20260410_0029
Revises: 20260410_0028
Create Date: 2026-04-10 00:10:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260410_0029"
down_revision = "20260410_0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "order_items",
        sa.Column("currency", sa.String(), nullable=False, server_default="GYD"),
    )

    op.alter_column("disputes", "created_at", existing_type=sa.DateTime(timezone=True), server_default=sa.text("now()"))
    op.alter_column("promo_codes", "created_at", existing_type=sa.DateTime(timezone=True), server_default=sa.text("now()"))
    op.alter_column("integration_api_keys", "created_at", existing_type=sa.DateTime(timezone=True), server_default=sa.text("now()"))

    # Keep application-level default only after backfilling existing deployments.
    op.alter_column("order_items", "currency", server_default=None)


def downgrade() -> None:
    op.alter_column("integration_api_keys", "created_at", existing_type=sa.DateTime(timezone=True), server_default=None)
    op.alter_column("promo_codes", "created_at", existing_type=sa.DateTime(timezone=True), server_default=None)
    op.alter_column("disputes", "created_at", existing_type=sa.DateTime(timezone=True), server_default=None)
    op.drop_column("order_items", "currency")
