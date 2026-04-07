"""Phase 11 event reminder logs

Revision ID: 20260406_0011
Revises: 20260406_0010
Create Date: 2026-04-06 11:00:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260406_0011"
down_revision: Union[str, None] = "20260406_0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

reminder_type_enum = postgresql.ENUM(
    "24_hours_before",
    "3_hours_before",
    "30_minutes_before",
    name="reminder_type",
    create_type=False,
)


def upgrade() -> None:
    reminder_type_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "event_reminder_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "reminder_type",
            reminder_type_enum,
            nullable=False,
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", "user_id", "reminder_type", name="uq_event_reminder_logs_event_user_type"),
    )
    op.create_index(op.f("ix_event_reminder_logs_event_id"), "event_reminder_logs", ["event_id"], unique=False)
    op.create_index(op.f("ix_event_reminder_logs_user_id"), "event_reminder_logs", ["user_id"], unique=False)
    op.create_index(op.f("ix_event_reminder_logs_reminder_type"), "event_reminder_logs", ["reminder_type"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_event_reminder_logs_reminder_type"), table_name="event_reminder_logs")
    op.drop_index(op.f("ix_event_reminder_logs_user_id"), table_name="event_reminder_logs")
    op.drop_index(op.f("ix_event_reminder_logs_event_id"), table_name="event_reminder_logs")
    op.drop_table("event_reminder_logs")
    reminder_type_enum.drop(op.get_bind(), checkfirst=True)
