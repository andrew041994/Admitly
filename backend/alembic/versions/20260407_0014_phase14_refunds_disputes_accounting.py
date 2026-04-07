"""Phase 14 refunds, disputes, and refund accounting

Revision ID: 20260407_0014
Revises: 20260407_0013
Create Date: 2026-04-07 16:30:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260407_0014"
down_revision: Union[str, None] = "20260407_0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

refund_status_enum = postgresql.ENUM("pending", "approved", "rejected", "processed", name="refund_status_enum", create_type=False)
refund_reason_enum = postgresql.ENUM(
    "event_canceled", "duplicate_purchase", "fraud", "user_request", "other", name="refund_reason", create_type=False
)
dispute_status_enum = postgresql.ENUM("open", "under_review", "resolved", "rejected", name="dispute_status", create_type=False)
financial_entry_type_enum = postgresql.ENUM("refund_reversal", name="financial_entry_type", create_type=False)
balance_adjustment_type_enum = postgresql.ENUM("refund_offset", name="balance_adjustment_type", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    refund_status_enum.create(bind, checkfirst=True)
    refund_reason_enum.create(bind, checkfirst=True)
    dispute_status_enum.create(bind, checkfirst=True)
    financial_entry_type_enum.create(bind, checkfirst=True)
    balance_adjustment_type_enum.create(bind, checkfirst=True)

    op.create_table(
        "refunds",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("approved_by_user_id", sa.Integer(), nullable=True),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("status", refund_status_enum, nullable=False),
        sa.Column("reason", refund_reason_enum, nullable=False),
        sa.Column("admin_notes", sa.Text(), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_refunds_order_id"), "refunds", ["order_id"], unique=False)
    op.create_index(op.f("ix_refunds_user_id"), "refunds", ["user_id"], unique=False)
    op.create_index(op.f("ix_refunds_status"), "refunds", ["status"], unique=False)
    op.create_index(op.f("ix_refunds_approved_by_user_id"), "refunds", ["approved_by_user_id"], unique=False)
    op.create_index(op.f("ix_refunds_created_at"), "refunds", ["created_at"], unique=False)

    op.create_table(
        "disputes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("resolved_by_user_id", sa.Integer(), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", dispute_status_enum, nullable=False),
        sa.Column("admin_notes", sa.Text(), nullable=True),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.ForeignKeyConstraint(["resolved_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_disputes_order_id"), "disputes", ["order_id"], unique=False)
    op.create_index(op.f("ix_disputes_user_id"), "disputes", ["user_id"], unique=False)
    op.create_index(op.f("ix_disputes_status"), "disputes", ["status"], unique=False)
    op.create_index(op.f("ix_disputes_resolved_by_user_id"), "disputes", ["resolved_by_user_id"], unique=False)
    op.create_index(op.f("ix_disputes_created_at"), "disputes", ["created_at"], unique=False)

    op.create_table(
        "financial_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("refund_id", sa.Integer(), nullable=False),
        sa.Column("organizer_id", sa.Integer(), nullable=True),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("entry_type", financial_entry_type_enum, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.ForeignKeyConstraint(["organizer_id"], ["organizer_profiles.id"]),
        sa.ForeignKeyConstraint(["refund_id"], ["refunds.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_financial_entries_order_id"), "financial_entries", ["order_id"], unique=False)
    op.create_index(op.f("ix_financial_entries_refund_id"), "financial_entries", ["refund_id"], unique=False)
    op.create_index(op.f("ix_financial_entries_organizer_id"), "financial_entries", ["organizer_id"], unique=False)
    op.create_index(op.f("ix_financial_entries_entry_type"), "financial_entries", ["entry_type"], unique=False)

    op.create_table(
        "organizer_balance_adjustments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organizer_id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("refund_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("adjustment_type", balance_adjustment_type_enum, nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.ForeignKeyConstraint(["organizer_id"], ["organizer_profiles.id"]),
        sa.ForeignKeyConstraint(["refund_id"], ["refunds.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_organizer_balance_adjustments_organizer_id"), "organizer_balance_adjustments", ["organizer_id"], unique=False)
    op.create_index(op.f("ix_organizer_balance_adjustments_order_id"), "organizer_balance_adjustments", ["order_id"], unique=False)
    op.create_index(op.f("ix_organizer_balance_adjustments_refund_id"), "organizer_balance_adjustments", ["refund_id"], unique=False)
    op.create_index(op.f("ix_organizer_balance_adjustments_adjustment_type"), "organizer_balance_adjustments", ["adjustment_type"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_organizer_balance_adjustments_adjustment_type"), table_name="organizer_balance_adjustments")
    op.drop_index(op.f("ix_organizer_balance_adjustments_refund_id"), table_name="organizer_balance_adjustments")
    op.drop_index(op.f("ix_organizer_balance_adjustments_order_id"), table_name="organizer_balance_adjustments")
    op.drop_index(op.f("ix_organizer_balance_adjustments_organizer_id"), table_name="organizer_balance_adjustments")
    op.drop_table("organizer_balance_adjustments")

    op.drop_index(op.f("ix_financial_entries_entry_type"), table_name="financial_entries")
    op.drop_index(op.f("ix_financial_entries_organizer_id"), table_name="financial_entries")
    op.drop_index(op.f("ix_financial_entries_refund_id"), table_name="financial_entries")
    op.drop_index(op.f("ix_financial_entries_order_id"), table_name="financial_entries")
    op.drop_table("financial_entries")

    op.drop_index(op.f("ix_disputes_created_at"), table_name="disputes")
    op.drop_index(op.f("ix_disputes_resolved_by_user_id"), table_name="disputes")
    op.drop_index(op.f("ix_disputes_status"), table_name="disputes")
    op.drop_index(op.f("ix_disputes_user_id"), table_name="disputes")
    op.drop_index(op.f("ix_disputes_order_id"), table_name="disputes")
    op.drop_table("disputes")

    op.drop_index(op.f("ix_refunds_created_at"), table_name="refunds")
    op.drop_index(op.f("ix_refunds_approved_by_user_id"), table_name="refunds")
    op.drop_index(op.f("ix_refunds_status"), table_name="refunds")
    op.drop_index(op.f("ix_refunds_user_id"), table_name="refunds")
    op.drop_index(op.f("ix_refunds_order_id"), table_name="refunds")
    op.drop_table("refunds")

    balance_adjustment_type_enum.drop(op.get_bind(), checkfirst=True)
    financial_entry_type_enum.drop(op.get_bind(), checkfirst=True)
    dispute_status_enum.drop(op.get_bind(), checkfirst=True)
    refund_reason_enum.drop(op.get_bind(), checkfirst=True)
    refund_status_enum.drop(op.get_bind(), checkfirst=True)
