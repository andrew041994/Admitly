"""Phase 24 check-in attempt audit trail

Revision ID: 20260407_0019
Revises: 20260407_0018
Create Date: 2026-04-07 18:10:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260407_0019"
down_revision: Union[str, None] = "20260407_0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ticket_check_in_attempts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ticket_id", sa.Integer(), nullable=True),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result_code", sa.String(length=64), nullable=False),
        sa.Column("reason_code", sa.String(length=64), nullable=True),
        sa.Column("reason_message", sa.Text(), nullable=True),
        sa.Column("method", sa.String(length=32), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], name=op.f("fk_ticket_check_in_attempts_actor_user_id_users")),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], name=op.f("fk_ticket_check_in_attempts_event_id_events"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"], name=op.f("fk_ticket_check_in_attempts_ticket_id_tickets")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ticket_check_in_attempts")),
    )
    op.create_index(op.f("ix_ticket_check_in_attempts_actor_user_id"), "ticket_check_in_attempts", ["actor_user_id"], unique=False)
    op.create_index(op.f("ix_ticket_check_in_attempts_attempted_at"), "ticket_check_in_attempts", ["attempted_at"], unique=False)
    op.create_index(op.f("ix_ticket_check_in_attempts_event_id"), "ticket_check_in_attempts", ["event_id"], unique=False)
    op.create_index(op.f("ix_ticket_check_in_attempts_reason_code"), "ticket_check_in_attempts", ["reason_code"], unique=False)
    op.create_index(op.f("ix_ticket_check_in_attempts_result_code"), "ticket_check_in_attempts", ["result_code"], unique=False)
    op.create_index(op.f("ix_ticket_check_in_attempts_ticket_id"), "ticket_check_in_attempts", ["ticket_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_ticket_check_in_attempts_ticket_id"), table_name="ticket_check_in_attempts")
    op.drop_index(op.f("ix_ticket_check_in_attempts_result_code"), table_name="ticket_check_in_attempts")
    op.drop_index(op.f("ix_ticket_check_in_attempts_reason_code"), table_name="ticket_check_in_attempts")
    op.drop_index(op.f("ix_ticket_check_in_attempts_event_id"), table_name="ticket_check_in_attempts")
    op.drop_index(op.f("ix_ticket_check_in_attempts_attempted_at"), table_name="ticket_check_in_attempts")
    op.drop_index(op.f("ix_ticket_check_in_attempts_actor_user_id"), table_name="ticket_check_in_attempts")
    op.drop_table("ticket_check_in_attempts")
