from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.enums import EventApprovalStatus, EventStatus, OrderStatus, PayoutStatus, ReconciliationStatus, TicketStatus
from app.models.event import Event
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.ticket_hold import TicketHold
from app.models.ticket_tier import TicketTier
from app.models.user import User
from app.services.event_permissions import EventPermissionAction, has_event_permission_by_id
from app.services.promo_codes import (
    PromoCodeValidationError,
    apply_promo_code_to_order_pricing_context,
    comp_pricing,
    record_promo_redemption_for_order,
    standard_pricing,
)
from app.services.notifications import (
    NotificationDispatchResult,
    notify_order_cancelled,
    notify_order_completed,
    notify_order_refunded,
    notify_tickets_issued,
)
from app.services.tickets import invalidate_order_tickets, issue_tickets_for_completed_order
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


class OrderAuthorizationError(OrderFlowError):
    """Raised when actor is not authorized for order reversal operations."""


class OrderCancellationError(OrderFlowError):
    """Raised when pending cancellation request is invalid."""


class OrderRefundError(OrderFlowError):
    """Raised when refund request is invalid."""


def _to_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def create_pending_order_from_holds(
    db: Session,
    *,
    user_id: int,
    hold_ids: list[int],
    promo_code_text: str | None = None,
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
        subtotal_amount = Decimal("0.00")
        tier_ids: list[int] = []

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
            tier_ids.append(hold.ticket_tier_id)
            subtotal_amount += Decimal(hold.quantity) * Decimal(hold.ticket_tier.price_amount)

        if len(event_ids) != 1:
            raise HoldEventMismatchError("All holds must belong to the same event.")
        if len(currencies) != 1:
            raise HoldCurrencyMismatchError("All holds must share the same currency.")

        event = db.execute(select(Event).where(Event.id == next(iter(event_ids)))).scalar_one_or_none()
        if event is None or event.status != EventStatus.PUBLISHED or event.approval_status != EventApprovalStatus.APPROVED:
            raise OrderNotPayableError("Event is not currently sellable.")

        pricing = standard_pricing(subtotal_amount)
        if promo_code_text:
            pricing = apply_promo_code_to_order_pricing_context(
                db,
                event_id=next(iter(event_ids)),
                user_id=user_id,
                tier_ids=tier_ids,
                subtotal_amount=subtotal_amount,
                promo_code_text=promo_code_text,
                now=reference_now,
            )

        order = Order(
            user_id=user_id,
            event_id=next(iter(event_ids)),
            status=OrderStatus.PENDING,
            subtotal_amount=pricing.subtotal_amount,
            discount_amount=pricing.discount_amount,
            total_amount=pricing.total_amount,
            currency=next(iter(currencies)),
            promo_code_id=pricing.promo_code_id,
            promo_code_text=pricing.promo_code_text,
            discount_type=pricing.discount_type,
            discount_value_snapshot=pricing.discount_value_snapshot,
            pricing_source=pricing.pricing_source,
            is_comp=False,
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
            .options(joinedload(Order.order_items), joinedload(Order.ticket_holds), joinedload(Order.tickets))
            .where(Order.id == order_id, Order.user_id == user_id)
        )
        .unique()
        .scalar_one_or_none()
    )


