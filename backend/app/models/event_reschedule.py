from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.event import Event
    from app.models.user import User


class EventReschedule(TimestampMixin, Base):
    __tablename__ = "event_reschedules"
    __table_args__ = (
        UniqueConstraint("event_id", "idempotency_key", name="uq_event_reschedules_event_idempotency_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    previous_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    previous_end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    previous_doors_open_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    previous_sales_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    previous_sales_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    new_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    new_end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    new_doors_open_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    new_sales_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    new_sales_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    previous_venue_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    new_venue_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    previous_custom_venue_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    new_custom_venue_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    previous_custom_address_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_custom_address_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    previous_latitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)
    new_latitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)
    previous_longitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)
    new_longitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)
    previous_is_location_pinned: Mapped[bool] = mapped_column(Boolean, nullable=False)
    new_is_location_pinned: Mapped[bool] = mapped_column(Boolean, nullable=False)
    rescheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    event: Mapped["Event"] = relationship(back_populates="reschedules")
    actor: Mapped["User"] = relationship()
