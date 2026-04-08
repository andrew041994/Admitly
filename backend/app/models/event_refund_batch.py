from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import EventRefundBatchStatus
from app.models.mixins import TimestampMixin
from app.models.sa_enum import db_enum

if TYPE_CHECKING:
    from app.models.event import Event
    from app.models.user import User


class EventRefundBatch(TimestampMixin, Base):
    __tablename__ = "event_refund_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id"), nullable=False, index=True
    )
    initiated_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    status: Mapped[EventRefundBatchStatus] = mapped_column(
        db_enum(EventRefundBatchStatus, name="event_refund_batch_status"),
        nullable=False,
        default=EventRefundBatchStatus.PENDING,
        index=True,
    )
    total_orders: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processed_orders: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    successful_refunds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_orders: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_orders: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    event: Mapped["Event"] = relationship(back_populates="refund_batches")
    initiated_by_user: Mapped["User | None"] = relationship(
        foreign_keys=[initiated_by_user_id]
    )
