"""Phase 1 foundation models

Revision ID: 20260406_0001
Revises:
Create Date: 2026-04-06 00:00:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260406_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


event_status = sa.Enum("draft", "published", "cancelled", "completed", name="event_status")
event_visibility = sa.Enum("public", "unlisted", "private", name="event_visibility")
event_approval_status = sa.Enum("pending", "approved", "rejected", name="event_approval_status")
event_staff_role = sa.Enum("owner", "manager", "scanner", name="event_staff_role")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    op.create_index(op.f("ix_users_phone"), "users", ["phone"], unique=False)

    op.create_table(
        "organizer_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("business_name", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("contact_email", sa.String(length=255), nullable=True),
        sa.Column("contact_phone", sa.String(length=32), nullable=True),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_approved", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_organizer_profiles_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organizer_profiles")),
        sa.UniqueConstraint("user_id", name=op.f("uq_organizer_profiles_user_id")),
    )

    op.create_table(
        "venues",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organizer_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("country", sa.String(length=120), nullable=True),
        sa.Column("city", sa.String(length=120), nullable=True),
        sa.Column("address_line1", sa.String(length=255), nullable=True),
        sa.Column("address_line2", sa.String(length=255), nullable=True),
        sa.Column("latitude", sa.Numeric(precision=10, scale=7), nullable=True),
        sa.Column("longitude", sa.Numeric(precision=10, scale=7), nullable=True),
        sa.Column("capacity", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["organizer_id"],
            ["organizer_profiles.id"],
            name=op.f("fk_venues_organizer_id_organizer_profiles"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_venues")),
    )
    op.create_index(op.f("ix_venues_organizer_id"), "venues", ["organizer_id"], unique=False)

    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organizer_id", sa.Integer(), nullable=False),
        sa.Column("venue_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("short_description", sa.Text(), nullable=True),
        sa.Column("long_description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("cover_image_url", sa.String(length=500), nullable=True),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("doors_open_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sales_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sales_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="America/Guyana"),
        sa.Column("status", event_status, nullable=False, server_default="draft"),
        sa.Column("visibility", event_visibility, nullable=False, server_default="public"),
        sa.Column("approval_status", event_approval_status, nullable=False, server_default="pending"),
        sa.Column("refund_policy_text", sa.Text(), nullable=True),
        sa.Column("terms_text", sa.Text(), nullable=True),
        sa.Column("custom_venue_name", sa.String(length=255), nullable=True),
        sa.Column("custom_address_text", sa.Text(), nullable=True),
        sa.Column("latitude", sa.Numeric(precision=10, scale=7), nullable=True),
        sa.Column("longitude", sa.Numeric(precision=10, scale=7), nullable=True),
        sa.Column("is_location_pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["organizer_id"], ["organizer_profiles.id"], name=op.f("fk_events_organizer_id_organizer_profiles")),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"], name=op.f("fk_events_venue_id_venues")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_events")),
    )
    op.create_index(op.f("ix_events_organizer_id"), "events", ["organizer_id"], unique=False)
    op.create_index(op.f("ix_events_slug"), "events", ["slug"], unique=True)

    op.create_table(
        "event_staff",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", event_staff_role, nullable=False, server_default="scanner"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("invited_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], name=op.f("fk_event_staff_event_id_events")),
        sa.ForeignKeyConstraint(["invited_by_user_id"], ["users.id"], name=op.f("fk_event_staff_invited_by_user_id_users")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_event_staff_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_event_staff")),
        sa.UniqueConstraint("event_id", "user_id", name="uq_event_staff_event_id_user_id"),
    )
    op.create_index(op.f("ix_event_staff_event_id"), "event_staff", ["event_id"], unique=False)
    op.create_index(op.f("ix_event_staff_invited_by_user_id"), "event_staff", ["invited_by_user_id"], unique=False)
    op.create_index(op.f("ix_event_staff_user_id"), "event_staff", ["user_id"], unique=False)

    op.create_table(
        "ticket_tiers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("tier_code", sa.String(length=64), nullable=False),
        sa.Column("price_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="GYD"),
        sa.Column("quantity_total", sa.Integer(), nullable=False),
        sa.Column("quantity_sold", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("quantity_held", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("min_per_order", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("max_per_order", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("sales_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sales_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("access_description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], name=op.f("fk_ticket_tiers_event_id_events")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ticket_tiers")),
        sa.UniqueConstraint("event_id", "tier_code", name="uq_ticket_tiers_event_id_tier_code"),
    )
    op.create_index(op.f("ix_ticket_tiers_event_id"), "ticket_tiers", ["event_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_ticket_tiers_event_id"), table_name="ticket_tiers")
    op.drop_table("ticket_tiers")

    op.drop_index(op.f("ix_event_staff_user_id"), table_name="event_staff")
    op.drop_index(op.f("ix_event_staff_invited_by_user_id"), table_name="event_staff")
    op.drop_index(op.f("ix_event_staff_event_id"), table_name="event_staff")
    op.drop_table("event_staff")

    op.drop_index(op.f("ix_events_slug"), table_name="events")
    op.drop_index(op.f("ix_events_organizer_id"), table_name="events")
    op.drop_table("events")

    op.drop_index(op.f("ix_venues_organizer_id"), table_name="venues")
    op.drop_table("venues")

    op.drop_table("organizer_profiles")

    op.drop_index(op.f("ix_users_phone"), table_name="users")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")

    bind = op.get_bind()
    event_staff_role.drop(bind, checkfirst=True)
    event_approval_status.drop(bind, checkfirst=True)
    event_visibility.drop(bind, checkfirst=True)
    event_status.drop(bind, checkfirst=True)
