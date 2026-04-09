"""Phase 10 recipient name on transfer invites

Revision ID: 20260409_0027
Revises: 20260409_0026
Create Date: 2026-04-09 12:00:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260409_0027"
down_revision: Union[str, None] = "20260409_0026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("ticket_transfer_invites", sa.Column("recipient_name", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("ticket_transfer_invites", "recipient_name")
