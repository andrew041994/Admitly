from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import TicketScanStatus
from app.models.mixins import TimestampMixin
from app.models.sa_enum import db_enum

if TYPE_CHECKING:
    from app.models.ticket import Ticket
    from app.models.user import User


class TicketScanLog(TimestampMixin, Base):
    __tablename__ = "ticket_scan_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey("tickets.id"), nullable=True, index=True)
    scanned_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    scanned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    status: Mapped[TicketScanStatus] = mapped_column(
        db_enum(TicketScanStatus, name="ticket_scan_status"),
        nullable=False,
        index=True,
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    ticket: Mapped["Ticket | None"] = relationship(back_populates="scan_logs")
    scanner: Mapped["User | None"] = relationship(back_populates="ticket_scan_logs", foreign_keys=[scanned_by])
