from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.push_token import PushToken
    from app.models.user_notification import UserNotification


class PushDispatch(TimestampMixin, Base):
    __tablename__ = "push_dispatches"
    __table_args__ = (
        UniqueConstraint("notification_id", "push_token_id", name="uq_push_dispatch_notification_token"),
        Index("ix_push_dispatches_claim", "status", "next_attempt_at", "id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    notification_id: Mapped[int] = mapped_column(
        ForeignKey("user_notifications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    push_token_id: Mapped[int] = mapped_column(
        ForeignKey("push_tokens.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provider_ticket_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    provider_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)

    notification: Mapped["UserNotification"] = relationship(back_populates="push_dispatches")
    push_token: Mapped["PushToken"] = relationship(back_populates="dispatches")


class NotificationJob(TimestampMixin, Base):
    __tablename__ = "notification_jobs"
    __table_args__ = (Index("ix_notification_jobs_claim", "status", "run_at", "id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    job_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    dedupe_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    related_entity_id: Mapped[int] = mapped_column(nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_cursor_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
