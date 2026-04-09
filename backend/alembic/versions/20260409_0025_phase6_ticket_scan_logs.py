"""Phase 6 ticket scanning and scan logs

Revision ID: 20260409_0025
Revises: 20260408_0024
Create Date: 2026-04-09 10:00:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260409_0025"
down_revision: Union[str, None] = "20260408_0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


check_in_status_enum = sa.Enum("not_checked_in", "checked_in", name="check_in_status")
ticket_scan_status_enum = sa.Enum("success", "already_used", "invalid", "wrong_event", name="ticket_scan_status")


def upgrade() -> None:
    bind = op.get_bind()
    check_in_status_enum.create(bind, checkfirst=True)
    ticket_scan_status_enum.create(bind, checkfirst=True)

    op.add_column(
        "tickets",
        sa.Column(
            "check_in_status",
            check_in_status_enum,
            nullable=False,
            server_default="not_checked_in",
        ),
    )
    op.create_index(op.f("ix_tickets_check_in_status"), "tickets", ["check_in_status"], unique=False)

    op.execute(
        """
        UPDATE tickets
        SET check_in_status = CASE
            WHEN status = 'checked_in' THEN 'checked_in'
            ELSE 'not_checked_in'
        END
        """
    )

    op.create_table(
        "ticket_scan_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ticket_id", sa.Integer(), nullable=True),
        sa.Column("scanned_by", sa.Integer(), nullable=True),
        sa.Column("scanned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", ticket_scan_status_enum, nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["scanned_by"], ["users.id"], name=op.f("fk_ticket_scan_logs_scanned_by_users")),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"], name=op.f("fk_ticket_scan_logs_ticket_id_tickets")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ticket_scan_logs")),
    )
    op.create_index(op.f("ix_ticket_scan_logs_scanned_at"), "ticket_scan_logs", ["scanned_at"], unique=False)
    op.create_index(op.f("ix_ticket_scan_logs_scanned_by"), "ticket_scan_logs", ["scanned_by"], unique=False)
    op.create_index(op.f("ix_ticket_scan_logs_status"), "ticket_scan_logs", ["status"], unique=False)
    op.create_index(op.f("ix_ticket_scan_logs_ticket_id"), "ticket_scan_logs", ["ticket_id"], unique=False)

    op.alter_column("tickets", "check_in_status", server_default=None)


def downgrade() -> None:
    op.drop_index(op.f("ix_ticket_scan_logs_ticket_id"), table_name="ticket_scan_logs")
    op.drop_index(op.f("ix_ticket_scan_logs_status"), table_name="ticket_scan_logs")
    op.drop_index(op.f("ix_ticket_scan_logs_scanned_by"), table_name="ticket_scan_logs")
    op.drop_index(op.f("ix_ticket_scan_logs_scanned_at"), table_name="ticket_scan_logs")
    op.drop_table("ticket_scan_logs")

    op.drop_index(op.f("ix_tickets_check_in_status"), table_name="tickets")
    op.drop_column("tickets", "check_in_status")

    bind = op.get_bind()
    ticket_scan_status_enum.drop(bind, checkfirst=True)
    check_in_status_enum.drop(bind, checkfirst=True)
