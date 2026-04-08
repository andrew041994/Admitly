from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import ReminderType
from app.models.mixins import TimestampMixin
from app.models.sa_enum import db_enum

if TYPE_CHECKING:
    from app.models.event import Event
    from app.models.user import User


class EventReminderLog(TimestampMixin, Base):
    __tablename__ = "event_reminder_logs"
    __table_args__ = (
        UniqueConstraint(
            "event_id",
            "user_id",
            "reminder_type",
            name="uq_event_reminder_logs_event_user_type",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reminder_type: Mapped[ReminderType] = mapped_column(
        db_enum(ReminderType, name="reminder_type"), nullable=False, index=True
    )
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    event: Mapped["Event"] = relationship(back_populates="reminder_logs")
    user: Mapped["User"] = relationship(back_populates="event_reminder_logs")
