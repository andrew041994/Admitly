"""Harden user phones and ticket transfer lifecycle.

Revision ID: 20260804_0035
Revises: 20260411_0034
Create Date: 2026-08-04 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260804_0035"
down_revision: Union[str, None] = "20260411_0034"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("phone_verified_at", sa.DateTime(timezone=True), nullable=True))

    # Empty and unparseable legacy values are missing identity data, not identifiers.
    # Only deterministic Guyana, NANP, or explicit international forms are migrated.
    op.execute("UPDATE users SET phone = NULL WHERE btrim(coalesce(phone, '')) = ''")
    op.execute(
        """
        UPDATE users
        SET phone = CASE
            WHEN phone LIKE '00%' AND length(regexp_replace(phone, '[^0-9]', '', 'g')) BETWEEN 10 AND 17
                 AND substr(regexp_replace(phone, '[^0-9]', '', 'g'), 3, 1) != '0'
                THEN '+' || substr(regexp_replace(phone, '[^0-9]', '', 'g'), 3)
            WHEN phone LIKE '+%' AND length(regexp_replace(phone, '[^0-9]', '', 'g')) BETWEEN 8 AND 15
                 AND regexp_replace(phone, '[^0-9]', '', 'g') NOT LIKE '0%'
                THEN '+' || regexp_replace(phone, '[^0-9]', '', 'g')
            WHEN length(regexp_replace(phone, '[^0-9]', '', 'g')) = 7
                THEN '+592' || regexp_replace(phone, '[^0-9]', '', 'g')
            WHEN length(regexp_replace(phone, '[^0-9]', '', 'g')) = 10
                 AND regexp_replace(phone, '[^0-9]', '', 'g') LIKE '592%'
                THEN '+' || regexp_replace(phone, '[^0-9]', '', 'g')
            WHEN length(regexp_replace(phone, '[^0-9]', '', 'g')) = 10
                THEN '+1' || regexp_replace(phone, '[^0-9]', '', 'g')
            WHEN length(regexp_replace(phone, '[^0-9]', '', 'g')) = 11
                 AND regexp_replace(phone, '[^0-9]', '', 'g') LIKE '1%'
                THEN '+' || regexp_replace(phone, '[^0-9]', '', 'g')
            ELSE NULL
        END
        WHERE phone IS NOT NULL
        """
    )
    # Duplicate normalized numbers are ambiguous. Preserve every account and require
    # those users to re-enter a unique number instead of guessing which account owns it.
    op.execute(
        """
        UPDATE users
        SET phone = NULL
        WHERE phone IN (
            SELECT phone FROM users WHERE phone IS NOT NULL GROUP BY phone HAVING count(*) > 1
        )
        """
    )
    op.drop_index(op.f("ix_users_phone"), table_name="users")
    op.create_index(op.f("ix_users_phone"), "users", ["phone"], unique=True)

    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE transfer_invite_status ADD VALUE IF NOT EXISTS 'declined'")
        op.execute("ALTER TYPE transfer_invite_status ADD VALUE IF NOT EXISTS 'canceled'")
    op.execute("UPDATE ticket_transfer_invites SET status = 'canceled' WHERE status = 'revoked'")

    op.alter_column("ticket_transfer_invites", "revoked_at", new_column_name="canceled_at")
    op.alter_column("ticket_transfer_invites", "revoked_by_user_id", new_column_name="canceled_by_user_id")
    op.add_column("ticket_transfer_invites", sa.Column("declined_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("ticket_transfer_invites", sa.Column("declined_by_user_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        op.f("fk_ticket_transfer_invites_declined_by_user_id_users"),
        "ticket_transfer_invites",
        "users",
        ["declined_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.drop_index(op.f("ix_ticket_transfer_invites_invite_token"), table_name="ticket_transfer_invites")
    op.drop_constraint(op.f("uq_ticket_transfer_invites_invite_token"), "ticket_transfer_invites", type_="unique")
    op.drop_column("ticket_transfer_invites", "invite_token")
    op.create_index(
        "ix_ticket_transfer_invites_recipient_status",
        "ticket_transfer_invites",
        ["recipient_user_id", "status", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_ticket_transfer_invites_sender_status",
        "ticket_transfer_invites",
        ["sender_user_id", "status", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_ticket_transfer_invites_sender_status", table_name="ticket_transfer_invites")
    op.drop_index("ix_ticket_transfer_invites_recipient_status", table_name="ticket_transfer_invites")
    op.drop_constraint(
        op.f("fk_ticket_transfer_invites_declined_by_user_id_users"),
        "ticket_transfer_invites",
        type_="foreignkey",
    )
    op.drop_column("ticket_transfer_invites", "declined_by_user_id")
    op.drop_column("ticket_transfer_invites", "declined_at")
    op.add_column("ticket_transfer_invites", sa.Column("invite_token", sa.String(length=128), nullable=True))
    op.execute("UPDATE ticket_transfer_invites SET invite_token = 'legacy-' || id::text")
    op.alter_column("ticket_transfer_invites", "invite_token", nullable=False)
    op.create_unique_constraint(op.f("uq_ticket_transfer_invites_invite_token"), "ticket_transfer_invites", ["invite_token"])
    op.create_index(op.f("ix_ticket_transfer_invites_invite_token"), "ticket_transfer_invites", ["invite_token"], unique=True)
    op.execute("UPDATE ticket_transfer_invites SET status = 'expired' WHERE status = 'declined'")
    op.execute("UPDATE ticket_transfer_invites SET status = 'revoked' WHERE status = 'canceled'")
    op.alter_column("ticket_transfer_invites", "canceled_by_user_id", new_column_name="revoked_by_user_id")
    op.alter_column("ticket_transfer_invites", "canceled_at", new_column_name="revoked_at")
    op.drop_index(op.f("ix_users_phone"), table_name="users")
    op.create_index(op.f("ix_users_phone"), "users", ["phone"], unique=False)
    op.drop_column("users", "phone_verified_at")
