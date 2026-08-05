"""Add opaque ticket transfer recipient resolutions.

Revision ID: 20260804_0036
Revises: 20260804_0035
Create Date: 2026-08-04 00:30:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260804_0036"
down_revision: Union[str, None] = "20260804_0035"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ticket_transfer_recipient_resolutions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("ticket_id", sa.Integer(), nullable=False),
        sa.Column("sender_user_id", sa.Integer(), nullable=False),
        sa.Column("recipient_user_id", sa.Integer(), nullable=False),
        sa.Column("recipient_email_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sender_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recipient_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ticket_transfer_recipient_resolutions_token_hash"), "ticket_transfer_recipient_resolutions", ["token_hash"], unique=True)
    op.create_index(op.f("ix_ticket_transfer_recipient_resolutions_ticket_id"), "ticket_transfer_recipient_resolutions", ["ticket_id"], unique=False)
    op.create_index(op.f("ix_ticket_transfer_recipient_resolutions_sender_user_id"), "ticket_transfer_recipient_resolutions", ["sender_user_id"], unique=False)
    op.create_index(op.f("ix_ticket_transfer_recipient_resolutions_recipient_user_id"), "ticket_transfer_recipient_resolutions", ["recipient_user_id"], unique=False)
    op.create_index(op.f("ix_ticket_transfer_recipient_resolutions_expires_at"), "ticket_transfer_recipient_resolutions", ["expires_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_ticket_transfer_recipient_resolutions_expires_at"), table_name="ticket_transfer_recipient_resolutions")
    op.drop_index(op.f("ix_ticket_transfer_recipient_resolutions_recipient_user_id"), table_name="ticket_transfer_recipient_resolutions")
    op.drop_index(op.f("ix_ticket_transfer_recipient_resolutions_sender_user_id"), table_name="ticket_transfer_recipient_resolutions")
    op.drop_index(op.f("ix_ticket_transfer_recipient_resolutions_ticket_id"), table_name="ticket_transfer_recipient_resolutions")
    op.drop_index(op.f("ix_ticket_transfer_recipient_resolutions_token_hash"), table_name="ticket_transfer_recipient_resolutions")
    op.drop_table("ticket_transfer_recipient_resolutions")
