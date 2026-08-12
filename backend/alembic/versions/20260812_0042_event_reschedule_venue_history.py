"""Add venue snapshots to event reschedule history.

Revision ID: 20260812_0042
Revises: 20260812_0041
"""

from alembic import op
import sqlalchemy as sa


revision = "20260812_0042"
down_revision = "20260812_0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("event_reschedules", sa.Column("previous_venue_id", sa.Integer(), nullable=True))
    op.add_column("event_reschedules", sa.Column("new_venue_id", sa.Integer(), nullable=True))
    op.add_column("event_reschedules", sa.Column("previous_custom_venue_name", sa.String(length=255), nullable=True))
    op.add_column("event_reschedules", sa.Column("new_custom_venue_name", sa.String(length=255), nullable=True))
    op.add_column("event_reschedules", sa.Column("previous_custom_address_text", sa.Text(), nullable=True))
    op.add_column("event_reschedules", sa.Column("new_custom_address_text", sa.Text(), nullable=True))
    op.add_column("event_reschedules", sa.Column("previous_latitude", sa.Numeric(precision=10, scale=7), nullable=True))
    op.add_column("event_reschedules", sa.Column("new_latitude", sa.Numeric(precision=10, scale=7), nullable=True))
    op.add_column("event_reschedules", sa.Column("previous_longitude", sa.Numeric(precision=10, scale=7), nullable=True))
    op.add_column("event_reschedules", sa.Column("new_longitude", sa.Numeric(precision=10, scale=7), nullable=True))
    op.add_column(
        "event_reschedules",
        sa.Column("previous_is_location_pinned", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "event_reschedules",
        sa.Column("new_is_location_pinned", sa.Boolean(), server_default=sa.false(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("event_reschedules", "new_is_location_pinned")
    op.drop_column("event_reschedules", "previous_is_location_pinned")
    op.drop_column("event_reschedules", "new_longitude")
    op.drop_column("event_reschedules", "previous_longitude")
    op.drop_column("event_reschedules", "new_latitude")
    op.drop_column("event_reschedules", "previous_latitude")
    op.drop_column("event_reschedules", "new_custom_address_text")
    op.drop_column("event_reschedules", "previous_custom_address_text")
    op.drop_column("event_reschedules", "new_custom_venue_name")
    op.drop_column("event_reschedules", "previous_custom_venue_name")
    op.drop_column("event_reschedules", "new_venue_id")
    op.drop_column("event_reschedules", "previous_venue_id")
