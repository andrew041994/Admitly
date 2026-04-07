"""Phase 13 promo codes, discounts, and comps

Revision ID: 20260407_0013
Revises: 20260407_0012
Create Date: 2026-04-07 14:00:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260407_0013"
down_revision: Union[str, None] = "20260407_0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

promo_discount_type_enum = sa.Enum("percentage", "fixed_amount", name="promo_code_discount_type")
pricing_source_enum = sa.Enum("standard", "promo_code", "comp", name="pricing_source")


def upgrade() -> None:
    bind = op.get_bind()
    promo_discount_type_enum.create(bind, checkfirst=True)
    pricing_source_enum.create(bind, checkfirst=True)

    op.create_table(
        "promo_codes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("code_normalized", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("discount_type", promo_discount_type_enum, nullable=False),
        sa.Column("discount_value", sa.Numeric(10, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("max_total_redemptions", sa.Integer(), nullable=True),
        sa.Column("max_redemptions_per_user", sa.Integer(), nullable=True),
        sa.Column("min_order_amount", sa.Numeric(10, 2), nullable=True),
        sa.Column("applies_to_all_tiers", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", "code_normalized", name="uq_promo_codes_event_id_code_normalized"),
    )
    op.create_index(op.f("ix_promo_codes_event_id"), "promo_codes", ["event_id"], unique=False)

    op.create_table(
        "promo_code_ticket_tiers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("promo_code_id", sa.Integer(), nullable=False),
        sa.Column("ticket_tier_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["promo_code_id"], ["promo_codes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ticket_tier_id"], ["ticket_tiers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("promo_code_id", "ticket_tier_id", name="uq_promo_code_ticket_tiers_pair"),
    )
    op.create_index(op.f("ix_promo_code_ticket_tiers_promo_code_id"), "promo_code_ticket_tiers", ["promo_code_id"], unique=False)
    op.create_index(op.f("ix_promo_code_ticket_tiers_ticket_tier_id"), "promo_code_ticket_tiers", ["ticket_tier_id"], unique=False)

    op.add_column("orders", sa.Column("subtotal_amount", sa.Numeric(10, 2), nullable=False, server_default="0.00"))
    op.add_column("orders", sa.Column("discount_amount", sa.Numeric(10, 2), nullable=False, server_default="0.00"))
    op.add_column("orders", sa.Column("promo_code_id", sa.Integer(), nullable=True))
    op.add_column("orders", sa.Column("promo_code_text", sa.String(length=64), nullable=True))
    op.add_column("orders", sa.Column("discount_type", sa.String(length=32), nullable=True))
    op.add_column("orders", sa.Column("discount_value_snapshot", sa.Numeric(10, 2), nullable=True))
    op.add_column("orders", sa.Column("pricing_source", pricing_source_enum, nullable=False, server_default="standard"))
    op.add_column("orders", sa.Column("comp_reason", sa.Text(), nullable=True))
    op.add_column("orders", sa.Column("is_comp", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index(op.f("ix_orders_promo_code_id"), "orders", ["promo_code_id"], unique=False)
    op.create_foreign_key("fk_orders_promo_code_id_promo_codes", "orders", "promo_codes", ["promo_code_id"], ["id"])

    op.execute("UPDATE orders SET subtotal_amount = total_amount WHERE subtotal_amount = 0")

    op.alter_column("orders", "subtotal_amount", server_default=None)
    op.alter_column("orders", "discount_amount", server_default=None)
    op.alter_column("orders", "pricing_source", server_default=None)
    op.alter_column("orders", "is_comp", server_default=None)

    op.create_table(
        "promo_code_redemptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("promo_code_id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("discount_amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["promo_code_id"], ["promo_codes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id", name="uq_promo_code_redemptions_order_id"),
    )
    op.create_index(op.f("ix_promo_code_redemptions_order_id"), "promo_code_redemptions", ["order_id"], unique=False)
    op.create_index(op.f("ix_promo_code_redemptions_promo_code_id"), "promo_code_redemptions", ["promo_code_id"], unique=False)
    op.create_index(op.f("ix_promo_code_redemptions_user_id"), "promo_code_redemptions", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_promo_code_redemptions_user_id"), table_name="promo_code_redemptions")
    op.drop_index(op.f("ix_promo_code_redemptions_promo_code_id"), table_name="promo_code_redemptions")
    op.drop_index(op.f("ix_promo_code_redemptions_order_id"), table_name="promo_code_redemptions")
    op.drop_table("promo_code_redemptions")

    op.drop_constraint("fk_orders_promo_code_id_promo_codes", "orders", type_="foreignkey")
    op.drop_index(op.f("ix_orders_promo_code_id"), table_name="orders")
    op.drop_column("orders", "is_comp")
    op.drop_column("orders", "comp_reason")
    op.drop_column("orders", "pricing_source")
    op.drop_column("orders", "discount_value_snapshot")
    op.drop_column("orders", "discount_type")
    op.drop_column("orders", "promo_code_text")
    op.drop_column("orders", "promo_code_id")
    op.drop_column("orders", "discount_amount")
    op.drop_column("orders", "subtotal_amount")

    op.drop_index(op.f("ix_promo_code_ticket_tiers_ticket_tier_id"), table_name="promo_code_ticket_tiers")
    op.drop_index(op.f("ix_promo_code_ticket_tiers_promo_code_id"), table_name="promo_code_ticket_tiers")
    op.drop_table("promo_code_ticket_tiers")

    op.drop_index(op.f("ix_promo_codes_event_id"), table_name="promo_codes")
    op.drop_table("promo_codes")

    pricing_source_enum.drop(op.get_bind(), checkfirst=True)
    promo_discount_type_enum.drop(op.get_bind(), checkfirst=True)
