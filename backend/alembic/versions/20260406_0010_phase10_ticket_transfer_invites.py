"""Phase 10 ticket transfer invites

Revision ID: 20260406_0010
Revises: 20260406_0009
Create Date: 2026-04-06 10:00:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260406_0010"
down_revision: Union[str, None] = "20260406_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ticket_transfer_invites",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ticket_id", sa.Integer(), nullable=False),
        sa.Column("sender_user_id", sa.Integer(), nullable=False),
        sa.Column("recipient_user_id", sa.Integer(), nullable=True),
        sa.Column("recipient_email", sa.String(length=255), nullable=True),
        sa.Column("recipient_phone", sa.String(length=32), nullable=True),
        sa.Column("invite_token", sa.String(length=128), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "accepted", "revoked", "expired", name="transfer_invite_status"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_by_user_id", sa.Integer(), nullable=True),
        sa.Column("revoked_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["accepted_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["recipient_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["revoked_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["sender_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("invite_token"),
    )
    op.create_index(op.f("ix_ticket_transfer_invites_ticket_id"), "ticket_transfer_invites", ["ticket_id"], unique=False)
    op.create_index(op.f("ix_ticket_transfer_invites_sender_user_id"), "ticket_transfer_invites", ["sender_user_id"], unique=False)
    op.create_index(op.f("ix_ticket_transfer_invites_recipient_user_id"), "ticket_transfer_invites", ["recipient_user_id"], unique=False)
    op.create_index(op.f("ix_ticket_transfer_invites_status"), "ticket_transfer_invites", ["status"], unique=False)
    op.create_index(op.f("ix_ticket_transfer_invites_invite_token"), "ticket_transfer_invites", ["invite_token"], unique=True)
    op.create_index(
        "uq_ticket_transfer_invites_pending_ticket_id",
        "ticket_transfer_invites",
        ["ticket_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
        sqlite_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index("uq_ticket_transfer_invites_pending_ticket_id", table_name="ticket_transfer_invites")
    op.drop_index(op.f("ix_ticket_transfer_invites_invite_token"), table_name="ticket_transfer_invites")
    op.drop_index(op.f("ix_ticket_transfer_invites_status"), table_name="ticket_transfer_invites")
    op.drop_index(op.f("ix_ticket_transfer_invites_recipient_user_id"), table_name="ticket_transfer_invites")
    op.drop_index(op.f("ix_ticket_transfer_invites_sender_user_id"), table_name="ticket_transfer_invites")
    op.drop_index(op.f("ix_ticket_transfer_invites_ticket_id"), table_name="ticket_transfer_invites")
    op.drop_table("ticket_transfer_invites")
    sa.Enum("pending", "accepted", "revoked", "expired", name="transfer_invite_status").drop(
        op.get_bind(), checkfirst=True
    )
