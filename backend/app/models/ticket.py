from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import TicketStatus
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.event import Event
    from app.models.order import Order
    from app.models.order_item import OrderItem
    from app.models.ticket_tier import TicketTier
    from app.models.user import User


class Ticket(TimestampMixin, Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    order_item_id: Mapped[int] = mapped_column(
        ForeignKey("order_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    purchaser_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    owner_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ticket_tier_id: Mapped[int] = mapped_column(ForeignKey("ticket_tiers.id"), nullable=False, index=True)
    status: Mapped[TicketStatus] = mapped_column(
        Enum(TicketStatus, name="ticket_status"), nullable=False, default=TicketStatus.ISSUED, index=True
    )
    ticket_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    qr_payload: Mapped[str] = mapped_column(Text, nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    transferred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    transfer_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    checked_in_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    voided_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    void_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    order: Mapped["Order"] = relationship(back_populates="tickets")
    order_item: Mapped["OrderItem"] = relationship(back_populates="tickets")
    event: Mapped["Event"] = relationship(back_populates="tickets")
    user: Mapped["User"] = relationship(back_populates="tickets", foreign_keys=[user_id])
    purchaser: Mapped["User"] = relationship(back_populates="purchased_tickets", foreign_keys=[purchaser_user_id])
    owner: Mapped["User"] = relationship(back_populates="owned_tickets", foreign_keys=[owner_user_id])
    ticket_tier: Mapped["TicketTier"] = relationship(back_populates="tickets")
    checked_in_by: Mapped["User | None"] = relationship(
        back_populates="checked_in_tickets", foreign_keys=[checked_in_by_user_id]
    )
    voided_by: Mapped["User | None"] = relationship(back_populates="voided_tickets", foreign_keys=[voided_by_user_id])
