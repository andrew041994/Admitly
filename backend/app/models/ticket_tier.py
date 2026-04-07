from typing import TYPE_CHECKING

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.order_item import OrderItem
    from app.models.promo_code_ticket_tier import PromoCodeTicketTier
    from app.models.ticket import Ticket
    from app.models.ticket_hold import TicketHold


class TicketTier(TimestampMixin, Base):
    __tablename__ = "ticket_tiers"
    __table_args__ = (UniqueConstraint("event_id", "tier_code", name="uq_ticket_tiers_event_id_tier_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    tier_code: Mapped[str] = mapped_column(String(64), nullable=False)
    price_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="GYD")
    quantity_total: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_sold: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quantity_held: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    min_per_order: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    max_per_order: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    sales_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sales_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    access_description: Mapped[str | None] = mapped_column(Text, nullable=True)

    event = relationship("Event", back_populates="ticket_tiers")
    holds: Mapped[list["TicketHold"]] = relationship(back_populates="ticket_tier")
    order_items: Mapped[list["OrderItem"]] = relationship(back_populates="ticket_tier")
    tickets: Mapped[list["Ticket"]] = relationship(back_populates="ticket_tier")
    promo_code_scopes: Mapped[list["PromoCodeTicketTier"]] = relationship(
        back_populates="ticket_tier", cascade="all, delete-orphan"
    )