def get_order_with_holds(db: Session, *, order_id: int) -> Order | None:
    return (
        db.execute(
            select(Order)
            .options(joinedload(Order.order_items), joinedload(Order.ticket_holds), joinedload(Order.tickets))
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

    effective_now = reference_now

    normalized_holds: list[datetime] = []
    for hold in order.ticket_holds:
        hold_expires_at = hold.expires_at
        if hold_expires_at.tzinfo is None:
            hold_expires_at = hold_expires_at.replace(tzinfo=effective_now.tzinfo or timezone.utc)
        normalized_holds.append(hold_expires_at)

    if not all(hold > effective_now.astimezone(hold.tzinfo) for hold in normalized_holds):
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

    became_completed = order.status != OrderStatus.COMPLETED
    if became_completed:
        order.status = OrderStatus.COMPLETED

    if payment_reference:
        order.payment_reference = payment_reference

    if order.refund_status != "refunded":
        order.reconciliation_status = ReconciliationStatus.UNRECONCILED
        order.payout_status = PayoutStatus.ELIGIBLE

    order.paid_at = _to_aware(paid_at) if paid_at is not None else get_guyana_now()
    db.flush()

    tickets = issue_tickets_for_completed_order(db, order)
    if became_completed:
        record_promo_redemption_for_order(db, order=order)
    if became_completed:
        notify_order_completed(db, order)
        notify_tickets_issued(db, order, tickets)
    return order


def create_comp_order_for_user(
    db: Session,
    *,
    event_id: int,
    purchaser_user_id: int,
    actor_user_id: int,
    ticket_requests: list[dict[str, int]],
    reason: str | None = None,
) -> Order:
    if not has_event_permission_by_id(
        db,
        user_id=actor_user_id,
        event_id=event_id,
        action=EventPermissionAction.EDIT_EVENT,
    ):
        raise OrderAuthorizationError("Not authorized to comp tickets for this event.")
    if not ticket_requests:
        raise OrderFlowError("At least one ticket request is required.")

    tier_quantities = {int(item["ticket_tier_id"]): int(item["quantity"]) for item in ticket_requests if int(item["quantity"]) > 0}
    if not tier_quantities:
        raise OrderFlowError("Ticket quantities must be greater than zero.")

    tiers = db.execute(
        select(TicketTier).where(TicketTier.event_id == event_id, TicketTier.id.in_(tier_quantities.keys())).with_for_update()
    ).scalars().all()
    if len(tiers) != len(tier_quantities):
        raise OrderFlowError("One or more ticket tiers were not found for event.")

    subtotal = Decimal("0.00")
    for tier in tiers:
        quantity = tier_quantities[tier.id]
        remaining = int(tier.quantity_total) - int(tier.quantity_sold) - int(tier.quantity_held)
        if remaining < quantity:
            raise OrderFlowError(f"Insufficient availability for tier {tier.id}.")
        subtotal += Decimal(quantity) * Decimal(tier.price_amount)

    pricing = comp_pricing(subtotal)
    order = Order(
        user_id=purchaser_user_id,
        event_id=event_id,
        status=OrderStatus.COMPLETED,
        subtotal_amount=pricing.subtotal_amount,
        discount_amount=pricing.discount_amount,
        total_amount=pricing.total_amount,
        currency=tiers[0].currency,
        payment_provider=None,
        payment_method=None,
        payment_verification_status="verified",
        paid_at=get_guyana_now(),
        reconciliation_status=ReconciliationStatus.UNRECONCILED,
        payout_status=PayoutStatus.NOT_READY,
        pricing_source=pricing.pricing_source,
        comp_reason=reason.strip() if reason else None,
        is_comp=True,
    )
    db.add(order)
    db.flush()

    for tier in tiers:
        db.add(
            OrderItem(
                order_id=order.id,
                ticket_tier_id=tier.id,
                quantity=tier_quantities[tier.id],
                unit_price=tier.price_amount,
            )
        )
    db.flush()
    issue_tickets_for_completed_order(db, order)
    db.flush()
    return get_order_with_holds(db, order_id=order.id) or order


def cancel_pending_order(
    db: Session,
    *,
    order_id: int,
    actor_user_id: int,
    reason: str | None = None,
) -> Order:
    tx_ctx = db.begin_nested() if db.in_transaction() else db.begin()
    with tx_ctx:
        order = (
            db.execute(
                select(Order)
                .options(joinedload(Order.ticket_holds))
                .where(Order.id == order_id)
                .with_for_update()
            )
            .unique()
            .scalar_one_or_none()
        )
        if order is None:
            raise OrderNotFoundError("Order not found.")
        if order.user_id != actor_user_id:
            raise OrderAuthorizationError("Only the order owner can cancel a pending order.")
        if order.status == OrderStatus.CANCELLED:
            raise OrderCancellationError("Order is already cancelled.")
        if order.status != OrderStatus.PENDING:
            raise OrderCancellationError("Only pending orders can be cancelled.")

        now = get_guyana_now()
        order.status = OrderStatus.CANCELLED
        order.cancelled_at = now
        order.cancelled_by_user_id = actor_user_id
        order.cancel_reason = reason.strip() if reason else None
        order.updated_at = now
        db.flush()
        notify_order_cancelled(order, actor_user_id=actor_user_id)
        return order


def refund_completed_order(
    db: Session,
    *,
    order_id: int,
    actor_user_id: int,
    reason: str | None = None,
) -> Order:
    tx_ctx = db.begin_nested() if db.in_transaction() else db.begin()
    with tx_ctx:
        order = (
            db.execute(
                select(Order)
                .options(joinedload(Order.tickets), joinedload(Order.event), joinedload(Order.order_items))
                .where(Order.id == order_id)
                .with_for_update()
            )
            .unique()
            .scalar_one_or_none()
        )
        if order is None:
            raise OrderNotFoundError("Order not found.")
        if not has_event_permission_by_id(
            db,
            user_id=actor_user_id,
            event_id=order.event_id,
            action=EventPermissionAction.MANAGE_REFUNDS,
        ):
            raise OrderAuthorizationError("Not authorized to refund this order.")
        if order.status != OrderStatus.COMPLETED:
            raise OrderRefundError("Only completed orders can be refunded.")
        if order.payment_verification_status != "verified":
            raise OrderRefundError("Only verified-paid orders can be refunded.")
        if order.refund_status == "refunded" or order.refunded_at is not None:
            raise OrderRefundError("Order has already been refunded.")
        if any(ticket.status == TicketStatus.CHECKED_IN for ticket in order.tickets):
            raise OrderRefundError("Orders with checked-in tickets cannot be fully refunded.")

        now = get_guyana_now()
        order.refund_status = "refunded"
        order.refunded_at = now
        order.refunded_by_user_id = actor_user_id
        order.refund_reason = reason.strip() if reason else None
        order.updated_at = now
        db.flush()

        invalidate_order_tickets(
            db,
            order_id=order.id,
            actor_user_id=actor_user_id,
            reason=reason or "Order refunded",
        )
        try:
            notify_order_refunded(order, actor_user_id=actor_user_id)
        except TypeError:
            notify_order_refunded(db, order, actor_user_id=actor_user_id)
        return order


class OrderResendError(OrderFlowError):
    """Raised when resend is not allowed."""


def resend_order_confirmation(
    db: Session,
    *,
    order_id: int,
    actor_user_id: int,
) -> NotificationDispatchResult:
    order = (
        db.execute(
            select(Order)
            .options(joinedload(Order.tickets), joinedload(Order.event))
            .where(Order.id == order_id)
        )
        .unique()
        .scalar_one_or_none()
    )
    if order is None:
        raise OrderNotFoundError("Order not found.")
    if order.user_id != actor_user_id:
        raise OrderAuthorizationError("Only the order owner can resend confirmation notifications.")
    if order.status != OrderStatus.COMPLETED:
        raise OrderResendError("Only completed orders can resend confirmation notifications.")

    completed_result = notify_order_completed(db, order)
    tickets_result = notify_tickets_issued(db, order, list(order.tickets))
    return NotificationDispatchResult(
        success=completed_result.success and tickets_result.success,
        channel_results={
            "order_email": completed_result.channel_results.get("email", "skipped"),
            "order_push": completed_result.channel_results.get("push", "skipped"),
            "tickets_email": tickets_result.channel_results.get("email", "skipped"),
            "tickets_push": tickets_result.channel_results.get("push", "skipped"),
        },
    )
