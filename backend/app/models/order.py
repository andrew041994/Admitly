from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import OrderStatus, PayoutStatus, PricingSource, ReconciliationStatus
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.event import Event
    from app.models.order_item import OrderItem
    from app.models.ticket import Ticket
    from app.models.ticket_hold import TicketHold
    from app.models.user import User
    from app.models.promo_code import PromoCode
    from app.models.promo_code_redemption import PromoCodeRedemption


class Order(TimestampMixin, Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), nullable=False, index=True)
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus, name="order_status"), nullable=False, default=OrderStatus.PENDING
    )
    subtotal_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0.00"))
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0.00"))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    promo_code_id: Mapped[int | None] = mapped_column(ForeignKey("promo_codes.id"), nullable=True, index=True)
    promo_code_text: Mapped[str | None] = mapped_column(String(64), nullable=True)
    discount_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    discount_value_snapshot: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    pricing_source: Mapped[PricingSource] = mapped_column(
        Enum(PricingSource, name="pricing_source"), nullable=False, default=PricingSource.STANDARD
    )
    comp_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_comp: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="GYD")
    payment_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payment_intent_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payment_method: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payment_reference: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    payment_checkout_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    payment_verification_status: Mapped[str] = mapped_column(String(64), nullable=False, default="not_started")
    payment_submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    cancel_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    refunded_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    refund_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    refund_status: Mapped[str] = mapped_column(String(32), nullable=False, default="not_refunded")
    reconciliation_status: Mapped[ReconciliationStatus] = mapped_column(
        Enum(ReconciliationStatus, name="reconciliation_status"),
        nullable=False,
        default=ReconciliationStatus.UNRECONCILED,
    )
    reconciled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reconciled_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    reconciliation_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    payout_status: Mapped[PayoutStatus] = mapped_column(
        Enum(PayoutStatus, name="payout_status"),
        nullable=False,
        default=PayoutStatus.NOT_READY,
    )
    payout_batch_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    payout_included_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payout_paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payout_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped["User"] = relationship(foreign_keys=[user_id])
    event: Mapped["Event"] = relationship(back_populates="orders")
    order_items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )
    tickets: Mapped[list["Ticket"]] = relationship(back_populates="order", cascade="all, delete-orphan")
    ticket_holds: Mapped[list["TicketHold"]] = relationship(back_populates="order")
    promo_code: Mapped["PromoCode | None"] = relationship(back_populates="orders")
    promo_code_redemption: Mapped["PromoCodeRedemption | None"] = relationship(back_populates="order", uselist=False)
