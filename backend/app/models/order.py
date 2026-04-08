from __future__ import annotations

from datetime import datetime
import secrets
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, Text, event
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from app.db.base import Base
from app.lib.order_references import format_order_reference
from app.models.enums import (
    OrderStatus,
    PayoutStatus,
    PricingSource,
    ReconciliationStatus,
)
from app.models.mixins import TimestampMixin
from app.models.sa_enum import db_enum

if TYPE_CHECKING:
    from app.models.event import Event
    from app.models.order_item import OrderItem
    from app.models.ticket import Ticket
    from app.models.ticket_hold import TicketHold
    from app.models.user import User
    from app.models.promo_code import PromoCode
    from app.models.promo_code_redemption import PromoCodeRedemption
    from app.models.support_case import SupportCase
    from app.models.payment_attempt import PaymentAttempt


class Order(TimestampMixin, Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id"), nullable=False, index=True
    )
    status: Mapped[OrderStatus] = mapped_column(
        db_enum(OrderStatus, name="order_status"),
        nullable=False,
        default=OrderStatus.PENDING,
    )
    subtotal_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("0.00")
    )
    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("0.00")
    )
    total_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    promo_code_id: Mapped[int | None] = mapped_column(
        ForeignKey("promo_codes.id"), nullable=True, index=True
    )
    promo_code_text: Mapped[str | None] = mapped_column(String(64), nullable=True)
    discount_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    discount_value_snapshot: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    pricing_source: Mapped[PricingSource] = mapped_column(
        db_enum(PricingSource, name="pricing_source"),
        nullable=False,
        default=PricingSource.STANDARD,
    )
    comp_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_comp: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="GYD")
    payment_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payment_intent_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payment_method: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payment_reference: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    payment_checkout_url: Mapped[str | None] = mapped_column(
        String(1024), nullable=True
    )
    payment_verification_status: Mapped[str] = mapped_column(
        String(64), nullable=False, default="not_started"
    )
    payment_submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancelled_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    cancel_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    refunded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    refunded_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    refund_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    refund_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="not_refunded"
    )
    reconciliation_status: Mapped[ReconciliationStatus] = mapped_column(
        db_enum(ReconciliationStatus, name="reconciliation_status"),
        nullable=False,
        default=ReconciliationStatus.UNRECONCILED,
    )
    reconciled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reconciled_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    reconciliation_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    payout_status: Mapped[PayoutStatus] = mapped_column(
        db_enum(PayoutStatus, name="payout_status"),
        nullable=False,
        default=PayoutStatus.NOT_READY,
    )
    payout_batch_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    payout_included_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    payout_paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    payout_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reference_code: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        unique=True,
        index=True,
        default=lambda: f"TMP-{secrets.token_hex(8).upper()}",
    )

    user: Mapped["User"] = relationship(foreign_keys=[user_id])
    event: Mapped["Event"] = relationship(back_populates="orders")
    order_items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )
    tickets: Mapped[list["Ticket"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )
    ticket_holds: Mapped[list["TicketHold"]] = relationship(back_populates="order")
    promo_code: Mapped["PromoCode | None"] = relationship(back_populates="orders")
    promo_code_redemption: Mapped["PromoCodeRedemption | None"] = relationship(
        back_populates="order", uselist=False
    )
    support_cases: Mapped[list["SupportCase"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )
    payment_attempts: Mapped[list["PaymentAttempt"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )


@event.listens_for(Session, "before_flush")
def _track_new_orders_for_reference_assignment(
    session: Session,
    flush_context,  # noqa: ANN001
    instances,  # noqa: ANN001
) -> None:
    pending_orders = [
        obj
        for obj in session.new
        if isinstance(obj, Order) and (not obj.reference_code or obj.reference_code.startswith("TMP-"))
    ]
    if pending_orders:
        tracked = session.info.setdefault("orders_missing_reference", set())
        tracked.update(pending_orders)


@event.listens_for(Session, "after_flush_postexec")
def _assign_reference_codes_after_insert(
    session: Session,
    flush_context,  # noqa: ANN001
) -> None:
    tracked_orders = session.info.get("orders_missing_reference")
    if not tracked_orders:
        return

    unresolved_orders = set()
    for order in tracked_orders:
        if order not in session:
            continue
        if order.id is None:
            unresolved_orders.add(order)
            continue
        if order.reference_code and not order.reference_code.startswith("TMP-"):
            continue
        order.reference_code = format_order_reference(order.id)

    if unresolved_orders:
        session.info["orders_missing_reference"] = unresolved_orders
    else:
        session.info.pop("orders_missing_reference", None)
