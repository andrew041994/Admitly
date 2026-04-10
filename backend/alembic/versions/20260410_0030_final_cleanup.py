"""final cleanup

Revision ID: 20260410_0030
Revises: 20260410_0029
Create Date: 2026-04-10 00:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260410_0030"
down_revision = "20260410_0029"
branch_labels = None
depends_on = None


def _set_timestamp_defaults_and_not_null(table_name: str) -> None:
    op.execute(sa.text(f"UPDATE {table_name} SET created_at = now() WHERE created_at IS NULL"))
    op.execute(sa.text(f"UPDATE {table_name} SET updated_at = now() WHERE updated_at IS NULL"))
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


def upgrade() -> None:
    for table_name in (
        "disputes",
        "refunds",
        "promo_codes",
        "integration_api_keys",
        "event_refund_batches",
    ):
        _set_timestamp_defaults_and_not_null(table_name)


def downgrade() -> None:
    for table_name in (
        "event_refund_batches",
        "integration_api_keys",
        "promo_codes",
        "refunds",
        "disputes",
    ):
        op.alter_column(
            table_name,
            "updated_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=True,
            server_default=None,
        )
        op.alter_column(
            table_name,
            "created_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=True,
            server_default=None,
        )
