"""Harden payment callback audit and provider references.

Revision ID: 20260811_0039
Revises: 20260805_0038
"""

from alembic import op
import sqlalchemy as sa


revision = "20260811_0039"
down_revision = "20260805_0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "payment_attempts",
        sa.Column(
            "authenticity_status",
            sa.String(length=64),
            nullable=False,
            server_default="not_applicable",
        ),
    )
    op.create_unique_constraint(
        "uq_orders_payment_provider_reference",
        "orders",
        ["payment_provider", "payment_reference"],
    )
    op.add_column("refunds", sa.Column("payment_provider", sa.String(length=64), nullable=True))
    op.add_column("refunds", sa.Column("provider_refund_reference", sa.String(length=255), nullable=True))
    op.add_column(
        "refunds",
        sa.Column("provider_status", sa.String(length=64), nullable=False, server_default="not_submitted"),
    )
    op.add_column("refunds", sa.Column("provider_submitted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("refunds", sa.Column("provider_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(
        op.f("ix_refunds_provider_refund_reference"),
        "refunds",
        ["provider_refund_reference"],
        unique=False,
    )
    op.create_unique_constraint(
        "uq_refunds_provider_reference",
        "refunds",
        ["payment_provider", "provider_refund_reference"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_refunds_provider_reference", "refunds", type_="unique")
    op.drop_index(op.f("ix_refunds_provider_refund_reference"), table_name="refunds")
    op.drop_column("refunds", "provider_verified_at")
    op.drop_column("refunds", "provider_submitted_at")
    op.drop_column("refunds", "provider_status")
    op.drop_column("refunds", "provider_refund_reference")
    op.drop_column("refunds", "payment_provider")
    op.drop_constraint(
        "uq_orders_payment_provider_reference",
        "orders",
        type_="unique",
    )
    op.drop_column("payment_attempts", "authenticity_status")
