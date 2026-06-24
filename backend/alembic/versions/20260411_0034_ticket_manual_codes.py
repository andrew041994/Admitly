"""Add manual ticket check-in codes

Revision ID: 20260411_0034
Revises: 20260410_0033
Create Date: 2026-04-11 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260411_0034"
down_revision: Union[str, None] = "20260410_0033"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tickets", sa.Column("manual_code", sa.String(length=10), nullable=True))
    op.execute(
        """
        WITH numbered AS (
            SELECT
                id,
                row_number() OVER (PARTITION BY event_id ORDER BY md5(id::text || ':' || ticket_code)) AS rn,
                ((hashtext(event_id::text) % 1000000 + 1000000) % 1000000) AS event_offset
            FROM tickets
            WHERE manual_code IS NULL
        )
        UPDATE tickets
        SET manual_code = 'ADM-' || lpad(((((numbered.rn - 1) * 7919 + numbered.event_offset) % 1000000))::text, 6, '0')
        FROM numbered
        WHERE tickets.id = numbered.id
        """
    )
    op.alter_column("tickets", "manual_code", existing_type=sa.String(length=10), nullable=False)
    op.create_index(op.f("ix_tickets_manual_code"), "tickets", ["manual_code"], unique=False)
    op.create_unique_constraint("uq_tickets_event_manual_code", "tickets", ["event_id", "manual_code"])


def downgrade() -> None:
    op.drop_constraint("uq_tickets_event_manual_code", "tickets", type_="unique")
    op.drop_index(op.f("ix_tickets_manual_code"), table_name="tickets")
    op.drop_column("tickets", "manual_code")
