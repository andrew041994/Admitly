from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.enums import OrderStatus
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.ticket_hold import TicketHold
from app.services.ticket_holds import get_guyana_now


class OrderFlowError(ValueError):
    """Base business-rule error for order creation from holds."""


class EmptyHoldSelectionError(OrderFlowError):
    """Raised when hold_ids is empty."""


class HoldNotFoundError(OrderFlowError):
    """Raised when any requested hold cannot be found."""


class HoldOwnershipError(OrderFlowError):
    """Raised when a hold does not belong to the authenticated user."""


class HoldExpiredError(OrderFlowError):
    """Raised when a hold has expired."""


class HoldAlreadyAttachedError(OrderFlowError):
    """Raised when a hold is already attached to an order."""


class HoldEventMismatchError(OrderFlowError):
    """Raised when provided holds span multiple events."""


class HoldCurrencyMismatchError(OrderFlowError):
    """Raised when provided holds span multiple currencies."""


class OrderNotPayableError(OrderFlowError):
    """Raised when pending order is no longer payable."""


class OrderNotFoundError(OrderFlowError):
    """Raised when order does not exist."""


def _to_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def create_pending_order_from_holds(
    db: Session,
    *,
    user_id: int,
    hold_ids: list[int],
    now: datetime | None = None,
) -> Order:
    if not hold_ids:
        raise EmptyHoldSelectionError("At least one hold id is required.")

    unique_hold_ids = list(dict.fromkeys(hold_ids))
    reference_now = _to_aware(now) if now is not None else get_guyana_now()

    tx_ctx = db.begin_nested() if db.in_transaction() else db.begin()
    with tx_ctx:
        holds = (
            db.execute(
                select(TicketHold)
                .options(joinedload(TicketHold.ticket_tier))
                .where(TicketHold.id.in_(unique_hold_ids))
                .with_for_update()
            )
            .unique()
            .scalars()
            .all()
        )

        if len(holds) != len(unique_hold_ids):
            raise HoldNotFoundError("One or more holds were not found.")

        event_ids: set[int] = set()
        currencies: set[str] = set()
        total_amount = Decimal("0.00")

        for hold in holds:
            if hold.user_id != user_id:
                raise HoldOwnershipError(f"Hold {hold.id} does not belong to the authenticated user.")
            if _to_aware(hold.expires_at) <= reference_now:
                raise HoldExpiredError(f"Hold {hold.id} is expired.")
            if hold.order_id is not None:
                raise HoldAlreadyAttachedError(f"Hold {hold.id} has already been used in an order.")

            event_ids.add(hold.event_id)
            tier_currency = hold.ticket_tier.currency
            currencies.add(tier_currency)
            total_amount += Decimal(hold.quantity) * Decimal(hold.ticket_tier.price_amount)

        if len(event_ids) != 1:
            raise HoldEventMismatchError("All holds must belong to the same event.")
        if len(currencies) != 1:
            raise HoldCurrencyMismatchError("All holds must share the same currency.")

        order = Order(
            user_id=user_id,
            event_id=next(iter(event_ids)),
            status=OrderStatus.PENDING,
            total_amount=total_amount,
            currency=next(iter(currencies)),
        )
        db.add(order)
        db.flush()

        for hold in holds:
            db.add(
                OrderItem(
                    order_id=order.id,
                    ticket_tier_id=hold.ticket_tier_id,
                    quantity=hold.quantity,
                    unit_price=hold.ticket_tier.price_amount,
                )
            )
            hold.order_id = order.id

        db.flush()

    return (
        db.execute(
            select(Order)
            .options(joinedload(Order.order_items), joinedload(Order.ticket_holds))
            .where(Order.id == order.id)
        )
        .unique()
        .scalar_one()
    )


def get_order_for_user(db: Session, *, order_id: int, user_id: int) -> Order | None:
    return (
        db.execute(
            select(Order)
            .options(joinedload(Order.order_items), joinedload(Order.ticket_holds))
            .where(Order.id == order_id, Order.user_id == user_id)
        )
        .unique()
        .scalar_one_or_none()
    )


def get_order_with_holds(db: Session, *, order_id: int) -> Order | None:
    return (
        db.execute(
            select(Order)
            .options(joinedload(Order.order_items), joinedload(Order.ticket_holds))
            .where(Order.id == order_id)
        )
        .unique()
        .scalar_one_or_none()
    )


def validate_order_still_payable(order: Order | None, now: datetime | None = None) -> None:
    if order is None:
        raise OrderNotFoundError("Order not found.")

    reference_now = _to_aware(now) if now is not None else get_guyana_now()
    if order.status != OrderStatus.PENDING:
        raise OrderNotPayableError("Only pending orders can be paid.")
    if not order.ticket_holds:
        raise OrderNotPayableError("Order has no linked holds.")

    if not all(_to_aware(hold.expires_at) > reference_now for hold in order.ticket_holds):
        order.status = OrderStatus.EXPIRED
        raise OrderNotPayableError("Order holds have expired.")


def complete_paid_order(
    db: Session,
    order: Order,
    *,
    paid_at: datetime | None = None,
    payment_reference: str | None = None,
) -> Order:
    if order.payment_verification_status != "verified":
        raise OrderNotPayableError("Order payment is not verified.")

    if order.status != OrderStatus.COMPLETED:
        order.status = OrderStatus.COMPLETED

    if payment_reference:
        order.payment_reference = payment_reference

    order.paid_at = _to_aware(paid_at) if paid_at is not None else get_guyana_now()
    db.flush()

    # TODO: trigger downstream ticket issuance once QR/ticket generation is implemented.
    return order
