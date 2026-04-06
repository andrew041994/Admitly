from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.event import Event
    from app.models.ticket_tier import TicketTier
    from app.models.user import User


class TicketHold(Base):
    __tablename__ = "ticket_holds"
    __table_args__ = (CheckConstraint("quantity > 0", name="ticket_holds_quantity_positive"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    ticket_tier_id: Mapped[int] = mapped_column(ForeignKey("ticket_tiers.id"), nullable=False)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    event: Mapped["Event"] = relationship(back_populates="ticket_holds")
    ticket_tier: Mapped["TicketTier"] = relationship(back_populates="holds")
    user: Mapped["User | None"] = relationship(back_populates="ticket_holds")
