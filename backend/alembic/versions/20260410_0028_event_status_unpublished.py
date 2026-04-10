"""add unpublished event status

Revision ID: 20260410_0028
Revises: 20260409_0027
Create Date: 2026-04-10 00:00:00.000000
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "20260410_0028"
down_revision = "20260409_0027"
branch_labels = None
depends_on = None


def upgrade():
    # Run outside transaction
    op.execute("COMMIT")
    op.execute("ALTER TYPE event_status ADD VALUE IF NOT EXISTS 'unpublished'")


def downgrade() -> None:
    # PostgreSQL enums are not safely downgraded in-place.
    pass
