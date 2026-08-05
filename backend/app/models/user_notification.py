from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.push_dispatch import PushDispatch
    from app.models.user import User


class UserNotification(TimestampMixin, Base):
    __tablename__ = "user_notifications"
    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_user_notifications_dedupe_key"),
        Index("ix_user_notifications_user_created", "user_id", "created_at"),
        Index("ix_user_notifications_user_unread", "user_id", "is_read", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    notification_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    body: Mapped[str] = mapped_column(String(500), nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    route_key: Mapped[str | None] = mapped_column(String(32), nullable=True)
    route_params: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    related_entity_type: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    related_entity_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    dedupe_key: Mapped[str] = mapped_column(String(255), nullable=False)
    push_status: Mapped[str] = mapped_column(String(32), nullable=False, default="not_queued", index=True)

    user: Mapped["User"] = relationship(back_populates="notifications")
    push_dispatches: Mapped[list["PushDispatch"]] = relationship(
        back_populates="notification", cascade="all, delete-orphan"
    )


class NotificationPreference(TimestampMixin, Base):
    __tablename__ = "notification_preferences"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    ticket_activity_push_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    event_reminders_push_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    nearby_events_push_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    location_discovery_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    latitude: Mapped[float | None] = mapped_column(nullable=True)
    longitude: Mapped[float | None] = mapped_column(nullable=True)
    location_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="notification_preference")
