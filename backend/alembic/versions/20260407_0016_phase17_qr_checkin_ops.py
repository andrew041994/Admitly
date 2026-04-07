"""Phase 17 QR check-in door operations

Revision ID: 20260407_0016
Revises: 20260407_0015
Create Date: 2026-04-07 12:00:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260407_0016"
down_revision: Union[str, None] = "20260407_0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tickets", sa.Column("check_in_method", sa.String(length=16), nullable=True))


def downgrade() -> None:
    op.drop_column("tickets", "check_in_method")
