from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import EventApprovalStatus, EventStatus, EventVisibility
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.event_staff import EventStaff
    from app.models.organizer_profile import OrganizerProfile
    from app.models.order import Order
    from app.models.event_reminder_log import EventReminderLog
    from app.models.ticket import Ticket
    from app.models.ticket_hold import TicketHold
    from app.models.ticket_tier import TicketTier
    from app.models.venue import Venue
    from app.models.promo_code import PromoCode


class Event(TimestampMixin, Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    organizer_id: Mapped[int] = mapped_column(
        ForeignKey("organizer_profiles.id"), nullable=False, index=True
    )
    venue_id: Mapped[int | None] = mapped_column(ForeignKey("venues.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    short_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    long_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    cover_image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    doors_open_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sales_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sales_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="America/Guyana")
    status: Mapped[EventStatus] = mapped_column(
        Enum(EventStatus, name="event_status"), nullable=False, default=EventStatus.DRAFT
    )
    visibility: Mapped[EventVisibility] = mapped_column(
        Enum(EventVisibility, name="event_visibility"),
        nullable=False,
        default=EventVisibility.PUBLIC,
    )
    approval_status: Mapped[EventApprovalStatus] = mapped_column(
        Enum(EventApprovalStatus, name="event_approval_status"),
        nullable=False,
        default=EventApprovalStatus.PENDING,
    )

    refund_policy_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    terms_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    custom_venue_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    custom_address_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)
    is_location_pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    organizer: Mapped["OrganizerProfile"] = relationship(back_populates="events")
    venue: Mapped["Venue | None"] = relationship(back_populates="events")
    staff: Mapped[list["EventStaff"]] = relationship(back_populates="event")
    ticket_tiers: Mapped[list["TicketTier"]] = relationship(back_populates="event")

    orders: Mapped[list["Order"]] = relationship(back_populates="event")
    tickets: Mapped[list["Ticket"]] = relationship(back_populates="event")
    ticket_holds: Mapped[list["TicketHold"]] = relationship(back_populates="event")
    promo_codes: Mapped[list["PromoCode"]] = relationship(back_populates="event", cascade="all, delete-orphan")
    reminder_logs: Mapped[list["EventReminderLog"]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )
